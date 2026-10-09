"""Score amendment 1's pre-registered predictions against a trace directory.

Written before the first live call of benchmark 3, so the thresholds cannot
be adjusted once the numbers are in. Usage:

    python scripts/bench03_predictions.py runs/bench_03/budgeted

The baselines are benchmark 2's measured first-round score ranges, quoted
from PREREGISTERED.md amendment 1.

Public API:
    main(argv: Sequence[str] | None = None) -> int
"""

from __future__ import annotations

import glob
import json
import os
import re
import statistics as st
import sys
from collections.abc import Sequence

__all__ = ["main"]

# Benchmark 2's first-round score range per tool. The experiment asks whether
# the P1 group moves toward signal.mcglone's 0.15 while the P3 group does not.
BENCH_02_RANGE = {
    "trend.heiken_runs": 0.03,
    "momentum.rsi_stochastic": 0.02,
    "volatility.realised": 0.03,
    "market_regime.price": 0.06,
    "relative_strength.beta_regime": 0.02,
    "volatility.vix": 0.02,
    "pattern.rsi_divergence": 0.02,
    "volume.surge": 0.18,
    "signal.mcglone": 0.15,
}

# Condition named in the description is visible in the state.
P1_TOOLS = (
    "trend.heiken_runs",
    "momentum.rsi_stochastic",
    "volatility.realised",
    "market_regime.price",
)
# Condition names the benchmark index or the broad market, neither of which
# appears in the state. These must NOT move, or the effect is a prompt
# artefact rather than condition-matching.
P3_TOOLS = ("relative_strength.beta_regime", "volatility.vix")

P1_MIN = 0.10
P3_MAX = 0.05
P2_MIN = 0.05

# A range is a subtraction, so a span of exactly the threshold can land a hair
# under it: 0.71 - 0.61 == 0.09999999999999998. policy.py carries the same
# guard for the same reason. Without it three of the four P1 tools read as
# failing a bar they land exactly on.
_EPS = 1e-9
PAIR_PIVOTAL = {
    "volatility": ("volatility_spike", "volatility_calm", "volatility.realised"),
    "momentum": ("momentum_oversold", "momentum_neutral", "momentum.rsi_stochastic"),
}


def _first_round(trace_dir: str) -> tuple[dict[str, list[float]], dict[str, dict[str, float]]]:
    """Collect first-round usefulness scores from every jev trace.

    Args:
        trace_dir: Directory of ``jev__<scenario>.jsonl`` traces.

    Returns:
        Scores per tool, and scores per scenario per tool.
    """
    by_tool: dict[str, list[float]] = {}
    by_scenario: dict[str, dict[str, float]] = {}
    for path in sorted(glob.glob(os.path.join(trace_dir, "jev__*.jsonl"))):
        scenario = os.path.basename(path).split("__", 1)[1][: -len(".jsonl")]
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("record") != "iteration" or row.get("iteration") != 1:
                    continue
                scores = (row.get("parsed") or {}).get("usefulness") or {}
                by_scenario[scenario] = dict(scores)
                for tool, score in scores.items():
                    by_tool.setdefault(tool, []).append(score)
    return by_tool, by_scenario


def _drawdowns(trace_dir: str) -> dict[str, float]:
    """Read each scenario's drawdown out of its first-round state text.

    Args:
        trace_dir: Directory of traces.

    Returns:
        Drawdown percentage per scenario.
    """
    pattern = re.compile(r"([-+][\d.]+)% from the window high")
    out: dict[str, float] = {}
    for path in sorted(glob.glob(os.path.join(trace_dir, "jev__*.jsonl"))):
        scenario = os.path.basename(path).split("__", 1)[1][: -len(".jsonl")]
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("record") != "iteration" or row.get("iteration") != 1:
                    continue
                found = pattern.search(row.get("state_text", ""))
                if found:
                    out[scenario] = float(found.group(1))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Print the pre-registered verdicts.

    Args:
        argv: Arguments; the first is the trace directory.

    Returns:
        Zero when P1 passes and P3 holds, one otherwise.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: bench03_predictions.py <trace-dir>", file=sys.stderr)
        return 2
    trace_dir = args[0]
    by_tool, by_scenario = _first_round(trace_dir)
    if not by_tool:
        print(f"[error] no jev first-round scores under {trace_dir}", file=sys.stderr)
        return 2

    ranges = {t: max(v) - min(v) for t, v in by_tool.items()}
    print(f"first-round score ranges, {len(by_scenario)} scenarios\n")
    print(f"{'tool':32}{'bench_02':>10}{'now':>8}{'delta':>8}   group")
    for tool in sorted(ranges, key=lambda t: -ranges[t]):
        group = (
            "condition visible in state"
            if tool in P1_TOOLS
            else "CONTROL: condition absent from state"
            if tool in P3_TOOLS
            else ""
        )
        if tool == "signal.mcglone":
            group = "reference, description untouched"
        before = BENCH_02_RANGE.get(tool)
        delta = f"{ranges[tool] - before:+8.2f}" if before is not None else f"{'-':>8}"
        shown = f"{before:10.2f}" if before is not None else f"{'-':>10}"
        print(f"{tool:32}{shown}{ranges[tool]:8.2f}{delta}   {group}")

    p1 = {t: ranges.get(t) for t in P1_TOOLS}
    p3 = {t: ranges.get(t) for t in P3_TOOLS}
    p1_ok = all(v is not None and v >= P1_MIN - _EPS for v in p1.values())
    p3_ok = all(v is None or v <= P3_MAX + _EPS for v in p3.values())

    print(
        f"\nPrediction 1 -- DO THE DESCRIPTIONS WIDEN THE SCORES, for tools "
        f"whose\n   condition is visible in the state? (range >= {P1_MIN:.2f})  "
        f"{'PASS' if p1_ok else 'FAIL'}"
    )
    for tool, value in p1.items():
        mark = "ok " if value is not None and value >= P1_MIN - _EPS else "no "
        print(f"      {mark} {tool:30} {value if value is not None else float('nan'):.2f}")

    print(
        f"\nPrediction 2 -- DOES THE RIGHT HALF SCORE HIGHER, on the "
        f"volatility and\n   momentum pairs? (gap >= {P2_MIN:+.2f})"
    )
    for pair, (present, absent, pivotal) in PAIR_PIVOTAL.items():
        a = by_scenario.get(present, {}).get(pivotal)
        b = by_scenario.get(absent, {}).get(pivotal)
        if a is None or b is None:
            print(f"      ?   {pair:12} pivotal {pivotal} absent from a trace")
            continue
        gap = a - b
        mark = "ok " if gap >= P2_MIN - _EPS else "no "
        print(f"      {mark} {pair:12} present {a:.2f}  absent {b:.2f}  gap {gap:+.3f}")

    print(
        f"\nPrediction 3 -- THE ARTIFACT CONTROL: tools whose condition is "
        f"ABSENT\n   from the state must stay flat (range <= {P3_MAX:.2f})  "
        f"{'HOLDS' if p3_ok else 'VIOLATED -- longer text alone may explain prediction 1'}"
    )
    for tool, value in p3.items():
        mark = "ok " if value is None or value <= P3_MAX + _EPS else "no "
        print(f"      {mark} {tool:30} {value if value is not None else float('nan'):.2f}")

    mcg = by_tool.get("signal.mcglone")
    dd = _drawdowns(trace_dir)
    print(
        "\nPrediction 4 -- STABILITY: the one untouched tool should not drift\n"
        "   (signal.mcglone, expect range ~0.15 and drawdown r ~ -0.79)"
    )
    if mcg:
        paired = [
            (dd[s], by_scenario[s]["signal.mcglone"])
            for s in by_scenario
            if s in dd and "signal.mcglone" in by_scenario[s]
        ]
        corr = st.correlation(*zip(*paired, strict=False)) if len(paired) > 4 else float("nan")
        print(f"      range {max(mcg) - min(mcg):.2f}   r(drawdown) {corr:+.3f}   n={len(paired)}")
    else:
        print("      not scored in these traces")

    print(
        "\nPrediction 5 -- DECLARED ASYMMETRY (recorded, never a prediction):\n"
        "   RSI divergence cannot be judged before RSI exists in the state.  "
        f"range {ranges.get('pattern.rsi_divergence', float('nan')):.2f}"
    )
    return 0 if (p1_ok and p3_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
