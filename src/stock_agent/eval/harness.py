"""Running every arm against every scenario, and reporting the difference.

The benchmark runs in two regimes, because they answer different questions.

**Unbudgeted** -- nothing is capped. Here an arm that simply runs every
applicable analysis covers every expectation, so coverage says little and the
informative numbers are precision, redundancy, rounds taken and cost.

**Budgeted** -- the tool-call cap is tightened until an arm cannot run
everything. This is where routing is the whole game: with room for only a few
analyses, covering what matters requires choosing it. Coverage under a budget
is the headline metric, and it is the one the preregistration commits to.

Every arm shares the registry, the chokepoint, the policy, the guards and the
trace. The only thing that differs is how usefulness is scored.

Public API:
    ArmResult, BenchReport, run_arm, run_benchmark, validate_metrics
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stock_agent.asof import FrameProvider
from stock_agent.config import AgentConfig, BudgetConfig
from stock_agent.eval.baseline_rules import build_arm
from stock_agent.eval.metrics import (
    Calibration,
    PairedDelta,
    PairPreference,
    RunScore,
    calibrate,
    ndcg_at_k,
    pair_preference,
    paired_bootstrap,
    score_run,
)
from stock_agent.eval.scenarios import SCENARIOS, Scenario
from stock_agent.loop import DecisionModel, run_analysis
from stock_agent.tools.builtin import build_registry
from stock_agent.trace import read_trace

__all__ = [
    "ArmResult",
    "BenchReport",
    "calibration_items",
    "run_arm",
    "run_benchmark",
    "validate_metrics",
]

TICKER = "SYN"
OBJECTIVE = "whether this is a swing-trade entry"

# Tight enough that no arm can run every applicable analysis, so coverage has
# to be earned by choosing rather than by exhausting the menu.
BUDGETED_TOOL_CALLS = 4

# Headline claims the preregistration commits to, checked by validate_metrics
# before any of this is pointed at a real decision model.
ORACLE_FLOOR = 0.90
RANDOM_CEILING = 0.75


@dataclass(frozen=True)
class ArmResult:
    """One arm's run on one scenario.

    Attributes:
        score: The routing and cost metrics.
        ndcg: Mean nDCG over the rounds where a ranking was produced.
        usefulness_items: Labelled probabilities for the usefulness
            questions, for calibration.
        enough_items: Labelled probabilities for the sufficiency question.
        pivotal_score: The highest probability the arm gave the scenario's
            pivotal analysis, or None if it was never offered one. This is
            what makes a within-pair comparison possible.
        trace_path: Where the decision trace was written.
        error: What went wrong, when a run failed outright.
    """

    score: RunScore
    ndcg: float
    usefulness_items: tuple[tuple[int, float], ...]
    enough_items: tuple[tuple[int, float], ...]
    pivotal_score: float | None
    trace_path: Path | None
    error: str | None = None


@dataclass
class BenchReport:
    """Everything one benchmark produced.

    Attributes:
        regime: Which regime was run.
        results: Every arm-scenario result.
        calibrations: Calibration per arm, over usefulness and sufficiency.
        deltas: Paired comparisons against the reference arm.
        preferences: Per-arm within-pair comparison of the pivotal analysis.
        reference: The arm everything is compared against.
        scenario_failures: Scenarios whose planted feature did not verify.
    """

    regime: str
    results: list[ArmResult] = field(default_factory=list)
    calibrations: dict[str, list[Calibration]] = field(default_factory=dict)
    deltas: list[PairedDelta] = field(default_factory=list)
    preferences: list[PairPreference] = field(default_factory=list)
    reference: str = "rules"
    scenario_failures: list[tuple[str, str]] = field(default_factory=list)

    def arms(self) -> list[str]:
        """List the arms that ran.

        Returns:
            Arm names in first-seen order.
        """
        seen: list[str] = []
        for result in self.results:
            if result.score.arm not in seen:
                seen.append(result.score.arm)
        return seen

    def for_arm(self, arm: str) -> list[ArmResult]:
        """Select one arm's results.

        Args:
            arm: Arm name.

        Returns:
            Its results, in scenario order.
        """
        return [r for r in self.results if r.score.arm == arm]

    def mean(self, arm: str, metric: str) -> float:
        """Average one metric over an arm's scenarios.

        Args:
            arm: Arm name.
            metric: Field name on the score, or ``ndcg``.

        Returns:
            The mean over the scenarios where the metric is defined, or NaN
            when it is defined nowhere. Undefined values are skipped rather
            than treated as zero or one, either of which would let the nine
            scenarios that expect nothing dominate the average.
        """
        values: list[float] = []
        for result in self.for_arm(arm):
            raw = result.ndcg if metric == "ndcg" else getattr(result.score, metric)
            if isinstance(raw, bool):
                values.append(float(raw))
            elif isinstance(raw, (int, float)) and not math.isnan(float(raw)):
                values.append(float(raw))
        return sum(values) / len(values) if values else float("nan")

    def to_dict(self) -> dict[str, Any]:
        """Render the report.

        Returns:
            A JSON-safe mapping.
        """
        return {
            "regime": self.regime,
            "reference": self.reference,
            "scenario_failures": [{"scenario": s, "detail": d} for s, d in self.scenario_failures],
            "runs": [
                {**r.score.to_dict(), "ndcg": round(r.ndcg, 4), "error": r.error}
                for r in self.results
            ],
            "summary": {
                arm: {
                    metric: round(self.mean(arm, metric), 4)
                    for metric in (
                        "required_coverage",
                        "precision",
                        "ndcg",
                        "forbidden_hits",
                        "redundant_calls",
                        "tools_run",
                        "jev_calls",
                        "wall_s",
                    )
                }
                for arm in self.arms()
            },
            "calibration": {
                arm: [c.to_dict() for c in rows] for arm, rows in self.calibrations.items()
            },
            "deltas": [d.to_dict() for d in self.deltas],
            "pair_preference": [p.to_dict() for p in self.preferences],
        }


def _config(regime: str) -> AgentConfig:
    """Build the configuration for a regime.

    Args:
        regime: ``free`` or ``budgeted``.

    Returns:
        The configuration.

    Raises:
        ValueError: If the regime is unknown.
    """
    if regime == "free":
        return AgentConfig()
    if regime == "budgeted":
        return AgentConfig(budget=BudgetConfig(max_tool_calls=BUDGETED_TOOL_CALLS))
    raise ValueError(f"unknown regime {regime!r}; expected 'free' or 'budgeted'")


def _rounds_from_trace(records: Sequence[dict[str, Any]]) -> list[list[str]]:
    """Recover which analyses ran in each decision round.

    Args:
        records: Trace records.

    Returns:
        Tool names per round, in order.
    """
    return [
        [c["tool"] for c in record.get("tool_calls") or [] if c.get("status") == "ok"]
        for record in records
        if record.get("record") == "iteration"
    ]


def calibration_items(
    records: Sequence[dict[str, Any]],
    scenario: Scenario,
) -> tuple[
    list[tuple[int, float]],
    list[tuple[int, float]],
    list[float],
    float | None,
]:
    """Extract labelled probabilities and per-round rankings from a trace.

    A usefulness answer counts as correct when the analysis it scored is one
    the scenario expects. A sufficiency answer counts as correct when every
    expected analysis had already run, so stopping would have lost nothing --
    which is the only definition under which "is this enough" has a knowable
    answer.

    Args:
        records: Trace records.
        scenario: The scenario being scored.

    Returns:
        Usefulness items, sufficiency items, one nDCG per round, and the
        highest score given to the analysis this scenario's pair turns on.
    """
    usefulness: list[tuple[int, float]] = []
    enough: list[tuple[int, float]] = []
    ndcgs: list[float] = []
    measured: set[str] = set()
    pivotal_scores: list[float] = []

    for record in records:
        if record.get("record") != "iteration":
            continue
        parsed = record.get("parsed") or {}
        # Score the map the run actually routed on. nDCG, the pivotal score
        # and the calibration items are all claims about the signal that
        # chose the tools, so reading the absolute map once routing moved to
        # the comparative one would quietly measure a question the policy no
        # longer consults. Traces written before that question carry no
        # "routing" key and are read exactly as they were.
        scores = parsed.get(parsed.get("routing") or "usefulness") or {}

        if scores:
            for tool, probability in scores.items():
                usefulness.append((int(tool in scenario.required), float(probability)))
            if scenario.pivotal_probe in scores:
                pivotal_scores.append(float(scores[scenario.pivotal_probe]))
            # Judged per round, on the menu actually offered. Once the
            # expected analyses have run they leave the menu, and a round
            # with nothing relevant on it has no ideal ranking to normalise
            # against -- scoring those rounds zero was dragging every arm
            # toward the same middling number and hiding the difference.
            ranked = sorted(scores, key=lambda t: -scores[t])
            relevance = scenario.relevance(ranked)
            if any(relevance):
                ndcgs.append(ndcg_at_k(relevance))

        if parsed.get("enough") is not None:
            covered = bool(scenario.required) and scenario.required <= measured
            enough.append((int(covered), float(parsed["enough"])))

        for call in record.get("tool_calls") or []:
            if call.get("status") == "ok":
                measured.add(str(call["tool"]))

    best = max(pivotal_scores) if pivotal_scores else None
    return usefulness, enough, ndcgs, best


def run_arm(
    arm: str,
    scenario: Scenario,
    regime: str = "free",
    trace_dir: Path | None = None,
    model: DecisionModel | None = None,
    seed: int = 0,
) -> ArmResult:
    """Run one arm against one scenario.

    Args:
        arm: Arm name, used for reporting and to build the default model.
        scenario: The situation to analyse.
        regime: ``free`` or ``budgeted``.
        trace_dir: Where to write the decision trace; a temporary file is
            used when omitted, since the trace is how the rankings are
            recovered.
        model: An explicit decision model, for the live arm.
        seed: Seed for the random arm.

    Returns:
        The result, carrying an error rather than raising if the run fails.
    """
    import tempfile

    # Resolved before the try block below. A mistyped regime is a mistake in
    # how the benchmark was invoked, not a failure of the arm, and recording
    # it as one would quietly turn every scenario into an error row.
    config = _config(regime)

    frames = scenario.build()
    decider = model if model is not None else build_arm(arm, scenario, seed)

    if trace_dir is not None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_path = trace_dir / f"{arm}__{scenario.name}.jsonl"
        temporary = None
    else:
        temporary = tempfile.TemporaryDirectory()
        trace_path = Path(temporary.name) / f"{arm}__{scenario.name}.jsonl"

    # A live client is built once and shared across every scenario, so its
    # ``calls`` counter is cumulative. Reading it directly reports the running
    # total rather than this scenario's cost -- it put the jev arm at 14.73
    # mean calls in benchmark 3 when every scenario had in fact made one or
    # two. Mock arms were unaffected, being rebuilt per scenario, which is
    # exactly what made the inflated number look plausible.
    calls_before = getattr(decider, "calls", 0)
    started = time.perf_counter()
    error: str | None = None
    try:
        run = run_analysis(
            ticker=TICKER,
            objective=OBJECTIVE,
            registry=build_registry(),
            model=decider,
            provider=FrameProvider(frames),
            config=config,
            trace_path=trace_path,
        )
        records = read_trace(trace_path)
        tools_run = run.tools_run
        exit_reason, partial = run.exit_reason, run.partial
        history = run.state.history
        tool_calls = len(history)
        network = sum(c.get("network_calls", 0) for r in records for c in r.get("tool_calls") or [])
        latency = sum((r.get("jev_response") or {}).get("latency_s") or 0.0 for r in records)
    except Exception as exc:  # noqa: BLE001 - one bad arm must not end the benchmark
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
        records, tools_run, tool_calls, network, latency = [], [], 0, 0, 0.0
        exit_reason, partial = "harness_error", True
    wall = time.perf_counter() - started

    usefulness, enough, ndcgs, pivotal_score = calibration_items(records, scenario)
    result = ArmResult(
        score=score_run(
            scenario_name=scenario.name,
            arm=arm,
            required=scenario.required,
            forbidden=scenario.forbidden,
            pivotal=scenario.pivotal,
            tools_run=tools_run,
            per_round=_rounds_from_trace(records),
            tool_calls=tool_calls,
            jev_calls=getattr(decider, "calls", 0) - calls_before,
            network_calls=network,
            latency_s=latency,
            wall_s=wall,
            exit_reason=exit_reason,
            partial=partial,
        ),
        ndcg=sum(ndcgs) / len(ndcgs) if ndcgs else float("nan"),
        usefulness_items=tuple(usefulness),
        enough_items=tuple(enough),
        pivotal_score=pivotal_score,
        trace_path=trace_path if trace_dir is not None else None,
        error=error,
    )
    if temporary is not None:
        temporary.cleanup()
    return result


def run_benchmark(
    arms: Sequence[str] = ("rules", "cheapest", "random", "oracle"),
    scenarios: Sequence[Scenario] = SCENARIOS,
    regime: str = "free",
    reference: str = "rules",
    trace_dir: Path | None = None,
    models: dict[str, DecisionModel] | None = None,
    seed: int = 0,
    verify: bool = True,
    overwrite_traces: bool = False,
) -> BenchReport:
    """Run every arm against every scenario and compare them.

    Args:
        arms: Arm names to run.
        scenarios: Situations to run them against.
        regime: ``free`` or ``budgeted``.
        reference: The arm the others are compared against.
        trace_dir: Where to keep traces; discarded when omitted.
        models: Explicit decision models by arm name, for the live arm.
        seed: Seed for the random arm.
        verify: Confirm each scenario's planted feature first. A scenario that
            does not verify is still run, but is reported as unverified --
            silently benchmarking against a mislabelled situation would make
            every arm identically and invisibly wrong.
        overwrite_traces: Permit writing into a directory that already holds
            traces. Off by default because those traces are the only record
            of a paid run.

    Returns:
        The report.

    Raises:
        FileExistsError: If ``trace_dir`` already holds traces and
            ``overwrite_traces`` is not set.
    """
    # Benchmark 3's traces were destroyed by a later run pointed at the same
    # directory, and since runs/ is not committed there was nothing to
    # recover from. A paid run's traces are the only evidence it happened.
    if trace_dir is not None and not overwrite_traces:
        existing = sorted(Path(trace_dir).glob("*.jsonl")) if Path(trace_dir).is_dir() else []
        if existing:
            raise FileExistsError(
                f"{trace_dir} already holds {len(existing)} trace(s), the only "
                f"record of whichever run produced them. Write to a new "
                f"directory, or pass overwrite_traces=True "
                f"(--overwrite-traces) to replace them."
            )

    report = BenchReport(regime=regime, reference=reference)

    if verify:
        for scenario in scenarios:
            ok, detail = scenario.verify()
            if not ok:
                report.scenario_failures.append((scenario.name, detail))

    for arm in arms:
        for scenario in scenarios:
            report.results.append(
                run_arm(
                    arm,
                    scenario,
                    regime,
                    trace_dir,
                    model=(models or {}).get(arm),
                    seed=seed,
                )
            )

    for arm in report.arms():
        rows = report.for_arm(arm)
        report.calibrations[arm] = [
            calibrate(
                f"{arm}: usefulness",
                [i for r in rows for i in r.usefulness_items],
            ),
            calibrate(
                f"{arm}: sufficiency",
                [i for r in rows for i in r.enough_items],
            ),
        ]

    from stock_agent.eval.scenarios import pairs as scenario_pairs

    ran = {s.name for s in scenarios}
    for arm in report.arms():
        scored = {r.score.scenario: r for r in report.for_arm(arm)}
        by_pair: dict[str, tuple[str, float | None, float | None]] = {}
        for pair, halves in scenario_pairs().items():
            present = next((h for h in halves if h.half == "present"), None)
            absent = next((h for h in halves if h.half == "absent"), None)
            if present is None or absent is None:
                continue
            if present.name not in ran or absent.name not in ran:
                continue
            by_pair[pair] = (
                str(present.pivotal),
                scored[present.name].pivotal_score if present.name in scored else None,
                scored[absent.name].pivotal_score if absent.name in scored else None,
            )
        if by_pair:
            report.preferences.append(pair_preference(arm, by_pair))

    for arm in report.arms():
        if arm == reference:
            continue
        for metric in ("required_coverage", "precision", "ndcg", "tool_calls"):
            paired = {
                r.score.scenario: (
                    _metric_of(r, metric),
                    _metric_of(other, metric),
                )
                for r in report.for_arm(arm)
                for other in report.for_arm(reference)
                if other.score.scenario == r.score.scenario
            }
            report.deltas.append(paired_bootstrap(metric, arm, reference, paired))

    return report


def _metric_of(result: ArmResult, metric: str) -> float:
    """Read one metric off a result.

    Args:
        result: The result to read.
        metric: Field name on the score, or ``ndcg``.

    Returns:
        The value as a float.
    """
    if metric == "ndcg":
        return result.ndcg
    raw = getattr(result.score, metric)
    return float(raw) if isinstance(raw, (int, float)) else float("nan")


def validate_metrics(regime: str = "budgeted", seed: int = 0) -> dict[str, Any]:
    """Check the metrics can tell good routing from bad before trusting them.

    An oracle that knows the answer must score near the top, and seeded
    random choices must not. If that separation fails, the metrics are not
    measuring routing and no comparison built on them means anything --
    including a favourable one.

    Args:
        regime: Which regime to validate in; the budgeted one, since that is
            where coverage has to be earned.
        seed: Seed for the random arm.

    Returns:
        The two arms' mean coverage, the thresholds, and whether it passed.
    """
    report = run_benchmark(
        arms=("oracle", "random"),
        regime=regime,
        reference="random",
        seed=seed,
        verify=False,
    )
    oracle = report.mean("oracle", "required_coverage")
    chance = report.mean("random", "required_coverage")
    return {
        "regime": regime,
        "oracle_coverage": round(oracle, 4),
        "random_coverage": round(chance, 4),
        "oracle_floor": ORACLE_FLOOR,
        "random_ceiling": RANDOM_CEILING,
        "separated": bool(oracle >= ORACLE_FLOOR and chance <= RANDOM_CEILING),
        "oracle_ndcg": round(report.mean("oracle", "ndcg"), 4),
        "random_ndcg": round(report.mean("random", "ndcg"), 4),
    }
