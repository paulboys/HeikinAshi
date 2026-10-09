"""Score amendment 2's pre-registered predictions against a trace directory.

Written before the first live call of benchmark 4, so the thresholds cannot
be adjusted once the numbers are in. Usage:

    python scripts/bench04_predictions.py runs/bench_04/budgeted

Amendment 2 moves routing from the absolute usefulness noul to a comparative
"is this the best of the field" noul. Both are asked in every request, so the
absolute map is still present and C5 checks it for contamination.

Public API:
    main(argv: Sequence[str] | None = None) -> int
"""

from __future__ import annotations

import glob
import json
import os
import statistics as st
import sys
from collections.abc import Sequence
from pathlib import Path

from stock_agent.eval.harness import calibration_items
from stock_agent.eval.metrics import paired_bootstrap
from stock_agent.eval.scenarios import SCENARIOS
from stock_agent.trace import read_trace

__all__ = ["main"]

# A range or a margin is a subtraction, so a value exactly on a threshold can
# land a hair under it. policy.py carries the same guard, and amendment 1 was
# briefly scored as a failure for want of it.
_EPS = 1e-9

C1_MARGIN_MIN = 0.10
C1_ACT_CLEAR_MIN = 0.50
C2_SHARE_MIN = 0.30
C3_NDCG_MIN = 0.67
C3_PIVOTAL_MIN = 4
C3_PAIR_GAP_MIN = 0.023
C5_TOLERANCE = 0.02

# Benchmark 3's measured values: the baseline every prediction is against.
BENCH_03 = {
    "median_margin": 0.030,
    "top_share": 0.134,
    "ndcg": 0.67,
    "pivotal": 4,
    "pair_gap": 0.023,
}

# Benchmark 3's first-round min and max per tool on the absolute map, for C5.
BENCH_03_ABSOLUTE = {
    "momentum.rsi_stochastic": (0.60, 0.79),
    "signal.mcglone": (0.58, 0.75),
    "volume.surge": (0.32, 0.44),
    "market_regime.price": (0.61, 0.71),
    "trend.heiken_runs": (0.59, 0.69),
    "volatility.realised": (0.62, 0.72),
    "volatility.vix": (0.60, 0.66),
    "pattern.rsi_divergence": (0.69, 0.74),
    "relative_strength.beta_regime": (0.73, 0.76),
}


def _rounds(trace_dir: str, arm: str = "jev") -> list[dict]:
    """Collect every scoring round from an arm's traces.

    Args:
        trace_dir: Directory of traces.
        arm: Arm name prefix.

    Returns:
        One mapping per round, carrying the routing map, the absolute map and
        the policy band.
    """
    out: list[dict] = []
    for path in sorted(glob.glob(os.path.join(trace_dir, f"{arm}__*.jsonl"))):
        scenario = os.path.basename(path).split("__", 1)[1][: -len(".jsonl")]
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("record") != "iteration":
                    continue
                parsed = row.get("parsed") or {}
                routing = parsed.get("routing") or "usefulness"
                routed = parsed.get(routing) or {}
                if len(routed) < 2:
                    continue
                out.append(
                    {
                        "scenario": scenario,
                        "iteration": row.get("iteration"),
                        "routing": routing,
                        "routed": routed,
                        "absolute": parsed.get("usefulness") or {},
                        "band": (row.get("decision") or {}).get("band"),
                    }
                )
    return out


def _tool_calls(trace_dir: str, arm: str) -> dict[str, int]:
    """Read per-scenario tool-call totals for one arm.

    Args:
        trace_dir: Directory of traces.
        arm: Arm name prefix.

    Returns:
        Tool calls per scenario name.
    """
    out: dict[str, int] = {}
    for path in sorted(glob.glob(os.path.join(trace_dir, f"{arm}__*.jsonl"))):
        scenario = os.path.basename(path).split("__", 1)[1][: -len(".jsonl")]
        last = None
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                last = json.loads(line)
        if last:
            out[scenario] = int((last.get("totals") or {}).get("tool_calls") or 0)
    return out


def _score_c3(trace_dir: str) -> tuple[float, int, int, list[tuple[str, float]]]:
    """Compute the artifact check: nDCG, pivotal reach and the pair gaps.

    Args:
        trace_dir: Directory of traces.

    Returns:
        Mean nDCG, pivotal analyses reached, pivotal scenarios, and the gap
        per minimal pair.
    """
    pairs: dict[str, dict[str, object]] = {}
    for scenario in SCENARIOS:
        if scenario.pair:
            pairs.setdefault(scenario.pair, {})[scenario.half] = scenario

    pivotal_score: dict[str, float | None] = {}
    ndcg_all: list[float] = []
    reached = expected = 0
    for scenario in SCENARIOS:
        path = Path(trace_dir) / f"jev__{scenario.name}.jsonl"
        if not path.exists():
            continue
        records = read_trace(path)
        _, _, ndcgs, best = calibration_items(records, scenario)
        pivotal_score[scenario.name] = best
        if ndcgs:
            ndcg_all.append(sum(ndcgs) / len(ndcgs))
        if scenario.pivotal:
            expected += 1
            ran = {
                str(call["tool"])
                for record in records
                for call in (record.get("tool_calls") or [])
                if call.get("status") == "ok"
            }
            reached += int(scenario.pivotal in ran)

    gaps: list[tuple[str, float]] = []
    for name in sorted(pairs):
        present = pairs[name].get("present")
        absent = pairs[name].get("absent")
        first = pivotal_score.get(getattr(present, "name", ""))
        second = pivotal_score.get(getattr(absent, "name", ""))
        if first is not None and second is not None:
            gaps.append((name, first - second))

    ndcg = sum(ndcg_all) / len(ndcg_all) if ndcg_all else float("nan")
    return ndcg, reached, expected, gaps


def main(argv: Sequence[str] | None = None) -> int:
    """Print the pre-registered verdicts.

    Args:
        argv: Arguments; the first is the trace directory.

    Returns:
        Zero when C1, C2, C3 and C5 all hold, one otherwise.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: bench04_predictions.py <trace-dir>", file=sys.stderr)
        return 2
    trace_dir = args[0]
    rounds = _rounds(trace_dir)
    if not rounds:
        print(f"[error] no jev scoring rounds under {trace_dir}", file=sys.stderr)
        return 2

    routing = {r["routing"] for r in rounds}
    print(f"{len(rounds)} scoring rounds, routing on: {', '.join(sorted(routing))}")
    if routing != {"best_next"}:
        print(
            "  [warning] these rounds did not route on the comparative map, so "
            "predictions 1 and 2 below are a baseline reading, not a test of "
            "amendment 2"
        )

    margins = []
    for round_ in rounds:
        values = sorted(round_["routed"].values(), reverse=True)
        margins.append(values[0] - values[1])
    median_margin = st.median(margins)
    act_clear = sum(1 for r in rounds if r["band"] == "act_clear")
    fraction = act_clear / len(rounds)
    c1 = median_margin >= C1_MARGIN_MIN - _EPS and fraction >= C1_ACT_CLEAR_MIN - _EPS
    print(
        f"\nPrediction 1 -- DECISIVENESS: does it separate the top two "
        f"candidates?  {'PASS' if c1 else 'FAIL'}"
    )
    print(
        f"      median top1-top2 margin  {median_margin:.3f}   "
        f"need >= {C1_MARGIN_MIN:.2f}   bench_03 {BENCH_03['median_margin']:.3f}"
    )
    print(f"      largest margin seen      {max(margins):.3f}")
    print(
        f"      act_clear rounds         {act_clear}/{len(rounds)} = {fraction:.2f}"
        f"   need >= {C1_ACT_CLEAR_MIN:.2f}   bench_03 0/27"
    )

    shares = [max(r["routed"].values()) / sum(r["routed"].values()) for r in rounds]
    share = st.median(shares)
    sums = [sum(r["routed"].values()) for r in rounds]
    c2 = share >= C2_SHARE_MIN - _EPS
    print(
        f"\nPrediction 2 -- COHERENCE: does one candidate own the probability "
        f"mass?  {'PASS' if c2 else 'FAIL'}"
    )
    print(
        f"      top candidate's share    {share:.3f}   "
        f"need >= {C2_SHARE_MIN:.2f}   bench_03 {BENCH_03['top_share']:.3f}   "
        f"uniform 0.111"
    )
    print(
        f"      median probability sum   {st.median(sums):.2f}   "
        f"1.00 if read as a partition, bench_03 5.61"
    )

    ndcg, reached, expected, gaps = _score_c3(trace_dir)
    mean_gap = sum(g for _, g in gaps) / len(gaps) if gaps else float("nan")
    c3 = (
        ndcg >= C3_NDCG_MIN - _EPS
        and reached >= C3_PIVOTAL_MIN
        and mean_gap >= C3_PAIR_GAP_MIN - _EPS
    )
    print(
        f"\nPrediction 3 -- IS THE WINNER THE RIGHT ONE? (the safeguard on "
        f"prediction 1)  {'HOLDS' if c3 else 'VIOLATED'}"
    )
    print(f"      nDCG            {ndcg:.3f}    need >= {C3_NDCG_MIN:.2f}")
    print(f"      pivotal reached {reached}/{expected}      need >= {C3_PIVOTAL_MIN}/7")
    print(f"      mean pair gap   {mean_gap:+.3f}   need >= {C3_PAIR_GAP_MIN:+.3f}")
    for name, gap in gaps:
        print(f"         {name:20} {gap:+.3f}")
    if c1 and not c3:
        print(
            "      >>> prediction 1 passed and prediction 3 did not: the margin "
            "widened around an arbitrary winner, which is worse than a tie "
            "because the policy acts on it. Amendment 2 says revert."
        )

    jev_tools = _tool_calls(trace_dir, "jev")
    rules_tools = _tool_calls(trace_dir, "rules")
    shared = sorted(set(jev_tools) & set(rules_tools))
    print(
        "\nPrediction 4 -- COST: no more tool calls than the rule tree "
        "(preregistered criterion 3)"
    )
    if shared:
        delta = paired_bootstrap(
            "tool_calls",
            "jev",
            "rules",
            {s: (float(jev_tools[s]), float(rules_tools[s])) for s in shared},
        )
        ok = delta.ci[0] <= 0.0 <= delta.ci[1] or delta.ci[1] <= 0.0 + _EPS
        print(
            f"      tool calls {delta.delta:+.3f}  "
            f"[{delta.ci[0]:+.3f}, {delta.ci[1]:+.3f}]  n={delta.n_pairs}   "
            f"{'PASS' if ok else 'FAIL'}   bench_03 +1.000 [+0.533, +1.533]"
        )
    else:
        print("      rules traces absent; read the interval off the bench table")

    # First round only. The reference spans are first-round figures, and the
    # menu shrinks as tools run, so comparing against every round would read
    # a later round's lower scores as contamination.
    absolute: dict[str, list[float]] = {}
    for round_ in rounds:
        if round_["iteration"] != 1:
            continue
        for tool, value in round_["absolute"].items():
            absolute.setdefault(tool, []).append(value)
    print(
        f"\nPrediction 5 -- CONTAMINATION: did sharing one request move the old "
        f"question's answers? (tolerance +-{C5_TOLERANCE:.2f} vs bench_03)"
    )
    c5 = bool(absolute)
    if not absolute:
        print("      absolute map absent from these traces -- cannot check")
    for tool in sorted(absolute):
        low, high = min(absolute[tool]), max(absolute[tool])
        reference = BENCH_03_ABSOLUTE.get(tool)
        if reference is None:
            print(f"      ?   {tool:32} {low:.2f}-{high:.2f}   no bench_03 reference")
            continue
        drift = max(abs(low - reference[0]), abs(high - reference[1]))
        ok = drift <= C5_TOLERANCE + _EPS
        c5 = c5 and ok
        print(
            f"      {'ok ' if ok else 'no '} {tool:32} {low:.2f}-{high:.2f}   "
            f"vs {reference[0]:.2f}-{reference[1]:.2f}   drift {drift:.2f}"
        )
    if not c5 and absolute:
        print(
            "      >>> the two framings cannot share a request, so both runs "
            "are confounded, prediction 1 included."
        )

    return 0 if (c1 and c2 and c3 and c5) else 1


if __name__ == "__main__":
    raise SystemExit(main())
