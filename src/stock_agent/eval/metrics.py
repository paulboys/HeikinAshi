"""How a run is scored, and how two arms are compared.

Two families live here.

**Routing metrics** judge one run against a scenario's declared expectations.
Coverage alone is not enough: an arm that simply runs everything covers every
expectation, which is why precision, the number of rounds taken, redundancy
and wasted work are reported beside it, and why the benchmark also runs under
a tool budget. Under a budget, choosing well is the only way to cover.

**Calibration metrics** judge the probabilities themselves. The arithmetic is
carried over unchanged from the Latin work's ``jev_calibration.py`` -- the
same Mann-Whitney tie handling, the same bootstrap size and seed, the same
ten reliability bins -- so numbers from the two projects are comparable. That
matters more than elegance here: a reimplementation that rounded differently
would silently break the comparison.

Nothing here knows about any particular arm.

Public API:
    RunScore, score_run(...)
    auc, boot_auc, brier, reliability, ece, Calibration, calibrate
    ndcg_at_k, paired_bootstrap, PairedDelta
    pair_preference, PairPreference
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

__all__ = [
    "Calibration",
    "PairPreference",
    "PairedDelta",
    "RunScore",
    "auc",
    "boot_auc",
    "brier",
    "calibrate",
    "ece",
    "ndcg_at_k",
    "pair_preference",
    "paired_bootstrap",
    "reliability",
    "score_run",
]

# Carried over unchanged so results stay comparable with the earlier work.
BOOT_N = 2000
BOOT_SEED = 7
RELIABILITY_BINS = 10


# --- routing ----------------------------------------------------------------


@dataclass(frozen=True)
class RunScore:
    """How well one run routed.

    Attributes:
        scenario: Scenario name.
        arm: Arm name.
        required_coverage: Fraction of expected analyses that ran. One means
            nothing the scenario contains was overlooked.
        precision: Fraction of the analyses run that were expected. Low means
            effort went elsewhere; an arm that runs everything scores badly
            here however complete its coverage.
        forbidden_hits: Count of analyses the scenario marked as wasted.
        steps_to_coverage: Decision rounds taken before coverage was complete,
            or None if it never was.
        redundant_calls: Tool executions beyond one per distinct analysis.
        pivotal_found: Whether the analysis the scenario turns on was run.
            This is the single most informative field for a minimal pair.
        tools_run: How many distinct analyses produced measurements.
        tool_calls: Total executions, successful or not.
        jev_calls: Requests made to the decision model.
        network_calls: Outbound calls.
        latency_s: Time spent waiting on the decision model.
        wall_s: Total wall-clock time.
        exit_reason: Why the run stopped.
        partial: Whether it was cut short.
    """

    scenario: str
    arm: str
    required_coverage: float
    precision: float
    forbidden_hits: int
    steps_to_coverage: int | None
    redundant_calls: int
    pivotal_found: bool | None
    tools_run: int
    tool_calls: int
    jev_calls: int
    network_calls: int
    latency_s: float
    wall_s: float
    exit_reason: str
    partial: bool

    def to_dict(self) -> dict[str, object]:
        """Render the score for a report or a JSON dump.

        Returns:
            A JSON-safe mapping.
        """
        return {
            "scenario": self.scenario,
            "arm": self.arm,
            "required_coverage": round(self.required_coverage, 4),
            "precision": round(self.precision, 4),
            "forbidden_hits": self.forbidden_hits,
            "steps_to_coverage": self.steps_to_coverage,
            "redundant_calls": self.redundant_calls,
            "pivotal_found": self.pivotal_found,
            "tools_run": self.tools_run,
            "tool_calls": self.tool_calls,
            "jev_calls": self.jev_calls,
            "network_calls": self.network_calls,
            "latency_s": round(self.latency_s, 4),
            "wall_s": round(self.wall_s, 4),
            "exit_reason": self.exit_reason,
            "partial": self.partial,
        }


def score_run(
    scenario_name: str,
    arm: str,
    required: frozenset[str],
    forbidden: frozenset[str],
    pivotal: str | None,
    tools_run: Sequence[str],
    per_round: Sequence[Sequence[str]],
    tool_calls: int,
    jev_calls: int,
    network_calls: int,
    latency_s: float,
    wall_s: float,
    exit_reason: str,
    partial: bool,
) -> RunScore:
    """Score one run against a scenario's expectations.

    Args:
        scenario_name: Scenario name.
        arm: Arm name.
        required: Analyses the scenario expects.
        forbidden: Analyses the scenario counts as wasted.
        pivotal: The analysis the scenario turns on, if any.
        tools_run: Distinct analyses that produced measurements, in order.
        per_round: Tools that ran in each decision round, in order.
        tool_calls: Total executions.
        jev_calls: Requests to the decision model.
        network_calls: Outbound calls.
        latency_s: Time waiting on the decision model.
        wall_s: Total wall-clock time.
        exit_reason: Why it stopped.
        partial: Whether it was cut short.

    Returns:
        The score. Coverage and precision are NaN for a scenario that expects
        nothing: there was nothing to overlook and nothing to be precise
        about, so reporting a number would be worse than reporting none.
        Averaging those scenarios in was a real defect -- it handed every arm
        a free perfect score on the nine scenarios with no expectations, and
        made a random router look competent. Effort on those scenarios is
        judged by ``tools_run``, ``forbidden_hits`` and ``redundant_calls``.
    """
    ran = set(tools_run)
    hit = required & ran

    if required:
        coverage = len(hit) / len(required)
        precision = len(hit) / len(ran) if ran else 0.0
    else:
        coverage = float("nan")
        precision = float("nan")

    steps: int | None = None
    if required:
        seen: set[str] = set()
        for index, round_tools in enumerate(per_round, start=1):
            seen |= set(round_tools)
            if required <= seen:
                steps = index
                break

    return RunScore(
        scenario=scenario_name,
        arm=arm,
        required_coverage=coverage,
        precision=precision,
        forbidden_hits=len(forbidden & ran),
        steps_to_coverage=steps,
        redundant_calls=max(0, tool_calls - len(ran)),
        pivotal_found=None if pivotal is None else pivotal in ran,
        tools_run=len(ran),
        tool_calls=tool_calls,
        jev_calls=jev_calls,
        network_calls=network_calls,
        latency_s=latency_s,
        wall_s=wall_s,
        exit_reason=exit_reason,
        partial=partial,
    )


def ndcg_at_k(ranked: Sequence[float], k: int | None = None) -> float:
    """Normalised discounted cumulative gain over a ranking.

    The one metric that reads a whole probability vector rather than just its
    argmax, so it is the only one that notices an arm ranking the right
    analysis second instead of first.

    Args:
        ranked: Relevance values in the order the arm ranked them.
        k: Cut-off; the whole ranking when omitted.

    Returns:
        A value in [0, 1], or 0.0 when nothing is relevant.
    """
    cut = len(ranked) if k is None else min(k, len(ranked))
    if cut == 0:
        return 0.0

    def dcg(values: Sequence[float]) -> float:
        return sum((2.0**v - 1.0) / math.log2(i + 2.0) for i, v in enumerate(values[:cut]))

    ideal = dcg(sorted(ranked, reverse=True))
    return 0.0 if ideal <= 0 else dcg(ranked) / ideal


# --- calibration ------------------------------------------------------------


def auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """Probability a positive scores above a negative, ties counting a half.

    Args:
        pos: Scores given to positives.
        neg: Scores given to negatives.

    Returns:
        The Mann-Whitney statistic, or NaN when either side is empty.
    """
    if not pos or not neg:
        return float("nan")
    total = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return total / (len(pos) * len(neg))


def boot_auc(
    pos: Sequence[float],
    neg: Sequence[float],
    n: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> tuple[float, float]:
    """Bootstrap a 95% interval for the AUC.

    Args:
        pos: Scores given to positives.
        neg: Scores given to negatives.
        n: Resamples.
        seed: Seed, fixed so the interval is reproducible.

    Returns:
        The lower and upper bounds, or NaNs when either side is empty.
    """
    if not pos or not neg:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    values = sorted(
        auc([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]) for _ in range(n)
    )
    return values[int(0.025 * n)], values[int(0.975 * n) - 1]


def brier(labels: Sequence[int], probs: Sequence[float]) -> tuple[float, float, float]:
    """Mean squared error, against a forecaster that always says the base rate.

    Args:
        labels: Outcomes, zero or one.
        probs: Predicted probabilities.

    Returns:
        The Brier score, the base-rate forecaster's score, and the skill
        score, where zero means no better than the base rate.
    """
    n = len(labels)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    base = sum(labels) / n
    score = sum((p - y) ** 2 for y, p in zip(labels, probs, strict=True)) / n
    reference = sum((base - y) ** 2 for y in labels) / n
    skill = float("nan") if reference == 0 else 1.0 - score / reference
    return score, reference, skill


def reliability(
    labels: Sequence[int],
    probs: Sequence[float],
    bins: int = RELIABILITY_BINS,
) -> list[dict[str, float]]:
    """Group predictions into bins and compare claimed with observed rates.

    Args:
        labels: Outcomes, zero or one.
        probs: Predicted probabilities.
        bins: Number of equal-width bins.

    Returns:
        One row per non-empty bin, with its edges, size, mean prediction and
        observed rate.
    """
    rows: list[dict[str, float]] = []
    width = 1.0 / bins
    for index in range(bins):
        low = index * width
        high = low + width
        members = [
            (y, p)
            for y, p in zip(labels, probs, strict=True)
            if low <= p < high or (index == bins - 1 and p == 1.0)
        ]
        if not members:
            continue
        rows.append(
            {
                "low": low,
                "high": high,
                "n": float(len(members)),
                "mean_p": sum(p for _, p in members) / len(members),
                "observed": sum(y for y, _ in members) / len(members),
            }
        )
    return rows


def ece(labels: Sequence[int], probs: Sequence[float], bins: int = RELIABILITY_BINS) -> float:
    """Expected calibration error.

    Args:
        labels: Outcomes, zero or one.
        probs: Predicted probabilities.
        bins: Number of equal-width bins.

    Returns:
        The size-weighted mean gap between claimed and observed rates.
    """
    n = len(labels)
    if n == 0:
        return float("nan")
    return sum(
        row["n"] / n * abs(row["mean_p"] - row["observed"])
        for row in reliability(labels, probs, bins)
    )


@dataclass(frozen=True)
class Calibration:
    """Whether a set of probabilities means anything.

    Attributes:
        name: What was scored.
        n: Predictions made.
        positives: How many were positive.
        base_rate: Positive rate.
        mean_p_positive: Mean probability given to positives.
        mean_p_negative: Mean probability given to negatives.
        roc_auc: Discrimination; 0.5 is chance.
        auc_ci: Bootstrap 95% interval for the AUC.
        brier: Mean squared error.
        brier_base: The base-rate forecaster's error.
        skill: Brier skill score; zero means no better than the base rate.
        ece: Expected calibration error.
        bins: Reliability table.
    """

    name: str
    n: int
    positives: int
    base_rate: float
    mean_p_positive: float
    mean_p_negative: float
    roc_auc: float
    auc_ci: tuple[float, float]
    brier: float
    brier_base: float
    skill: float
    ece: float
    bins: list[dict[str, float]] = field(default_factory=list)

    @property
    def discriminates(self) -> bool:
        """Report whether the interval excludes chance.

        Returns:
            True when the whole bootstrap interval sits above 0.5.
        """
        low, _ = self.auc_ci
        return not math.isnan(low) and low > 0.5

    def to_dict(self) -> dict[str, object]:
        """Render the result for a report or a JSON dump.

        Returns:
            A JSON-safe mapping.
        """
        return {
            "name": self.name,
            "n": self.n,
            "positives": self.positives,
            "base_rate": round(self.base_rate, 4),
            "mean_p_positive": round(self.mean_p_positive, 4),
            "mean_p_negative": round(self.mean_p_negative, 4),
            "roc_auc": round(self.roc_auc, 4),
            "auc_ci": [round(v, 4) for v in self.auc_ci],
            "brier": round(self.brier, 4),
            "brier_base": round(self.brier_base, 4),
            "skill": round(self.skill, 4),
            "ece": round(self.ece, 4),
            "discriminates": self.discriminates,
            "bins": self.bins,
        }


def calibrate(name: str, items: Sequence[tuple[int, float]]) -> Calibration:
    """Score a set of labelled probabilities.

    Args:
        name: What is being scored, for the report.
        items: Pairs of outcome and predicted probability.

    Returns:
        The full calibration picture. An empty or single-class set yields NaNs
        rather than raising: a benchmark should report that it could not
        measure something, not fall over.
    """
    labels = [y for y, _ in items]
    probs = [p for _, p in items]
    n = len(items)
    positives = sum(labels)
    pos = [p for y, p in items if y]
    neg = [p for y, p in items if not y]
    score, reference, skill = brier(labels, probs)

    return Calibration(
        name=name,
        n=n,
        positives=positives,
        base_rate=positives / n if n else float("nan"),
        mean_p_positive=sum(pos) / len(pos) if pos else float("nan"),
        mean_p_negative=sum(neg) / len(neg) if neg else float("nan"),
        roc_auc=auc(pos, neg),
        auc_ci=boot_auc(pos, neg),
        brier=score,
        brier_base=reference,
        skill=skill,
        ece=ece(labels, probs),
        bins=reliability(labels, probs),
    )


# --- comparing two arms -----------------------------------------------------


@dataclass(frozen=True)
class PairedDelta:
    """The difference between two arms on the same scenarios.

    Attributes:
        metric: What was compared.
        left: Name of the first arm.
        right: Name of the second arm.
        mean_left: Its mean.
        mean_right: The other's mean.
        delta: Mean of the per-scenario differences, left minus right.
        ci: Bootstrap 95% interval for that difference.
        n_pairs: Scenarios compared.
    """

    metric: str
    left: str
    right: str
    mean_left: float
    mean_right: float
    delta: float
    ci: tuple[float, float]
    n_pairs: int

    @property
    def significant(self) -> bool:
        """Report whether the interval excludes zero.

        Returns:
            True when both bounds share a sign.
        """
        low, high = self.ci
        if math.isnan(low) or math.isnan(high):
            return False
        return (low > 0.0) == (high > 0.0)

    def to_dict(self) -> dict[str, object]:
        """Render the comparison.

        Returns:
            A JSON-safe mapping.
        """
        return {
            "metric": self.metric,
            "left": self.left,
            "right": self.right,
            "mean_left": round(self.mean_left, 4),
            "mean_right": round(self.mean_right, 4),
            "delta": round(self.delta, 4),
            "ci": [round(v, 4) for v in self.ci],
            "n_pairs": self.n_pairs,
            "significant": self.significant,
        }


def paired_bootstrap(
    metric: str,
    left: str,
    right: str,
    by_scenario: Mapping[str, tuple[float, float]],
    n: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> PairedDelta:
    """Compare two arms scenario by scenario.

    Paired because the arms face the same situations: comparing unpaired means
    would throw away the pairing and widen the interval for no reason.

    Args:
        metric: What is being compared.
        left: First arm's name.
        right: Second arm's name.
        by_scenario: Scenario name to its (left, right) values.
        n: Resamples.
        seed: Seed, fixed so the interval is reproducible.

    Returns:
        The difference and its interval.
    """
    rows = [(a, b) for a, b in by_scenario.values() if not (math.isnan(a) or math.isnan(b))]
    if not rows:
        return PairedDelta(
            metric,
            left,
            right,
            float("nan"),
            float("nan"),
            float("nan"),
            (float("nan"), float("nan")),
            0,
        )

    diffs = [a - b for a, b in rows]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n))
    return PairedDelta(
        metric=metric,
        left=left,
        right=right,
        mean_left=sum(a for a, _ in rows) / len(rows),
        mean_right=sum(b for _, b in rows) / len(rows),
        delta=sum(diffs) / len(diffs),
        ci=(means[int(0.025 * n)], means[int(0.975 * n) - 1]),
        n_pairs=len(rows),
    )


@dataclass(frozen=True)
class PairPreference:
    """Whether an arm scored the pivotal analysis higher where it mattered.

    The minimal pairs exist for exactly this comparison: the two halves differ
    in one planted feature, so an arm routing on evidence should want the
    analysis that measures it more on the half where it is present. This is
    the analogue of the paired check in the calibration work the arithmetic
    here comes from, and it is the strictest test the scenario set supports --
    it cannot be satisfied by running everything, or by a prior that happens
    to favour a cheap analysis.

    Attributes:
        arm: Arm name.
        pairs: How many pairs both halves were scored on.
        preferred: Pairs where the present half scored higher.
        ties: Pairs scored identically.
        mean_gap: Mean present-minus-absent probability.
        detail: Per-pair rows, for the report.
    """

    arm: str
    pairs: int
    preferred: int
    ties: int
    mean_gap: float
    detail: list[dict[str, object]] = field(default_factory=list)

    @property
    def rate(self) -> float:
        """Fraction of pairs scored in the right direction.

        Returns:
            The rate, or NaN when no pair could be compared.
        """
        return self.preferred / self.pairs if self.pairs else float("nan")

    def to_dict(self) -> dict[str, object]:
        """Render the comparison.

        Returns:
            A JSON-safe mapping.
        """
        return {
            "arm": self.arm,
            "pairs": self.pairs,
            "preferred": self.preferred,
            "ties": self.ties,
            "rate": round(self.rate, 4),
            "mean_gap": round(self.mean_gap, 4),
            "detail": self.detail,
        }


def pair_preference(
    arm: str,
    by_pair: Mapping[str, tuple[str, float | None, float | None]],
) -> PairPreference:
    """Compare an arm's score for each pivotal analysis across a pair's halves.

    Args:
        arm: Arm name.
        by_pair: Pair identifier to its (pivotal tool, score on the present
            half, score on the absent half). A None on either side means the
            analysis was never offered there, and that pair is skipped.

    Returns:
        The comparison.
    """
    rows: list[dict[str, object]] = []
    gaps: list[float] = []
    preferred = ties = 0

    for pair, (tool, present, absent) in sorted(by_pair.items()):
        if present is None or absent is None:
            rows.append(
                {
                    "pair": pair,
                    "tool": tool,
                    "present": present,
                    "absent": absent,
                    "comparable": False,
                }
            )
            continue
        gap = present - absent
        gaps.append(gap)
        if gap > 0:
            preferred += 1
        elif gap == 0:
            ties += 1
        rows.append(
            {
                "pair": pair,
                "tool": tool,
                "present": round(present, 4),
                "absent": round(absent, 4),
                "gap": round(gap, 4),
                "comparable": True,
            }
        )

    return PairPreference(
        arm=arm,
        pairs=len(gaps),
        preferred=preferred,
        ties=ties,
        mean_gap=sum(gaps) / len(gaps) if gaps else float("nan"),
        detail=rows,
    )
