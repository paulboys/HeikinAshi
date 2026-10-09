"""Re-deciding a recorded run, to prove the policy has not drifted.

A trace holds everything the policy was given and everything it concluded, so
the policy can be re-run against it offline: no network, no price data, no
decision model. If a refactor changes a branch, the replay says which
iteration diverged and how.

This is the one test that covers the policy as it was actually exercised
rather than as a table of cases someone thought to write down. It is also the
only check that a trace is complete enough to audit -- a field dropped from
the record shows up here as an unreplayable iteration.

Public API:
    IterationDiff, ReplayReport, replay_trace(path, config=None) -> ReplayReport
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stock_agent.config import PolicyConfig
from stock_agent.policy import decide
from stock_agent.trace import read_trace

__all__ = ["IterationDiff", "ReplayReport", "replay_trace"]

# Bands reached without asking anything; there is no decision to reproduce.
_UNASKED = frozenset({"bootstrap"})


@dataclass(frozen=True)
class IterationDiff:
    """One iteration whose replayed decision differs from the recorded one.

    Attributes:
        iteration: Round number.
        field_name: Which part of the decision differs.
        recorded: What the original run concluded.
        replayed: What the policy concludes now.
    """

    iteration: int
    field_name: str
    recorded: Any
    replayed: Any

    def __str__(self) -> str:
        """Render the divergence for a terminal.

        Returns:
            One line.
        """
        return (
            f"iteration {self.iteration}: {self.field_name} "
            f"was {self.recorded!r}, now {self.replayed!r}"
        )


@dataclass
class ReplayReport:
    """The outcome of replaying one trace.

    Attributes:
        path: Trace that was replayed.
        run_id: Identifier of the original run.
        ticker: Symbol it analysed.
        iterations_replayed: Rounds the policy was re-run for.
        iterations_skipped: Rounds with no decision to reproduce.
        diffs: Every divergence found.
        config_source: Whether thresholds came from the trace or the caller.
    """

    path: Path
    run_id: str = ""
    ticker: str = ""
    iterations_replayed: int = 0
    iterations_skipped: int = 0
    diffs: list[IterationDiff] = field(default_factory=list)
    config_source: str = "trace"

    @property
    def diverging_iterations(self) -> int:
        """Count the rounds that reached a different decision.

        Returns:
            Distinct iteration numbers among the divergences.
        """
        return len({d.iteration for d in self.diffs})

    @property
    def identical(self) -> bool:
        """Report whether the policy reproduced the run exactly.

        Returns:
            True when nothing diverged.
        """
        return not self.diffs

    def summary(self) -> str:
        """Render a one-line verdict.

        Returns:
            Human-readable summary.
        """
        if self.identical:
            return (
                f"{self.iterations_replayed} decisions reproduced exactly "
                f"({self.iterations_skipped} had nothing to decide)"
            )
        # Counted in iterations, not fields: one changed branch shows up as a
        # divergence in the band, the selection and the top choice at once.
        rounds = len({d.iteration for d in self.diffs})
        return (
            f"{rounds} of {self.iterations_replayed} decisions diverged from "
            f"the recorded run ({len(self.diffs)} differing fields)"
        )


def _policy_from(record: dict[str, Any]) -> PolicyConfig:
    """Rebuild the thresholds a run used.

    Args:
        record: The trace's ``run_start`` record.

    Returns:
        The policy configuration, falling back to defaults for any setting
        the trace predates.
    """
    stored = (record.get("config") or {}).get("policy") or {}
    known = {f for f in PolicyConfig.__dataclass_fields__}
    return PolicyConfig(**{k: v for k, v in stored.items() if k in known})


def _costs_from(record: dict[str, Any]) -> dict[str, str]:
    """Recover each tool's cost class.

    Args:
        record: The trace's ``run_start`` record.

    Returns:
        Cost class keyed by tool name.
    """
    tools = (record.get("registry") or {}).get("tools") or []
    return {t["name"]: t.get("cost", "low") for t in tools if "name" in t}


def replay_trace(path: Path, config: PolicyConfig | None = None) -> ReplayReport:
    """Re-run the policy over a recorded trace and report any divergence.

    The decision model's answers are taken from the record, so the replay is
    deterministic and free. Only the policy is re-executed.

    Args:
        path: Trace file to replay.
        config: Thresholds to apply instead of the ones the run used, for
            asking what a different policy would have done.

    Returns:
        The comparison.

    Raises:
        ValueError: If the file holds no ``run_start`` record, which means it
            is not a trace.
    """
    records = read_trace(path)
    start = next((r for r in records if r.get("record") == "run_start"), None)
    if start is None:
        raise ValueError(f"{path} has no run_start record; it is not a trace")

    report = ReplayReport(
        path=path,
        run_id=str(start.get("run_id", "")),
        ticker=str(start.get("ticker", "")),
        config_source="caller" if config is not None else "trace",
    )
    policy = config if config is not None else _policy_from(start)
    costs = _costs_from(start)

    streak = 0
    veto_used = False
    tools_run: list[str] = []

    for record in records:
        if record.get("record") != "iteration":
            continue
        recorded = record.get("decision") or {}
        parsed = record.get("parsed") or {}

        if recorded.get("band") in _UNASKED or not parsed:
            report.iterations_skipped += 1
            _absorb(record, tools_run)
            continue

        response = record.get("jev_response") or {}
        # Replay has to re-decide exactly as the run did: the same ranking
        # map, the same gate, and the same act threshold for the scale that
        # ranking is on. Traces written before the comparative question carry
        # no "routing" key and no best_next map, so they replay off
        # usefulness at the absolute threshold as they always did.
        routing = parsed.get("routing") or "usefulness"
        ranking = parsed.get(routing) or {}
        gate = parsed.get("usefulness") or ranking
        replayed = decide(
            usefulness=gate,
            ranking=ranking,
            act_threshold=(
                policy.rank_act_threshold if routing == "best_next" else policy.act_threshold
            ),
            enough=parsed.get("enough"),
            conflict=parsed.get("conflict"),
            config=policy,
            indecision_streak=streak,
            tools_run=len(tools_run),
            costs={name: costs.get(name, "low") for name in ranking},
            conflict_veto_used=veto_used,
            jev_failed=bool(response.get("error")),
        )
        report.iterations_replayed += 1

        for name, was, now in (
            ("band", recorded.get("band"), replayed.band),
            ("selected", list(recorded.get("selected") or []), list(replayed.selected)),
            ("top1", recorded.get("top1"), replayed.top1),
        ):
            if was != now:
                report.diffs.append(IterationDiff(int(record.get("iteration", -1)), name, was, now))

        # Carried forward from the replayed decision, not the recorded one, so
        # a divergence propagates the way it would in a real run instead of
        # being quietly resynchronised each round.
        streak = replayed.indecision_streak
        veto_used = veto_used or replayed.stop_vetoed_by_conflict
        _absorb(record, tools_run)

    return report


def _absorb(record: dict[str, Any], tools_run: list[str]) -> None:
    """Account for the tools one iteration ran.

    Args:
        record: An ``iteration`` record.
        tools_run: Accumulator of distinct successful tools, mutated in place.
    """
    for call in record.get("tool_calls") or []:
        if call.get("status") == "ok" and call.get("tool") not in tools_run:
            tools_run.append(str(call["tool"]))
