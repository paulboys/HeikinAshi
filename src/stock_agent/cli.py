"""Command line for the routing agent.

    python -m stock_agent analyze NVDA
    python -m stock_agent analyze NVDA --as-of 2025-06-30 --verbose
    python -m stock_agent analyze SYN_UPTREND --scenario uptrend --mock
    python -m stock_agent tools

Live decision-model calls are opt-in: without ``--live`` the agent uses the
deterministic mock, and ``--dry-run`` prints the request bodies that would
have been sent without sending anything or even reading a key.

Public API:
    main(argv: Sequence[str] | None = None) -> int
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from stock_agent import __version__
from stock_agent.asof import (
    FixtureProvider,
    FrameProvider,
    LiveProvider,
    PriceProvider,
    RecordingProvider,
)
from stock_agent.config import load_config
from stock_agent.eval.harness import BenchReport
from stock_agent.eval.metrics import Calibration
from stock_agent.eval.mock_jev import MockJevClient
from stock_agent.eval.synthetic import plant_run, synth_ohlc, synth_vix
from stock_agent.loop import AgentRun, DecisionModel, run_analysis
from stock_agent.registry import ToolRegistry
from stock_agent.replay import replay_trace
from stock_agent.tools.builtin import build_registry
from stock_agent.trace import read_trace

__all__ = ["main"]

DISCLAIMER = (
    "This is a research and analysis tool, not a trading system. It places no "
    "orders and makes no claim to predict returns."
)


@dataclass(frozen=True)
class _Scenario:
    """A built-in synthetic situation.

    Attributes:
        doc: What the situation represents.
        bars: Bars to generate.
        seed: Generator seed, so the series is reproducible.
        drift: Annualised drift.
        vol: Annualised volatility.
        run: Heiken Ashi run to plant, or zero for none.
    """

    doc: str
    bars: int
    seed: int
    drift: float
    vol: float
    run: int = 0


# Built-in situations, so the agent is runnable with no network at all.
_SCENARIOS: dict[str, _Scenario] = {
    "uptrend": _Scenario(
        "steady advance with an extended run of green candles",
        bars=400,
        seed=1,
        drift=0.35,
        vol=0.18,
        run=9,
    ),
    "choppy": _Scenario("no trend, moderate volatility", bars=400, seed=2, drift=0.0, vol=0.22),
    "selloff": _Scenario(
        "sustained decline with elevated volatility",
        bars=400,
        seed=3,
        drift=-0.40,
        vol=0.38,
    ),
    "short_history": _Scenario(
        "only 60 bars, so most analyses cannot run",
        bars=60,
        seed=4,
        drift=0.10,
        vol=0.20,
    ),
}


def _scenario_frame(name: str) -> pd.DataFrame:
    """Build the price history for a named scenario.

    Args:
        name: Scenario key.

    Returns:
        A frame of synthetic bars.

    Raises:
        KeyError: If the scenario is unknown.
    """
    spec = _SCENARIOS[name]
    frame = synth_ohlc(spec.bars, seed=spec.seed, drift_ann=spec.drift, vol_ann=spec.vol)
    return plant_run(frame, spec.run, "green") if spec.run else frame


def _scenario_provider(ticker: str, name: str) -> FrameProvider:
    """Build an offline provider covering every ticker the tools reach for.

    The benchmark and the volatility index are included because without them
    the relative-strength and contrarian analyses can only ever fail, and a
    scenario run would exercise a smaller slice of the registry than a live
    one.

    Args:
        ticker: Symbol under analysis.
        name: Scenario key.

    Returns:
        A provider serving the ticker, a benchmark and a volatility index.
    """
    bars = _SCENARIOS[name].bars
    frame = _scenario_frame(name)
    return FrameProvider(
        {
            ticker: frame,
            # A benchmark that advances gently, so relative strength is meaningful
            # rather than an artefact of the benchmark's own noise.
            "SPY": synth_ohlc(bars, seed=101, drift_ann=0.09, vol_ann=0.15, s0=400.0),
            # Derived from the ticker rather than generated independently, so a
            # selloff scenario actually comes with a stressed volatility index.
            "^VIX": synth_vix(frame),
        }
    )


def _render(run: AgentRun, registry: ToolRegistry, verbose: bool) -> None:
    """Print the analysis.

    Facts measured, the path taken and the uncertainty are kept visually
    separate, so a reader is never invited to mistake one for another.

    Args:
        run: The completed run.
        registry: The registry used, for titles.
        verbose: Print the decision trace as well.
    """
    state = run.state
    window = "live" if state.asof is None else f"as of {state.asof.isoformat()}"
    print()
    print("=" * 78)
    print(f"{state.ticker}   {window}   {state.interval}")
    print(f"objective: {state.objective}")
    print("=" * 78)

    if verbose and run.decisions:
        print("\nDECISION PATH")
        for index, decision in enumerate(run.decisions):
            selected = ", ".join(decision.selected) or "(stop)"
            probability = f"  p={decision.p_top1:.2f}" if decision.p_top1 is not None else ""
            print(f"  iteration {index}  {decision.band:<24} {selected}{probability}")
            print(f"              {decision.rationale}")

    print("\nMEASURED")
    by_tool: dict[str, list[str]] = {}
    for obs in state.observations.values():
        if obs.display:
            by_tool.setdefault(obs.tool, []).append(obs.display)
    if by_tool:
        for tool in sorted(by_tool):
            title = registry.get(tool).title if tool in registry else tool
            print(f"  [{title}]")
            for line in sorted(by_tool[tool]):
                print(f"      {line}")
    else:
        print("  nothing was measured")

    print("\nANALYSES RUN")
    print(f"  {', '.join(run.tools_run) if run.tools_run else 'none'}")
    skipped = [s.name for s in registry.implemented() if s.name not in run.tools_run]
    if skipped:
        print(f"  not run: {', '.join(skipped)}")
    absent = registry.absent()
    if absent:
        print(f"  unavailable in this system: {', '.join(s.name for s in absent)}")

    print("\nWHY IT STOPPED")
    print(f"  {run.exit_reason}: {run.exit_detail}")
    if run.partial:
        print("  the analysis is incomplete")
    if run.conviction is not None:
        print(f"  model conviction: {run.conviction} of 4")

    print("\nUNCERTAINTY")
    for caveat in run.caveats:
        print(f"  - {caveat}")
    if run.trace_path is not None:
        print(f"\ntrace: {run.trace_path}")
    print(f"\n{DISCLAIMER}")


def _build_model(args: argparse.Namespace) -> DecisionModel:
    """Choose the decision model for this run.

    Args:
        args: Parsed arguments.

    Returns:
        A live or mock client.
    """
    if not args.live:
        preferred = tuple(args.prefer.split(",")) if args.prefer else ()
        return MockJevClient(
            args.strategy,
            preferred=preferred,
            enough_after=args.enough_after,
        )

    from stock_agent.jev.client import JevClient

    config = load_config(args.config, args.set or [])
    return JevClient(
        endpoint=config.jev.endpoint,
        model=config.jev.model,
        timeout=config.jev.timeout_s,
        max_retries=config.jev.max_retries,
        dry_run=args.dry_run,
        recorder=(
            (lambda body: print(json.dumps(body, indent=2, ensure_ascii=False)))
            if args.dry_run
            else None
        ),
    )


def _cmd_analyze(args: argparse.Namespace) -> int:
    """Run one analysis.

    Args:
        args: Parsed arguments.

    Returns:
        Process exit code.
    """
    config = load_config(args.config, args.set or [])
    registry = build_registry()

    asof: date | None = None
    if args.as_of:
        try:
            asof = datetime.strptime(args.as_of, "%Y-%m-%d").date()
        except ValueError:
            print(f"[error] --as-of must be YYYY-MM-DD, got {args.as_of!r}", file=sys.stderr)
            return 2

    provider: PriceProvider
    if args.scenario:
        if args.scenario not in _SCENARIOS:
            print(
                f"[error] unknown scenario {args.scenario!r}; "
                f"choose from {', '.join(sorted(_SCENARIOS))}",
                file=sys.stderr,
            )
            return 2
        provider = _scenario_provider(args.ticker, args.scenario)
    elif args.frames:
        try:
            provider = FixtureProvider(Path(args.frames))
        except FileNotFoundError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 2
    else:
        provider = LiveProvider()

    if args.record_frames:
        # Wrapping, not replacing: the run still fetches normally and the
        # recording is a side effect, so one live run becomes a fixture every
        # later comparison can share.
        provider = RecordingProvider(provider, Path(args.record_frames))

    trace_path = None
    if not args.no_trace:
        trace_path = config.trace_dir / args.ticker / f"{args.ticker}.jsonl"

    run = run_analysis(
        ticker=args.ticker,
        objective=args.objective,
        registry=registry,
        model=_build_model(args),
        provider=provider,
        config=config,
        asof=asof,
        trace_path=trace_path,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "ticker": run.state.ticker,
                    "exit_reason": run.exit_reason,
                    "partial": run.partial,
                    "tools_run": run.tools_run,
                    "observations": {k: o.value for k, o in run.state.observations.items()},
                    "caveats": run.caveats,
                },
                indent=2,
                default=str,
            )
        )
    else:
        _render(run, registry, args.verbose)
    return 0


def _render_bench(report: BenchReport) -> None:
    """Print a benchmark report as a table.

    Args:
        report: The report to render.
    """
    print(f"\nregime: {report.regime}   reference arm: {report.reference}")
    if report.scenario_failures:
        print("  [warning] scenarios whose planted feature did not verify:")
        for name, detail in report.scenario_failures:
            print(f"    {name}: {detail}")

    columns = (
        ("cov", "required_coverage"),
        ("prec", "precision"),
        ("nDCG", "ndcg"),
        ("forb", "forbidden_hits"),
        ("redun", "redundant_calls"),
        ("tools", "tools_run"),
        ("calls", "jev_calls"),
        ("wall_s", "wall_s"),
    )
    header = "  ".join(f"{label:>6}" for label, _ in columns)
    print(f"\n{'arm':12}{header}")
    for arm in report.arms():
        row = "  ".join(f"{report.mean(arm, key):6.2f}" for _, key in columns)
        print(f"{arm:12}{row}")

    if report.deltas:
        print("\npaired differences against the reference (95% bootstrap):")
        for delta in report.deltas:
            mark = "*" if delta.significant else " "
            print(
                f" {mark} {delta.left:9} {delta.metric:18} "
                f"{delta.delta:+.3f}  [{delta.ci[0]:+.3f}, {delta.ci[1]:+.3f}]  "
                f"n={delta.n_pairs}"
            )
        print("   * = interval excludes zero")


def _render_calibration(rows: Sequence[Calibration]) -> None:
    """Print calibration results.

    Args:
        rows: Calibration results to render.
    """
    for row in rows:
        print(f"\n=== {row.name}")
        if not row.n:
            print("  nothing to score")
            continue
        print(f"  n={row.n} ({row.positives} positive, base rate {row.base_rate:.2f})")
        print(
            f"  mean p: positives {row.mean_p_positive:.3f} vs negatives "
            f"{row.mean_p_negative:.3f}"
        )
        print(
            f"  ROC AUC {row.roc_auc:.3f} (bootstrap 95% "
            f"{row.auc_ci[0]:.3f}-{row.auc_ci[1]:.3f}; 0.5 = chance)"
            f"{'  DISCRIMINATES' if row.discriminates else ''}"
        )
        print(
            f"  Brier {row.brier:.3f} vs base rate {row.brier_base:.3f} "
            f"-> skill {row.skill:+.3f} (0 = no better than the base rate)"
        )
        print(f"  ECE {row.ece:.3f}")
        for bucket in row.bins:
            print(
                f"    [{bucket['low']:.1f}-{bucket['high']:.1f}) "
                f"n={int(bucket['n']):4d}  mean p={bucket['mean_p']:.2f}  "
                f"observed={bucket['observed']:.2f}"
            )


def _cmd_bench(args: argparse.Namespace) -> int:
    """Run the benchmark across arms and scenarios.

    Args:
        args: Parsed arguments.

    Returns:
        Zero, or non-zero when validation fails or a scenario does not verify.
    """
    from stock_agent.eval.harness import run_benchmark, validate_metrics
    from stock_agent.eval.scenarios import SCENARIOS, by_name

    if args.validate:
        result = validate_metrics()
        print(json.dumps(result, indent=2))
        if not result["separated"]:
            print(
                "\n[error] the metrics cannot separate an oracle from random "
                "choices; no comparison built on them would mean anything",
                file=sys.stderr,
            )
            return 1
        print("\nmetrics validated: an oracle scores near-perfect, random near chance")
        return 0

    scenarios = SCENARIOS
    if args.scenario:
        try:
            scenarios = (by_name(args.scenario),)
        except KeyError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 2

    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    if "jev" in arms and not args.live:
        print(
            "[error] the jev arm calls the real decision model; pass --live to " "allow it",
            file=sys.stderr,
        )
        return 2

    models: dict[str, DecisionModel] | None = None
    if "jev" in arms:
        from stock_agent.jev.client import JevClient

        config = load_config(args.config, args.set or [])
        models = {
            "jev": JevClient(
                endpoint=config.jev.endpoint,
                model=config.jev.model,
                timeout=config.jev.timeout_s,
                max_retries=config.jev.max_retries,
            )
        }

    try:
        report = run_benchmark(
            arms=arms,
            scenarios=scenarios,
            regime=args.regime,
            reference=args.reference,
            trace_dir=Path(args.trace_dir) if args.trace_dir else None,
            models=models,
            seed=args.seed,
            verify=not args.no_verify,
            overwrite_traces=args.overwrite_traces,
        )
    except FileExistsError as exc:
        # Refused before any arm ran, so nothing was spent.
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        _render_bench(report)
        if args.calibration:
            for arm in report.arms():
                _render_calibration(report.calibrations.get(arm, []))
    return 1 if report.scenario_failures else 0


def _cmd_scenarios(args: argparse.Namespace) -> int:
    """Verify every benchmark scenario against the production detectors.

    Args:
        args: Parsed arguments.

    Returns:
        Zero when every scenario is what it claims, one otherwise.
    """
    from stock_agent.eval.scenarios import SCENARIOS, verify_all

    rows = verify_all()
    lookup = {s.name: s for s in SCENARIOS}
    failures = [name for name, ok, _ in rows if not ok]

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": name,
                        "verified": ok,
                        "detail": detail,
                        "pair": lookup[name].pair,
                        "half": lookup[name].half,
                        "required": sorted(lookup[name].required),
                        "forbidden": sorted(lookup[name].forbidden),
                        "pivotal": lookup[name].pivotal,
                    }
                    for name, ok, detail in rows
                ],
                indent=2,
            )
        )
        return 1 if failures else 0

    print(f"{'scenario':24}{'pair/half':26}{'verified':10}detail")
    for name, ok, detail in rows:
        scenario = lookup[name]
        pair = f"{scenario.pair or '-'}/{scenario.half}"
        print(f"{name:24}{pair:26}{'yes' if ok else 'NO':10}{detail}")
    if failures:
        print(
            f"\n[error] {len(failures)} scenario(s) are not what they claim: "
            f"{', '.join(failures)}",
            file=sys.stderr,
        )
        return 1
    print(f"\nall {len(rows)} scenarios verified against the real detectors")
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    """Score the probabilities in saved benchmark traces.

    Calibration needs labels, and the labels come from a scenario's declared
    expectations, so this reads traces written by ``bench --trace-dir``, whose
    filenames carry the arm and the scenario. A live single-ticker run has no
    labels and cannot be calibrated.

    Args:
        args: Parsed arguments.

    Returns:
        Zero when at least one arm could be scored, one otherwise.
    """
    from stock_agent.eval.harness import calibration_items
    from stock_agent.eval.metrics import calibrate
    from stock_agent.eval.scenarios import by_name

    root = Path(args.traces)
    files = sorted(root.glob("*.jsonl")) if root.is_dir() else [root]
    if not files:
        print(f"[error] no traces found at {root}", file=sys.stderr)
        return 1

    useful: dict[str, list[tuple[int, float]]] = {}
    enough: dict[str, list[tuple[int, float]]] = {}
    skipped: list[str] = []

    for path in files:
        stem = path.stem
        if "__" not in stem:
            skipped.append(f"{path.name}: filename does not name an arm and scenario")
            continue
        arm, _, scenario_name = stem.partition("__")
        try:
            scenario = by_name(scenario_name)
        except KeyError:
            skipped.append(f"{path.name}: unknown scenario {scenario_name!r}")
            continue
        rows = read_trace(path)
        arm_useful, arm_enough, _, _ = calibration_items(rows, scenario)
        useful.setdefault(arm, []).extend(arm_useful)
        enough.setdefault(arm, []).extend(arm_enough)

    for note in skipped:
        print(f"[skipped] {note}", file=sys.stderr)
    if not useful:
        print("[error] nothing could be scored", file=sys.stderr)
        return 1

    results = [
        calibrate(f"{arm}: {label}", items)
        for arm in sorted(useful)
        for label, items in (
            ("usefulness", useful[arm]),
            ("sufficiency", enough.get(arm, [])),
        )
    ]

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(f"scored {len(files) - len(skipped)} trace(s) from {root}")
        _render_calibration(results)
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    """Re-run the policy over a recorded trace.

    Args:
        args: Parsed arguments.

    Returns:
        Zero when every decision reproduced, one when any diverged.
    """
    path = Path(args.trace)
    if not path.exists():
        print(f"[error] no trace at {path}", file=sys.stderr)
        return 2

    # Thresholds come from the trace unless the caller supplies their own,
    # which turns the replay from a regression test into a what-if.
    policy = None
    if args.config or args.set:
        policy = load_config(args.config, args.set or []).policy

    try:
        report = replay_trace(path, policy)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "trace": str(report.path),
                    "run_id": report.run_id,
                    "ticker": report.ticker,
                    "config_source": report.config_source,
                    "iterations_replayed": report.iterations_replayed,
                    "iterations_skipped": report.iterations_skipped,
                    "diverging_iterations": report.diverging_iterations,
                    "identical": report.identical,
                    "diffs": [
                        {
                            "iteration": d.iteration,
                            "field": d.field_name,
                            "recorded": d.recorded,
                            "replayed": d.replayed,
                        }
                        for d in report.diffs
                    ],
                },
                indent=2,
                default=str,
            )
        )
        return 0 if report.identical else 1

    print(f"{report.ticker}   run {report.run_id}   thresholds from {report.config_source}")
    print(report.summary())
    for diff in report.diffs:
        print(f"  {diff}")
    return 0 if report.identical else 1


def _cmd_tools(args: argparse.Namespace) -> int:
    """List the analyses the agent can and cannot run.

    Args:
        args: Parsed arguments.

    Returns:
        Process exit code.
    """
    registry = build_registry()
    if args.json:
        print(
            json.dumps(
                {
                    "implemented": [
                        {
                            "name": s.name,
                            "category": s.category,
                            "title": s.title,
                            "description": s.jev_description,
                            "cost": s.cost.cost_class,
                            "asof_capable": s.asof_capable,
                            "retrospective": s.retrospective,
                            "computed_in_agent": s.computed_in_agent,
                            "produces": sorted(s.produces),
                            "requires": sorted(s.requires),
                        }
                        for s in registry.implemented()
                    ],
                    "absent": [
                        {"name": s.name, "category": s.category, "reason": s.absent_reason}
                        for s in registry.absent()
                    ],
                },
                indent=2,
            )
        )
        return 0

    print("\nAVAILABLE")
    for spec in registry.implemented():
        flags = []
        if spec.retrospective:
            flags.append("retrospective")
        if spec.computed_in_agent:
            flags.append("computed in agent")
        if spec.asof_capable == "none":
            flags.append("live only")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  {spec.name:<28} {spec.category:<14} {spec.cost.cost_class:<7}{suffix}")
        print(f"      {spec.jev_description}")
    print("\nNOT AVAILABLE IN THIS SYSTEM")
    for spec in registry.absent():
        print(f"  {spec.name:<28} {spec.absent_reason}")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="stock_agent",
        description="Adaptive stock analysis routed by a specialised decision model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Synthetic scenario, deterministic mock model, no network at all
  python -m stock_agent analyze SYN_UP --scenario uptrend --mock --verbose

  # Real prices, still the mock router
  python -m stock_agent analyze NVDA

  # Historical replay; the macro analyses withhold themselves
  python -m stock_agent analyze NVDA --as-of 2025-06-30

  # Print the request bodies without sending them or reading a key
  python -m stock_agent analyze NVDA --live --dry-run

  # Record the prices a run used, then reproduce it offline from them
  python -m stock_agent analyze NVDA --record-frames runs/NVDA/frames
  python -m stock_agent analyze NVDA --frames runs/NVDA/frames

  # Re-decide a recorded run; non-zero exit means the policy has drifted
  python -m stock_agent replay runs/NVDA/NVDA.jsonl

  # Confirm every benchmark scenario is what it claims to be
  python -m stock_agent scenarios

  # Compare the routing arms; --validate checks the metrics work at all
  python -m stock_agent bench --validate
  python -m stock_agent bench --regime budgeted --calibration

  # Keep the traces, then score the probabilities in them
  python -m stock_agent bench --trace-dir runs/bench
  python -m stock_agent calibrate runs/bench

  # What this system can and cannot analyse
  python -m stock_agent tools
        """,
    )
    parser.add_argument("--version", action="version", version=f"stock_agent {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="analyse one ticker")
    analyze.add_argument("ticker")
    analyze.add_argument(
        "--objective",
        default="whether this is a swing-trade entry",
        help="what the analysis is for; it is quoted in every question",
    )
    analyze.add_argument("--as-of", help="analyse as of a past date (YYYY-MM-DD)")
    analyze.add_argument("--scenario", help=f"use synthetic data: {', '.join(sorted(_SCENARIOS))}")
    analyze.add_argument(
        "--live",
        action="store_true",
        help="call the real decision model (costs money; off by default)",
    )
    analyze.add_argument("--mock", action="store_true", help="explicit opposite of --live")
    analyze.add_argument(
        "--strategy",
        default="oracle",
        choices=["oracle", "uniform", "adversarial", "stuck", "malformed", "down"],
        help="mock model behaviour (default: oracle)",
    )
    analyze.add_argument("--prefer", help="comma-separated tools the mock oracle favours")
    analyze.add_argument(
        "--frames",
        metavar="DIR",
        help="serve prices from a recorded fixture directory instead of the network",
    )
    analyze.add_argument(
        "--record-frames",
        metavar="DIR",
        help="save every frame fetched, so this run can be reproduced exactly",
    )
    analyze.add_argument(
        "--enough-after",
        type=int,
        default=3,
        metavar="N",
        help="analyses the mock runs before calling the evidence sufficient; "
        "raise it to walk more of the registry (default: 3)",
    )
    analyze.add_argument(
        "--dry-run",
        action="store_true",
        help="with --live, print request bodies and send nothing",
    )
    analyze.add_argument("--config", type=Path, help="TOML configuration file")
    analyze.add_argument(
        "--set",
        action="append",
        metavar="section.key=value",
        help="override one setting; repeatable",
    )
    analyze.add_argument("--verbose", action="store_true", help="show the decision path")
    analyze.add_argument("--json", action="store_true", help="emit JSON")
    analyze.add_argument("--no-trace", action="store_true", help="do not write a trace")
    analyze.set_defaults(func=_cmd_analyze)

    tools = sub.add_parser("tools", help="list the available analyses")
    tools.add_argument("--json", action="store_true", help="emit JSON")
    tools.set_defaults(func=_cmd_tools)

    bench = sub.add_parser("bench", help="compare routing arms across the scenario set")
    bench.add_argument(
        "--arms",
        default="rules,cheapest,random,oracle",
        help="comma-separated arms to run (default: every mock arm)",
    )
    bench.add_argument(
        "--regime",
        default="budgeted",
        choices=("free", "budgeted"),
        help="budgeted caps tool calls so coverage has to be earned (default)",
    )
    bench.add_argument(
        "--reference", default="rules", help="the arm the others are compared against"
    )
    bench.add_argument("--scenario", help="run one scenario instead of all fifteen")
    bench.add_argument("--trace-dir", metavar="DIR", help="keep every run's trace")
    bench.add_argument(
        "--overwrite-traces",
        action="store_true",
        help="allow --trace-dir to replace traces already there; refused by "
        "default, since those are the only record of a paid run",
    )
    bench.add_argument("--seed", type=int, default=0, help="seed for the random arm")
    bench.add_argument(
        "--validate",
        action="store_true",
        help="only check that the metrics separate an oracle from random choices",
    )
    bench.add_argument("--calibration", action="store_true", help="also print calibration tables")
    bench.add_argument(
        "--no-verify",
        action="store_true",
        help="skip confirming each scenario's planted feature really is present",
    )
    bench.add_argument(
        "--live",
        action="store_true",
        help="allow the jev arm to call the real decision model (costs money)",
    )
    bench.add_argument("--config", help="TOML configuration file")
    bench.add_argument(
        "--set",
        action="append",
        metavar="section.key=value",
        help="override one setting; repeatable",
    )
    bench.add_argument("--json", action="store_true", help="emit JSON")
    bench.set_defaults(func=_cmd_bench)

    scenarios = sub.add_parser(
        "scenarios", help="verify the benchmark scenarios against the real detectors"
    )
    scenarios.add_argument("--json", action="store_true", help="emit JSON")
    scenarios.set_defaults(func=_cmd_scenarios)

    calibrate_cmd = sub.add_parser(
        "calibrate",
        help="score the probabilities in traces saved by bench --trace-dir",
    )
    calibrate_cmd.add_argument("traces", help="a trace file, or a directory of them")
    calibrate_cmd.add_argument("--json", action="store_true", help="emit JSON")
    calibrate_cmd.set_defaults(func=_cmd_calibrate)

    replay = sub.add_parser(
        "replay",
        help="re-decide a recorded trace and report any divergence",
    )
    replay.add_argument("trace", help="path to a run's .jsonl trace")
    replay.add_argument("--config", help="apply these thresholds instead of the ones the run used")
    replay.add_argument(
        "--set",
        action="append",
        metavar="section.key=value",
        help="override one setting; repeatable",
    )
    replay.add_argument("--json", action="store_true", help="emit JSON")
    replay.set_defaults(func=_cmd_replay)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv: Arguments, defaulting to the process arguments.

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
