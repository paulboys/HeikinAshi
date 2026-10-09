"""Score amendment 3's pre-registered predictions against a trace directory.

    python scripts/bench05_predictions.py runs/bench_05a/budgeted

Unlike the benchmark 3 and 4 scorers, this one was written *after* the first
run completed. Every threshold it applies is quoted from PREREGISTERED.md
amendment 3, which was committed before the first call, so there is no room
to move a bar -- but the weaker position is worth stating rather than hiding.

Amendment 3 ranks on the comparative map and gates on the absolute one.

Public API:
    main(argv: Sequence[str] | None = None) -> int
"""

from __future__ import annotations

import glob
import json
import os
import statistics as st
import sys
from collections import Counter
from collections.abc import Sequence

from stock_agent.eval.harness import calibration_items
from stock_agent.eval.metrics import auc, boot_auc, paired_bootstrap
from stock_agent.eval.scenarios import SCENARIOS

__all__ = ["main"]

# A margin or a range is a subtraction, so a value exactly on a threshold can
# land a hair under it. policy.py carries the same guard.
_EPS = 1e-9

# Quoted from amendment 3.
E1_COVERAGE_MIN = 0.57
E2_PIVOTAL_MIN = 5
E4_NDCG_MIN = 0.74
E5_POSITIVES_MIN = 8

BENCH_04 = {
    "coverage": (0.43, 0.57),
    "pivotal": (2, 3),
    "ndcg": (0.74, 0.76),
    "tool_calls": "-2.000 / -1.933",
    "pair_gap": (0.122, 0.115),
}


def _jev_traces(trace_dir: str) -> list[tuple[str, list[dict]]]:
    """Load every jev trace in a directory.

    Args:
        trace_dir: Directory of traces.

    Returns:
        Scenario name and its records, in filename order.
    """
    out = []
    for path in sorted(glob.glob(os.path.join(trace_dir, "jev__*.jsonl"))):
        name = os.path.basename(path).split("__", 1)[1][: -len(".jsonl")]
        with open(path, encoding="utf-8") as handle:
            out.append((name, [json.loads(line) for line in handle]))
    return out


def _totals(records: list[dict], key: str) -> int:
    """Read one field from a run's closing totals.

    Args:
        records: One run's records.
        key: Field name.

    Returns:
        The value, or zero when absent.
    """
    return int((records[-1].get("totals") or {}).get(key) or 0)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the pre-registered verdicts.

    Args:
        argv: Arguments; the first is the trace directory.

    Returns:
        Zero when E1, E2, E3 and E4 all hold, one otherwise.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: bench05_predictions.py <trace-dir>", file=sys.stderr)
        return 2
    trace_dir = args[0]
    traces = _jev_traces(trace_dir)
    if not traces:
        print(f"[error] no jev traces under {trace_dir}", file=sys.stderr)
        return 2

    by_name = {name: records for name, records in traces}
    scored = {s.name: calibration_items(by_name[s.name], s) for s in SCENARIOS if s.name in by_name}

    bands: Counter[str] = Counter()
    exits: Counter[str] = Counter()
    margins: list[float] = []
    for _, records in traces:
        for record in records:
            if record.get("record") == "iteration":
                bands[record["decision"]["band"]] += 1
                comparative = (record.get("parsed") or {}).get("best_next") or {}
                if len(comparative) > 1:
                    values = sorted(comparative.values(), reverse=True)
                    margins.append(values[0] - values[1])
            elif record.get("record") == "run_end":
                exits[str(record.get("exit_reason"))] += 1

    print(f"{len(traces)} scenarios, routing on the comparative map\n")
    print("bands:", dict(bands))
    print("exits:", dict(exits))

    # -- E1 coverage -------------------------------------------------------
    coverages = [
        c
        for s in SCENARIOS
        if s.name in by_name and s.required
        for c in [
            len(
                s.required
                & {
                    str(call["tool"])
                    for rec in by_name[s.name]
                    for call in (rec.get("tool_calls") or [])
                    if call.get("status") == "ok"
                }
            )
            / len(s.required)
        ]
    ]
    coverage = sum(coverages) / len(coverages) if coverages else float("nan")
    e1 = coverage >= E1_COVERAGE_MIN - _EPS
    print(f"\nE1 -- DOES COVERAGE RECOVER?  {'PASS' if e1 else 'FAIL'}")
    print(
        f"      coverage {coverage:.3f}   need >= {E1_COVERAGE_MIN:.2f}   "
        f"bench_04 {BENCH_04['coverage'][0]:.2f} / {BENCH_04['coverage'][1]:.2f}"
    )

    # -- E2 pivotal --------------------------------------------------------
    reached = expected = 0
    for s in SCENARIOS:
        if s.name not in by_name or not s.pivotal:
            continue
        expected += 1
        ran = {
            str(call["tool"])
            for rec in by_name[s.name]
            for call in (rec.get("tool_calls") or [])
            if call.get("status") == "ok"
        }
        reached += int(s.pivotal in ran)
    e2 = reached >= E2_PIVOTAL_MIN
    print(f"\nE2 -- DOES THE RIGHT ANALYSIS NOW RUN?  {'PASS' if e2 else 'FAIL'}")
    print(
        f"      pivotal reached {reached}/{expected}   need >= {E2_PIVOTAL_MIN}/7   "
        f"bench_04 {BENCH_04['pivotal'][0]}/7 and {BENCH_04['pivotal'][1]}/7"
    )

    # -- E3 cost -----------------------------------------------------------
    rules = {
        os.path.basename(p).split("__", 1)[1][: -len(".jsonl")]: p
        for p in sorted(glob.glob(os.path.join(trace_dir, "rules__*.jsonl")))
    }
    print("\nE3 -- IS THE COST WIN KEPT?")
    e3 = False
    if rules:
        pairs = {}
        for name, records in traces:
            if name in rules:
                with open(rules[name], encoding="utf-8") as handle:
                    other = [json.loads(line) for line in handle]
                pairs[name] = (
                    float(_totals(records, "tool_calls")),
                    float(_totals(other, "tool_calls")),
                )
        delta = paired_bootstrap("tool_calls", "jev", "rules", pairs)
        e3 = delta.ci[1] <= 0.0 + _EPS
        print(
            f"      tool calls {delta.delta:+.3f}  "
            f"[{delta.ci[0]:+.3f}, {delta.ci[1]:+.3f}]  n={delta.n_pairs}   "
            f"{'PASS' if e3 else 'FAIL'}"
        )
        print(
            f"      amendment 3 requires the UPPER bound at or below zero; "
            f"bench_04 gave {BENCH_04['tool_calls']}"
        )
    else:
        print("      rules traces absent; cannot pair")

    # -- E4 ranking quality ------------------------------------------------
    ndcgs = [sum(n) / len(n) for _, _, n, _ in scored.values() if n]
    ndcg = sum(ndcgs) / len(ndcgs) if ndcgs else float("nan")
    e4 = ndcg >= E4_NDCG_MIN - _EPS
    print(f"\nE4 -- IS THE RANKING QUALITY KEPT?  {'PASS' if e4 else 'FAIL'}")
    print(
        f"      nDCG {ndcg:.3f}   need >= {E4_NDCG_MIN:.2f}   "
        f"bench_04 {BENCH_04['ndcg'][0]:.2f} / {BENCH_04['ndcg'][1]:.2f}"
    )

    # -- E5 stop signal ----------------------------------------------------
    items = [item for _, enough, _, _ in scored.values() for item in enough]
    pos = [p for label, p in items if label == 1]
    neg = [p for label, p in items if label == 0]
    print("\nE5 -- DOES THE STOP SIGNAL COME BACK?")
    if pos and neg:
        value = auc(pos, neg)
        low, high = boot_auc(pos, neg)
        discriminates = low > 0.5
        enough_positives = len(pos) >= E5_POSITIVES_MIN
        verdict = "PASS" if discriminates and enough_positives else "FAIL"
        print(
            f"      AUC {value:.3f}  [{low:.3f}, {high:.3f}]  n={len(items)}, "
            f"{len(pos)} positive   {verdict}"
        )
        print(
            f"      interval above 0.5: {'yes' if discriminates else 'no'};  "
            f">= {E5_POSITIVES_MIN} positives: "
            f"{'yes' if enough_positives else f'no ({len(pos)})'}"
        )
    else:
        print(f"      only one class present ({len(pos)} positive) -- cannot score")

    # -- context -----------------------------------------------------------
    pairs_by_name: dict[str, dict[str, object]] = {}
    for s in SCENARIOS:
        if s.pair:
            pairs_by_name.setdefault(s.pair, {})[s.half] = s
    gaps = []
    for name in sorted(pairs_by_name):
        present = pairs_by_name[name].get("present")
        absent = pairs_by_name[name].get("absent")
        first = scored.get(getattr(present, "name", ""), (None,) * 4)[3]
        second = scored.get(getattr(absent, "name", ""), (None,) * 4)[3]
        if first is not None and second is not None:
            gaps.append((name, first - second))
    if gaps:
        mean_gap = sum(g for _, g in gaps) / len(gaps)
        print(
            f"\nrecorded, not predicted: mean pair gap {mean_gap:+.3f}  "
            f"(bench_04 {BENCH_04['pair_gap'][0]:+.3f} / "
            f"{BENCH_04['pair_gap'][1]:+.3f})"
        )
        for name, gap in gaps:
            print(f"      {name:20} {gap:+.3f}")
    if margins:
        print(
            f"\nmedian top-two margin on the comparative map {st.median(margins):.3f} "
            f"(margin_min 0.10)"
        )

    return 0 if (e1 and e2 and e3 and e4) else 1


if __name__ == "__main__":
    raise SystemExit(main())
