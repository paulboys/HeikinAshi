"""The closed loop: state, one batched decision, tools, repeat.

Each iteration asks every question in a single request -- one usefulness
question per eligible tool, plus sufficiency, contradiction and the shadow
order-balanced choice -- because latency barely grows with question count and
independent questions avoid the option-order bias a single choice would
carry.

The loop never lets the decision model end a run on its own: stopping is a
policy decision made in Python from the model's answers, and every bound that
guarantees termination is enforced here regardless of what comes back.

Public API:
    AgentRun, run_analysis(...)
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from stock_agent.asof import PriceProvider, audit_frames
from stock_agent.config import AgentConfig
from stock_agent.guards import LoopGuard
from stock_agent.jev.answers import JevResponse
from stock_agent.jev.questions import (
    CONVICTION_QID,
    SELECT_FWD_QID,
    SELECT_REV_QID,
    STOP_CONFLICT_QID,
    STOP_ENOUGH_QID,
    average_choice_probabilities,
    best_next_qid,
    build_question_set,
    usefulness_qid,
)
from stock_agent.policy import Decision, decide
from stock_agent.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec
from stock_agent.state import AnalysisState, state_hash
from stock_agent.trace import TraceWriter

__all__ = ["AgentRun", "DecisionModel", "run_analysis"]


class DecisionModel(Protocol):
    """Anything that can answer a question set.

    An implementation may also provide ``observe(state)``, which the loop
    calls with the numeric state before each request. The decision model
    itself does not: it is given the rendered text and nothing else.
    """

    model: str
    endpoint: str
    calls: int

    def ask(
        self,
        state: str,
        questions: Mapping[str, Mapping[str, Any]],
    ) -> JevResponse:
        """Answer questions about a state.

        Args:
            state: The compact textual state.
            questions: Question identifier to definition.

        Returns:
            The response.
        """
        ...


@dataclass
class AgentRun:
    """The outcome of one analysis.

    Attributes:
        state: Everything measured.
        exit_reason: Short identifier for why it stopped.
        exit_detail: Human explanation.
        partial: Whether it was cut short.
        decisions: Every policy decision, in order.
        tools_run: Analyses that produced measurements.
        caveats: Qualifications the reader must carry.
        trace_path: Where the decision trace was written.
        run_id: Identifier for this run.
        conviction: The model's reported conviction, if asked.
    """

    state: AnalysisState
    exit_reason: str = ""
    exit_detail: str = ""
    partial: bool = False
    decisions: list[Decision] = field(default_factory=list)
    tools_run: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    trace_path: Path | None = None
    run_id: str = ""
    conviction: int | None = None


def _call(spec: ToolSpec, ctx: ToolContext, deadline: float) -> ToolResult:
    """Run one tool, bounding it in time if it reaches the network.

    A tool that only computes cannot hang: it is arithmetic over a frame
    already in memory. A tool that fetches can block for as long as the far
    end cares to take, and no count-based budget notices, because they are all
    tested between rounds.

    The deadline is applied only to networked tools, which also keeps the
    worker from racing the main thread over shared state: those tools return
    their findings and touch nothing else, whereas a computed tool may write
    an artifact that a later analysis reads.

    A thread cannot be killed, so an abandoned fetch runs on as a daemon until
    the process exits. Its result is discarded.

    Args:
        spec: The tool to run.
        ctx: Execution context.
        deadline: Seconds allowed, for a networked tool.

    Returns:
        The tool's result, or a failure describing the timeout.
    """
    if spec.run is None:
        return ToolResult(spec.name, False, error="no run")
    if not spec.cost.network:
        return spec.run(ctx)

    holder: list[ToolResult] = []

    def worker() -> None:
        try:
            holder.append(spec.run(ctx))  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001 - reported on the main thread
            holder.append(
                ToolResult(
                    tool=spec.name,
                    success=False,
                    error=f"{type(exc).__name__}: {str(exc)[:150]}",
                )
            )

    thread = threading.Thread(target=worker, daemon=True, name=f"tool:{spec.name}")
    thread.start()
    thread.join(deadline)
    if holder:
        return holder[0]
    return ToolResult(
        tool=spec.name,
        success=False,
        error=(
            f"gave up after {deadline:.0f}s; the feed was still responding but " f"had not finished"
        ),
    )


def _execute(
    spec: ToolSpec,
    ctx: ToolContext,
    role: str,
    iteration: int,
    guard: LoopGuard,
    run: AgentRun,
    deadline: float = 45.0,
) -> dict[str, Any]:
    """Run one tool and fold its result into the state.

    Args:
        spec: The tool to run.
        ctx: Execution context.
        role: Why it is running.
        iteration: Current iteration.
        guard: Budget guard to account against.
        run: The run being assembled.
        deadline: Seconds allowed for a networked tool.

    Returns:
        A trace record for this execution.
    """
    started = time.perf_counter()
    try:
        result = _call(spec, ctx, deadline)
    except Exception as exc:  # noqa: BLE001 - a broken tool must not end the run
        result = ToolResult(
            tool=spec.name,
            success=False,
            error=f"{type(exc).__name__}: {str(exc)[:150]}",
        )
    duration = time.perf_counter() - started

    if result.success:
        ctx.state.record(
            result.observations(iteration),
            spec.provenance(ctx.state.asof, iteration),
        )
        if spec.name not in run.tools_run:
            run.tools_run.append(spec.name)
        if spec.retrospective and spec.name not in str(run.caveats):
            run.caveats.append(
                f"{spec.title} is fitted with hindsight; its most recent " f"label is provisional."
            )

    from stock_agent.state import StepRecord

    ctx.state.history.append(
        StepRecord(
            tool=spec.name,
            role=role,
            iteration=iteration,
            status="ok" if result.success else "error",
            duration_s=round(duration, 4),
            error=result.error,
        )
    )
    guard.record_tool(spec.name, result.success, result.network_calls)

    return {
        "tool": spec.name,
        "role": role,
        "status": "ok" if result.success else "error",
        "duration_s": round(duration, 4),
        "network_calls": result.network_calls,
        "observations": dict(result.metrics),
        "error": result.error,
    }


def _parse(response: JevResponse, specs: Sequence[ToolSpec]) -> dict[str, Any]:
    """Extract the quantities the policy needs from a response.

    Args:
        response: The model's answers.
        specs: Candidates that were asked about.

    Returns:
        Both usefulness maps, plus sufficiency, conflict and conviction.
        ``routing`` names which map the policy was given, so a trace says
        which question decided the run rather than leaving it to be inferred.
    """
    usefulness: dict[str, float] = {}
    best_next: dict[str, float] = {}
    for spec in specs:
        probability = response.noul(usefulness_qid(spec.name))
        if probability is not None:
            usefulness[spec.name] = probability
        comparative = response.noul(best_next_qid(spec.name))
        if comparative is not None:
            best_next[spec.name] = comparative

    # The comparative question routes. Falling back is not a silent downgrade:
    # an empty comparative map with a usable absolute one would otherwise read
    # as "no candidates" and stop the run, which would look like a routing
    # decision rather than a parse failure.
    routing = "best_next" if best_next else "usefulness"

    conviction = response.score(CONVICTION_QID)
    return {
        "usefulness": usefulness,
        "best_next": best_next,
        "routing": routing,
        "enough": response.noul(STOP_ENOUGH_QID),
        "conflict": response.noul(STOP_CONFLICT_QID),
        "conviction": None if conviction is None else conviction.score,
    }


def _shadow(
    response: JevResponse, specs: Sequence[ToolSpec], top: str | None
) -> dict[str, Any] | None:
    """Compare the order-balanced choice against the usefulness ranking.

    Recorded only. The choice is known to favour whichever option appears
    first, so it measures that bias rather than steering the run.

    Args:
        response: The model's answers.
        specs: Candidates, in the order they were offered.
        top: The tool the usefulness questions ranked first.

    Returns:
        The comparison, or None when the pair was not asked.
    """
    forward = response.choice(SELECT_FWD_QID)
    reverse = response.choice(SELECT_REV_QID)
    if forward is None or reverse is None:
        return None

    averaged = average_choice_probabilities(forward.probabilities, reverse.probabilities)
    picked = max(averaged, key=lambda k: averaged[k]) if averaged else None
    first_option = specs[0].name if specs else None
    return {
        "first_option": first_option,
        "forward_choice": forward.choice,
        "reverse_choice": reverse.choice,
        "averaged_pick": picked,
        "agrees_with_usefulness_top1": picked == top,
        "forward_picked_first_option": forward.choice == first_option,
    }


def run_analysis(
    ticker: str,
    objective: str,
    registry: ToolRegistry,
    model: DecisionModel,
    provider: PriceProvider,
    config: AgentConfig,
    asof: date | None = None,
    trace_path: Path | None = None,
) -> AgentRun:
    """Analyse one ticker, letting the model choose the path.

    Args:
        ticker: Symbol to analyse.
        objective: What the analysis is for.
        registry: Available analyses.
        model: The decision model.
        provider: Source of price history.
        config: Thresholds and budgets.
        asof: Historical date to analyse as of, or None for live.
        trace_path: Where to write the decision trace.

    Returns:
        The completed run.
    """
    state = AnalysisState(
        ticker=ticker,
        objective=objective,
        asof=asof,
        data_source=str(getattr(provider, "source", "live")),
        interval=config.interval,
    )
    run = AgentRun(state=state)
    guard = LoopGuard(config.budget)
    writer = TraceWriter(trace_path)
    run.run_id = writer.run_id
    run.trace_path = trace_path

    writer.run_start(
        ticker=ticker,
        objective=objective,
        asof=None if asof is None else asof.isoformat(),
        config=config.to_dict(),
        tools=[
            {
                "name": s.name,
                "category": s.category,
                "cost": s.cost.cost_class,
                "asof_capable": s.asof_capable,
                "retrospective": s.retrospective,
                "computed_in_agent": s.computed_in_agent,
            }
            for s in registry.implemented()
        ],
        absent=[{"name": s.name, "reason": s.absent_reason} for s in registry.absent()],
        provider=getattr(provider, "source", "live"),
        mode=getattr(model, "endpoint", "unknown"),
    )

    conflict_veto_used = False
    indecision_streak = 0

    while True:
        before = state_hash(state)
        trip = guard.check()
        if trip is not None:
            run.exit_reason, run.exit_detail = trip.reason, trip.detail
            run.partial = True
            break

        eligible, excluded = registry.candidates(state, exclude=sorted(guard.disabled))
        eligible = [s for s in eligible if guard.may_run(s, state)[0]]

        # Price history is fetched without asking: every other analysis needs
        # it, so a question here would only ever have one sensible answer.
        if (
            config.policy.require_price_history
            and not state.has("ohlc.n_bars")
            and "price_history.ohlc" in registry
        ):
            spec = registry.get("price_history.ohlc")
            ctx = ToolContext(
                state, provider, spec.default_params, config.interval, config.default_bars
            )
            record = _execute(
                spec,
                ctx,
                "bootstrap",
                state.iteration,
                guard,
                run,
                config.budget.max_network_seconds,
            )
            audit_frames(state.frames, state.asof)
            decision = Decision(
                band="bootstrap",
                selected=("price_history.ohlc",),
                rationale="price history is a precondition for every analysis",
            )
            run.decisions.append(decision)
            after = state_hash(state)
            writer.iteration(
                iteration=state.iteration,
                state_hash_before=before,
                state_hash_after=after,
                state_text="",
                candidates=[],
                excluded=excluded,
                questions=None,
                response=None,
                parsed={},
                shadow=None,
                decision={
                    "band": decision.band,
                    "selected": list(decision.selected),
                    "rationale": decision.rationale,
                },
                tool_calls=[record],
                budget=guard.state.to_dict(),
            )
            guard.observe_iteration(before, after)
            guard.record_iteration()
            state.iteration += 1
            continue

        not_yet = [s.title for s in eligible]
        unavailable = [s.title for s in registry.absent()]
        state_text = state.to_jev_state(not_yet, unavailable)

        if not eligible:
            run.exit_reason = "no_candidates"
            run.exit_detail = "no applicable analyses remain"
            break

        questions = build_question_set(eligible, objective)
        guard.record_jev_call()

        # A baseline arm may read the numeric state; the decision model does
        # not implement this, so it sees only the rendered text. The asymmetry
        # favours the baselines deliberately -- a handicapped baseline would
        # make the comparison worthless.
        observe = getattr(model, "observe", None)
        if callable(observe):
            observe(state)

        response = model.ask(state_text, questions)
        parsed = _parse(response, eligible)

        # The comparative map ranks, the absolute map gates, and the act band
        # follows whichever question the ranking came from -- an arm that
        # answered only the absolute one keeps the original threshold.
        comparative = parsed["routing"] == "best_next"
        routed = parsed[parsed["routing"]]
        decision = decide(
            usefulness=parsed["usefulness"] or routed,
            ranking=routed,
            act_threshold=(
                config.policy.rank_act_threshold if comparative else config.policy.act_threshold
            ),
            enough=parsed["enough"],
            conflict=parsed["conflict"],
            config=config.policy,
            indecision_streak=indecision_streak,
            tools_run=len(run.tools_run),
            costs={s.name: s.cost.cost_class for s in eligible},
            conflict_veto_used=conflict_veto_used,
            jev_failed=not response.ok(),
        )
        run.decisions.append(decision)
        indecision_streak = decision.indecision_streak
        conflict_veto_used = conflict_veto_used or decision.stop_vetoed_by_conflict
        if parsed["conviction"] is not None:
            run.conviction = parsed["conviction"]

        records: list[dict[str, Any]] = []
        for name in decision.selected:
            spec = registry.get(name)
            for prereq in registry.prerequisite_plan(name, state):
                prereq_spec = registry.get(prereq)
                allowed, _ = guard.may_run(prereq_spec, state)
                if allowed:
                    records.append(
                        _execute(
                            prereq_spec,
                            ToolContext(
                                state,
                                provider,
                                prereq_spec.default_params,
                                config.interval,
                                config.default_bars,
                            ),
                            f"prerequisite_of:{name}",
                            state.iteration,
                            guard,
                            run,
                            config.budget.max_network_seconds,
                        )
                    )
            records.append(
                _execute(
                    spec,
                    ToolContext(
                        state, provider, spec.default_params, config.interval, config.default_bars
                    ),
                    "selected",
                    state.iteration,
                    guard,
                    run,
                    config.budget.max_network_seconds,
                )
            )

        # Checked every round rather than once at the end, so a leak names
        # the iteration that introduced it.
        audit_frames(state.frames, state.asof)

        after = state_hash(state)
        writer.iteration(
            iteration=state.iteration,
            state_hash_before=before,
            state_hash_after=after,
            state_text=state_text,
            candidates=[s.name for s in eligible],
            excluded=excluded,
            questions=questions,
            response={
                "latency_s": response.latency_s,
                "http_status": response.http_status,
                "attempts": response.attempts,
                "wrapper_key": response.wrapper_key,
                "usage": response.usage,
                "missing": list(response.missing),
                "malformed": list(response.malformed),
                "error": response.error,
                "model": response.model,
                # What answered, as distinct from what was asked for. A
                # benchmark is keyed on this: a silent substitution upstream
                # would otherwise be invisible in the record.
                "model_served": response.model_served,
            },
            parsed=parsed,
            shadow=_shadow(response, eligible, decision.top1),
            decision={
                "band": decision.band,
                "selected": list(decision.selected),
                "top1": decision.top1,
                "p_top1": decision.p_top1,
                "top2": decision.top2,
                "p_top2": decision.p_top2,
                "margin": decision.margin,
                "indecision_streak": decision.indecision_streak,
                "stop_vetoed_by_conflict": decision.stop_vetoed_by_conflict,
                "rationale": decision.rationale,
                "notes": list(decision.notes),
            },
            tool_calls=records,
            budget=guard.state.to_dict(),
        )
        guard.observe_iteration(before, after)
        guard.record_iteration()
        state.iteration += 1

        if decision.should_stop:
            run.exit_reason = decision.exit_reason or decision.band
            run.exit_detail = decision.rationale
            run.partial = decision.band == "jev_unavailable"
            break

    if not run.exit_reason:
        run.exit_reason = "completed"
        run.exit_detail = "the loop ended without a terminating decision"

    run.caveats.append(
        "Probabilities from the decision model are not calibrated; the "
        "thresholds above are policy settings, not beliefs."
    )
    writer.run_end(
        exit_reason=run.exit_reason,
        exit_detail=run.exit_detail,
        partial=run.partial,
        tools_run=run.tools_run,
        observations={k: o.value for k, o in state.observations.items()},
        caveats=run.caveats,
        budget=guard.state.to_dict(),
        final_state_hash=state_hash(state),
    )
    writer.close()
    return run
