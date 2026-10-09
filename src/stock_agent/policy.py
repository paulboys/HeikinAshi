"""Turning probabilities into actions.

The decision model's probabilities are known to be miscalibrated in a
set-dependent way, so nothing here treats one as a belief. The policy uses
only the *ranking* of candidates and a few fixed band crossings, and the
evaluation harness measures how sensitive the outcome is to where those bands
sit.

Two rules are deliberately the application's and not the model's:

* **A low-confidence stop never stops.** Sufficiency below the threshold
  continues the analysis rather than silently terminating it.
* **Sufficiency with contradiction does not stop either**, once. High
  sufficiency alongside high conflict is exactly the state in which stopping
  would be wrong.

:func:`decide` is pure, which is what lets every branch be tested directly.

Public API:
    Band, Decision, decide(...)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from stock_agent.config import PolicyConfig

__all__ = ["Band", "Decision", "decide"]

Band = Literal[
    "bootstrap",
    "act_clear",
    "act_tied",
    "consider",
    "indecisive",
    "stop_sufficient",
    "stop_no_useful_tool",
    "stop_repeated_indecision",
    "stop_nothing_available",
    "jev_unavailable",
]

# The margin is a subtraction, so two probabilities that differ by exactly
# the threshold can land a hair under it (0.90 - 0.80 = 0.0999...). Compare
# with a tolerance so a branch never turns on floating-point dust.
_EPS = 1e-9

_STOP_BANDS: frozenset[str] = frozenset(
    {
        "stop_sufficient",
        "stop_no_useful_tool",
        "stop_repeated_indecision",
        "stop_nothing_available",
        "jev_unavailable",
    }
)


@dataclass(frozen=True)
class Decision:
    """What the agent should do next, and why.

    Attributes:
        band: Which branch of the policy fired.
        selected: Tools to run this iteration, in order.
        top1: Highest-ranked candidate, if any.
        p_top1: Its usefulness probability.
        top2: Runner-up, if any.
        p_top2: Its usefulness probability.
        margin: Gap between the top two.
        indecision_streak: Consecutive indecisive iterations after this one.
        stop_vetoed_by_conflict: Whether a stop was blocked by contradiction.
        rationale: The arithmetic, in words, for the trace.
    """

    band: Band
    selected: tuple[str, ...] = ()
    top1: str | None = None
    p_top1: float | None = None
    top2: str | None = None
    p_top2: float | None = None
    margin: float | None = None
    indecision_streak: int = 0
    stop_vetoed_by_conflict: bool = False
    rationale: str = ""
    exit_reason: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def should_stop(self) -> bool:
        """Report whether this decision ends the run.

        Returns:
            True when the band is terminal.
        """
        return self.band in _STOP_BANDS


def decide(
    usefulness: Mapping[str, float],
    enough: float | None,
    conflict: float | None,
    config: PolicyConfig,
    indecision_streak: int,
    tools_run: int,
    costs: Mapping[str, str] | None = None,
    conflict_veto_used: bool = False,
    jev_failed: bool = False,
    ranking: Mapping[str, float] | None = None,
    act_threshold: float | None = None,
) -> Decision:
    """Choose the next action from one round of answers.

    Two questions are answered per round and each is read for what it can
    answer. The comparative question ranks the candidates -- which one wins
    -- and the absolute one gates the round -- whether anything is worth
    running at all. Reading a low "best of the field" probability as "nothing
    is useful" halted thirteen of thirty-three rounds in benchmark 4 while
    the absolute map never once fell below the floor.

    Passing only ``usefulness`` makes it both maps at the old threshold, so
    every arm that answers a single question behaves exactly as before.

    Args:
        usefulness: The gate. Probability per candidate that it would add
            information, used for the grey-band floor and for stopping when
            nothing clears it.
        enough: Probability the evidence already supports a conclusion.
        conflict: Probability the evidence contradicts itself.
        config: Thresholds.
        indecision_streak: Consecutive indecisive iterations so far.
        tools_run: Distinct tools that have run successfully.
        costs: Cost class per tool, used to break ties toward the cheap.
        conflict_veto_used: Whether a stop has already been vetoed once.
        jev_failed: Whether the decision request failed outright.
        ranking: Probability per candidate that it is the best next analysis.
            Orders the candidates and drives the act band. Defaults to
            ``usefulness``.
        act_threshold: The act band for the scale ``ranking`` is on. The
            threshold belongs to the question answered, not to the policy: an
            arm answering the absolute question keeps ``config.act_threshold``
            even when the policy is capable of reading a comparative map, and
            that is what keeps the mock arms' baselines intact. Defaults to
            ``config.act_threshold``.

    Returns:
        The decision, including the arithmetic that produced it.
    """
    order = usefulness if ranking is None else ranking
    act_at = config.act_threshold if act_threshold is None else act_threshold
    if jev_failed:
        return Decision(
            band="jev_unavailable",
            exit_reason="jev_error",
            rationale=(
                "the decision model returned no usable answers; reporting what "
                "has been measured rather than substituting another model"
            ),
        )

    if not order or not usefulness:
        return Decision(
            band="stop_nothing_available",
            exit_reason="no_candidates",
            rationale="no applicable analyses remain",
        )

    # Sufficiency is considered before selection: if the evidence is already
    # enough, the best next tool is no tool.
    if enough is not None and enough >= config.stop_threshold:
        if tools_run < config.min_tools_before_stop:
            note = (
                f"p(enough)={enough:.2f} met the threshold but only {tools_run} "
                f"analyses have run (minimum {config.min_tools_before_stop})"
            )
        elif conflict is not None and conflict >= config.conflict_veto and not conflict_veto_used:
            # Sufficiency plus contradiction is precisely where stopping is
            # wrong. Allowed once, so the veto itself cannot loop.
            note = (
                f"p(enough)={enough:.2f} met the threshold but p(conflict)="
                f"{conflict:.2f} indicates the evidence disagrees with itself"
            )
            return _select(
                order,
                usefulness,
                config,
                act_at,
                indecision_streak,
                costs,
                vetoed=True,
                extra_note=note,
            )
        else:
            return Decision(
                band="stop_sufficient",
                exit_reason="jev_sufficient",
                rationale=(
                    f"p(enough)={enough:.2f} >= {config.stop_threshold:.2f} with "
                    f"{tools_run} analyses run"
                ),
            )
        return _select(
            order,
            usefulness,
            config,
            act_at,
            indecision_streak,
            costs,
            extra_note=note,
        )

    return _select(order, usefulness, config, act_at, indecision_streak, costs)


def _rank(usefulness: Mapping[str, float]) -> list[tuple[str, float]]:
    """Order candidates by usefulness, breaking ties by name.

    Args:
        usefulness: Probability per candidate.

    Returns:
        Pairs sorted by descending probability.
    """
    return sorted(usefulness.items(), key=lambda kv: (-kv[1], kv[0]))


def _cheapest(
    names: Sequence[str],
    costs: Mapping[str, str] | None,
) -> str:
    """Pick the cheapest of several equally-ranked tools.

    Args:
        names: Candidate names.
        costs: Cost class per tool.

    Returns:
        The chosen name.
    """
    if not costs:
        return names[0]
    order = {"low": 0, "medium": 1, "high": 2}
    return min(names, key=lambda n: (order.get(costs.get(n, "medium"), 1), n))


def _select(
    ranking: Mapping[str, float],
    gate: Mapping[str, float],
    config: PolicyConfig,
    act_threshold: float,
    indecision_streak: int,
    costs: Mapping[str, str] | None,
    vetoed: bool = False,
    extra_note: str | None = None,
) -> Decision:
    """Choose which tools to run, ordering by one map and gating on another.

    When the two maps are the same object -- every single-question arm -- this
    reduces exactly to the behaviour before the split, because the gate's best
    score is then the top of the ranking.

    Args:
        ranking: Probability per candidate that it is the best next analysis.
            Sets the order, the margin and the act band.
        gate: Probability per candidate that it would add information. Only
            its best score is used, to decide whether the round is worth
            acting on at all.
        config: Thresholds.
        act_threshold: The act band on the scale ``ranking`` is measured on.
        indecision_streak: Consecutive indecisive iterations so far.
        costs: Cost class per tool.
        vetoed: Whether this selection follows a vetoed stop.
        extra_note: Additional context for the trace.

    Returns:
        The decision.
    """
    ranked = _rank(ranking)
    top1, p1 = ranked[0]
    top2, p2 = ranked[1] if len(ranked) > 1 else (None, None)
    margin = p1 if p2 is None else p1 - p2
    notes = (extra_note,) if extra_note else ()
    gate_best = max(gate.values()) if gate else p1

    if p1 >= act_threshold:
        if margin >= config.margin_min - _EPS or top2 is None:
            return Decision(
                band="act_clear",
                selected=(top1,),
                top1=top1,
                p_top1=p1,
                top2=top2,
                p_top2=p2,
                margin=margin,
                indecision_streak=0,
                stop_vetoed_by_conflict=vetoed,
                notes=notes,
                rationale=(
                    f"p({top1})={p1:.2f} >= act {act_threshold:.2f} and "
                    f"margin {margin:.2f} >= {config.margin_min:.2f}"
                ),
            )
        # Two strong candidates that cannot be separated. Running both is
        # cheaper than another round trip, and the batched questions already
        # gave independent evidence for each.
        selected = tuple([top1, top2][: config.max_corun])
        return Decision(
            band="act_tied",
            selected=selected,
            top1=top1,
            p_top1=p1,
            top2=top2,
            p_top2=p2,
            margin=margin,
            indecision_streak=0,
            stop_vetoed_by_conflict=vetoed,
            notes=notes,
            rationale=(
                f"p({top1})={p1:.2f} and p({top2})={p2:.2f} both clear act "
                f"{act_threshold:.2f} within margin {config.margin_min:.2f}; "
                f"running both"
            ),
        )

    if gate_best >= config.consider_threshold:
        if margin >= config.margin_min - _EPS or top2 is None:
            return Decision(
                band="consider",
                selected=(top1,),
                top1=top1,
                p_top1=p1,
                top2=top2,
                p_top2=p2,
                margin=margin,
                indecision_streak=0,
                stop_vetoed_by_conflict=vetoed,
                notes=notes,
                rationale=(
                    f"p({top1})={p1:.2f} in the grey band "
                    f"[{config.consider_threshold:.2f}, {act_threshold:.2f}) "
                    f"with a clear margin"
                ),
            )
        streak = indecision_streak + 1
        if streak >= config.indecision_limit:
            return Decision(
                band="stop_repeated_indecision",
                top1=top1,
                p_top1=p1,
                top2=top2,
                p_top2=p2,
                margin=margin,
                indecision_streak=streak,
                stop_vetoed_by_conflict=vetoed,
                notes=notes,
                exit_reason="repeated_indecision",
                rationale=(
                    f"{streak} consecutive iterations with no candidate clearly "
                    f"preferred (limit {config.indecision_limit})"
                ),
            )
        # Still run something: an indecisive iteration that does nothing
        # wastes a round trip and cannot change the state it is stuck on.
        # Viability is the gate's question; the order among viable
        # candidates is the ranking's.
        viable = [n for n, _ in ranked if gate.get(n, p1) >= config.consider_threshold]
        pick = _cheapest(viable or [top1], costs)
        return Decision(
            band="indecisive",
            selected=(pick,),
            top1=top1,
            p_top1=p1,
            top2=top2,
            p_top2=p2,
            margin=margin,
            indecision_streak=streak,
            stop_vetoed_by_conflict=vetoed,
            notes=notes,
            rationale=(
                f"no clear preference (margin {margin:.2f} < "
                f"{config.margin_min:.2f}); running the cheapest viable "
                f"candidate {pick!r}"
            ),
        )

    return Decision(
        band="stop_no_useful_tool",
        top1=top1,
        p_top1=p1,
        top2=top2,
        p_top2=p2,
        margin=margin,
        indecision_streak=indecision_streak,
        stop_vetoed_by_conflict=vetoed,
        notes=notes,
        exit_reason="no_useful_tool",
        rationale=(
            f"no candidate clears the grey band: the best usefulness score "
            f"is {gate_best:.2f}, below consider "
            f"{config.consider_threshold:.2f}; nothing remaining would add "
            f"information (top of the ranking was {top1!r} at {p1:.2f})"
        ),
    )
