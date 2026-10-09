"""The closed loop, its budgets, and the trace it leaves behind."""

import json
from datetime import date

import pytest

from stock_agent.asof import FrameProvider
from stock_agent.config import AgentConfig, BudgetConfig, PolicyConfig
from stock_agent.eval.mock_jev import MockJevClient
from stock_agent.eval.synthetic import plant_run, synth_ohlc
from stock_agent.guards import BudgetState, LoopGuard
from stock_agent.loop import run_analysis
from stock_agent.registry import ToolSpec
from stock_agent.state import AnalysisState
from stock_agent.tools.builtin import build_registry
from stock_agent.trace import read_trace

TICKER = "SYN"


def _frames(bars=400, seed=1, drift=0.30, run=0):
    frame = synth_ohlc(bars, seed=seed, drift_ann=drift, vol_ann=0.20)
    if run:
        frame = plant_run(frame, run, "green")
    return FrameProvider({TICKER: frame})


def _run(strategy="oracle", prefer=("trend.heiken_runs",), config=None, **kw):
    model = MockJevClient(strategy, preferred=list(prefer))
    result = run_analysis(
        ticker=TICKER,
        objective="whether this is a swing-trade entry",
        registry=build_registry(),
        model=model,
        provider=kw.pop("provider", _frames()),
        config=config or AgentConfig(),
        **kw,
    )
    return result, model


# --- the loop completes -----------------------------------------------------


def test_a_full_analysis_runs_and_stops_for_a_reason():
    run, model = _run()

    assert run.tools_run
    assert run.exit_reason
    assert model.calls >= 1


def test_price_history_is_fetched_without_asking():
    """Every other analysis needs it, so a question could only have one answer."""
    run, model = _run()

    assert run.tools_run[0] == "price_history.ohlc"
    assert run.decisions[0].band == "bootstrap"


def test_one_batched_request_per_decision_round():
    run, model = _run()

    deciding = [d for d in run.decisions if d.band != "bootstrap"]
    assert model.calls == len(deciding)


def test_observations_accumulate():
    run, _ = _run()

    assert len(run.state.observations) > 5
    assert run.state.has("ohlc.n_bars")


# --- every strategy terminates ----------------------------------------------


@pytest.mark.parametrize(
    "strategy",
    ["oracle", "uniform", "adversarial", "stuck", "malformed", "down"],
)
def test_every_mock_strategy_terminates(strategy):
    run, _ = _run(strategy)

    assert run.exit_reason


def test_adversarial_model_cannot_loop_forever():
    """Termination must not depend on the model being sensible."""
    run, _ = _run("adversarial", prefer=("trend.heiken_runs",))

    assert run.exit_reason
    assert run.state.iteration <= AgentConfig().budget.max_iterations


def test_model_failure_yields_a_partial_analysis_not_a_crash():
    run, _ = _run("down")

    assert run.exit_reason == "jev_error"
    assert run.partial is True
    # What was measured before the failure is still reported.
    assert run.tools_run == ["price_history.ohlc"]


def test_malformed_answers_are_treated_as_a_failure_not_guessed_at():
    run, _ = _run("malformed")

    assert run.exit_reason == "jev_error"
    assert run.partial is True


def test_indecision_terminates_the_run():
    run, _ = _run("uniform", prefer=())

    assert run.exit_reason == "repeated_indecision"


# --- budgets ----------------------------------------------------------------


def test_iteration_cap_is_enforced():
    config = AgentConfig(budget=BudgetConfig(max_iterations=2))

    run, _ = _run("stuck", config=config)

    assert run.state.iteration <= 2
    assert run.partial is True


def test_tool_call_cap_is_enforced():
    config = AgentConfig(budget=BudgetConfig(max_tool_calls=2))

    run, _ = _run("stuck", config=config)

    assert len(run.state.history) <= 3


def test_a_tool_is_not_rerun_once_satisfied():
    run, _ = _run("stuck")

    counts: dict[str, int] = {}
    for step in run.state.history:
        counts[step.tool] = counts.get(step.tool, 0) + 1
    assert max(counts.values()) <= AgentConfig().budget.max_same_tool_calls


# --- guards in isolation ----------------------------------------------------


def test_state_unchanged_compares_within_an_iteration_not_across_two():
    """Consecutive iterations trivially share a fingerprint."""
    guard = LoopGuard(BudgetConfig())

    guard.observe_iteration("aaa", "bbb")
    assert guard.check() is None

    guard.observe_iteration("ccc", "ccc")
    trip = guard.check()
    assert trip is not None and trip.reason == "state_unchanged"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("iterations", 99, "iteration_cap"),
        ("tool_calls", 99, "tool_call_cap"),
        ("jev_calls", 99, "jev_call_cap"),
        ("network_calls", 99, "network_cap"),
        ("consecutive_tool_errors", 99, "tool_failures"),
    ],
)
def test_each_budget_names_itself_when_it_trips(field, value, reason):
    state = BudgetState()
    setattr(state, field, value)
    guard = LoopGuard(BudgetConfig(), state)

    trip = guard.check()

    assert trip is not None and trip.reason == reason


def test_a_failed_tool_is_withheld_rather_than_offered_again():
    """The model cannot know a tool is broken, so the agent must not re-offer it."""
    guard = LoopGuard(BudgetConfig())
    spec = ToolSpec(name="t", category="c", title="T", jev_description="d", run=lambda ctx: None)

    guard.record_tool("t", success=False)

    assert "t" in guard.disabled
    allowed, reason = guard.may_run(spec, AnalysisState(ticker="X", objective="o"))
    assert allowed is False
    assert "failure" in reason


def test_repeat_cap_blocks_a_third_run():
    guard = LoopGuard(BudgetConfig(max_same_tool_calls=2))
    spec = ToolSpec(name="t", category="c", title="T", jev_description="d", run=lambda ctx: None)

    guard.record_tool("t", success=True)
    guard.record_tool("t", success=True)

    allowed, reason = guard.may_run(spec, AnalysisState(ticker="X", objective="o"))
    assert allowed is False
    assert "limit" in reason


# --- the trace --------------------------------------------------------------


def test_trace_has_the_three_record_types_in_order(tmp_path):
    path = tmp_path / "t.jsonl"
    _run(trace_path=path)

    records = read_trace(path)

    assert records[0]["record"] == "run_start"
    assert records[-1]["record"] == "run_end"
    assert any(r["record"] == "iteration" for r in records)


def test_trace_captures_the_questions_verbatim(tmp_path):
    path = tmp_path / "t.jsonl"
    _run(trace_path=path)

    asked = [r for r in read_trace(path) if r["record"] == "iteration" and r.get("jev_request")]

    assert asked
    questions = asked[0]["jev_request"]["questions"]
    assert any(q.startswith("useful__") for q in questions)
    # The exact text sent must be recoverable, or the trace cannot explain
    # what was asked.
    assert all("instructions" in q for q in questions.values())


def test_trace_records_why_each_tool_was_withheld(tmp_path):
    path = tmp_path / "t.jsonl"
    _run(trace_path=path)

    excluded = [
        e
        for r in read_trace(path)
        if r["record"] == "iteration"
        for e in r.get("candidates_excluded", [])
    ]

    assert excluded
    assert all(e["reason"] for e in excluded)
    assert any("not_implemented" in e["reason"] for e in excluded)


def test_trace_records_the_policy_arithmetic(tmp_path):
    path = tmp_path / "t.jsonl"
    _run(trace_path=path)

    decisions = [r["decision"] for r in read_trace(path) if r["record"] == "iteration"]

    assert all(d["rationale"] for d in decisions)


def test_trace_records_the_order_bias_comparison(tmp_path):
    path = tmp_path / "t.jsonl"
    _run(trace_path=path)

    shadows = [
        r["shadow_choice"]
        for r in read_trace(path)
        if r["record"] == "iteration" and r.get("shadow_choice")
    ]

    assert shadows
    assert "forward_picked_first_option" in shadows[0]
    assert "agrees_with_usefulness_top1" in shadows[0]


def test_trace_is_valid_jsonl(tmp_path):
    path = tmp_path / "t.jsonl"
    _run(trace_path=path)

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            json.loads(line)


def test_no_trace_is_written_when_none_is_requested(tmp_path):
    run, _ = _run(trace_path=None)

    assert run.trace_path is None
    assert list(tmp_path.iterdir()) == []


# --- point in time ----------------------------------------------------------


def test_an_asof_run_sees_no_later_bars():
    provider = _frames(bars=600)

    run, _ = _run(provider=provider, asof=date(2021, 1, 4))

    assert run.state.asof == date(2021, 1, 4)
    for frame in run.state.frames.values():
        if frame.last_bar is not None:
            assert frame.last_bar.date() <= date(2021, 1, 4)


def test_state_text_reports_the_window():
    run, model = _run(asof=date(2021, 1, 4))

    sent = [r["state"] for r in model.requests]
    assert sent
    assert "as of 2021-01-04" in sent[0]


# --- the model's view -------------------------------------------------------


def test_the_model_is_told_what_it_cannot_run():
    """Otherwise it has no way to know fundamentals are unavailable."""
    _, model = _run()

    assert model.requests
    assert "UNAVAILABLE IN THIS SYSTEM" in model.requests[0]["state"]


def test_the_model_is_told_what_remains():
    _, model = _run()

    assert "NOT YET MEASURED" in model.requests[0]["state"]


def test_no_raw_frame_reaches_the_model():
    _, model = _run()

    for request in model.requests:
        assert "Timestamp(" not in request["state"]
        assert len(request["state"]) < 4000


def test_a_short_history_withholds_the_analyses_that_need_more_bars():
    # 15 bars clears trend (>= 10) but not momentum (>= 20) or
    # volatility (>= 25). Gates are checked in Python before the model ever
    # sees the menu, so it is never asked about an analysis that cannot run.
    provider = FrameProvider({TICKER: synth_ohlc(15, seed=5)})

    run, model = _run(provider=provider)

    assert "momentum.rsi_stochastic" not in run.tools_run
    assert "volatility.realised" not in run.tools_run
    for request in model.requests:
        assert "useful__momentum__rsi_stochastic" not in request["questions"]


def test_policy_thresholds_change_behaviour():
    strict = AgentConfig(policy=PolicyConfig(act_threshold=0.99, consider_threshold=0.95))

    run, _ = _run(config=strict)

    assert run.exit_reason == "no_useful_tool"


# --- configuration overrides -------------------------------------------------


def test_a_path_setting_stays_a_path_when_overridden():
    """Found by the first live run.

    ``--set trace_dir=...`` left a plain string behind, and the first path
    join raised a TypeError after the analysis had already been paid for.
    """
    from pathlib import Path

    from stock_agent.config import load_config

    config = load_config(None, ["trace_dir=runs/elsewhere"])

    assert isinstance(config.trace_dir, Path)
    assert config.trace_dir / "x" == Path("runs/elsewhere/x")


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ("budget.max_jev_calls=4", 4),
        ("budget.max_tool_calls=2", 2),
    ],
)
def test_numeric_overrides_keep_their_type(override, expected):
    from stock_agent.config import load_config

    config = load_config(None, [override])
    section, _, key = override.partition("=")[0].partition(".")

    assert getattr(getattr(config, section), key) == expected


def test_the_trace_records_which_model_actually_answered(tmp_path):
    """A silent substitution upstream would otherwise leave no trace."""
    path = tmp_path / "t.jsonl"
    _run(trace_path=path)

    answered = [
        r["jev_response"]
        for r in read_trace(path)
        if r["record"] == "iteration" and r.get("jev_response")
    ]

    assert answered
    assert all("model_served" in r for r in answered)


# --- a slow feed cannot hang a run -------------------------------------------


def _slow_spec(seconds, network=True):
    """A tool that blocks, to stand in for a feed that will not finish."""
    import time as clock

    from stock_agent.registry import ToolCost, ToolResult, ToolSpec

    def blocking(ctx):
        clock.sleep(seconds)
        return ToolResult(tool="slow.feed", success=True, metrics={"slow.x": 1})

    return ToolSpec(
        name="slow.feed",
        category="slow",
        title="Slow feed",
        jev_description="d",
        produces=frozenset({"slow.x"}),
        cost=ToolCost(est_seconds=seconds, network=network, network_calls=1),
        run=blocking,
    )


def test_a_networked_tool_that_never_finishes_is_abandoned():
    """Found by the first live run.

    Every other budget counts calls and is tested between rounds, so none of
    them can end a tool that is still blocking. The macro snapshot sat there
    for twelve minutes on the first live run, waiting on a throttled feed.
    """
    from stock_agent.registry import ToolContext
    from stock_agent.state import AnalysisState

    spec = _slow_spec(30.0)
    state = AnalysisState(ticker=TICKER, objective="o")
    guard = LoopGuard(BudgetConfig())
    run = __import__("stock_agent.loop", fromlist=["AgentRun"]).AgentRun(state=state)

    from stock_agent.loop import _execute

    record = _execute(
        spec,
        ToolContext(state, _frames()),
        "selected",
        0,
        guard,
        run,
        deadline=0.3,
    )

    assert record["status"] == "error"
    assert "gave up after" in record["error"]
    assert record["duration_s"] < 5.0


def test_a_computed_tool_is_not_put_on_a_deadline():
    """It cannot block, and it may write an artifact a later analysis reads.

    Running it on a worker thread would race the main thread for no benefit.
    """
    from stock_agent.registry import ToolContext
    from stock_agent.state import AnalysisState

    spec = _slow_spec(0.2, network=False)
    state = AnalysisState(ticker=TICKER, objective="o")
    guard = LoopGuard(BudgetConfig())
    run = __import__("stock_agent.loop", fromlist=["AgentRun"]).AgentRun(state=state)

    from stock_agent.loop import _execute

    record = _execute(
        spec,
        ToolContext(state, _frames()),
        "selected",
        0,
        guard,
        run,
        deadline=0.01,
    )

    assert record["status"] == "ok"


def test_an_abandoned_tool_is_not_offered_again():
    from stock_agent.registry import ToolContext
    from stock_agent.state import AnalysisState

    spec = _slow_spec(30.0)
    state = AnalysisState(ticker=TICKER, objective="o")
    guard = LoopGuard(BudgetConfig())
    run = __import__("stock_agent.loop", fromlist=["AgentRun"]).AgentRun(state=state)

    from stock_agent.loop import _execute

    _execute(spec, ToolContext(state, _frames()), "selected", 0, guard, run, deadline=0.2)

    assert "slow.feed" in guard.disabled


def test_the_deadline_is_configurable():
    assert BudgetConfig().max_network_seconds > 0
    assert BudgetConfig(max_network_seconds=5.0).max_network_seconds == 5.0


def test_the_insider_tool_shortens_its_filing_window(monkeypatch):
    """The default of a year spans ~545 days of filings, fetched one by one."""
    from stock_agent.registry import ToolContext
    from stock_agent.state import AnalysisState
    from stock_agent.tools.builtin import build_registry

    seen = {}

    def spy(ticker, **kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr("stockcharts.screener.sec_insider.screen_insider_ticker", spy)
    spec = build_registry().get("events.insider")
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")

    spec.run(ToolContext(state, _frames(), spec.default_params))

    assert seen["holdings_lookback_days"] == 120
