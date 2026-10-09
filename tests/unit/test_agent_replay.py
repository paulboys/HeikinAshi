"""Reproducing a recorded run, and proving a replay sees no future bars.

Two separate guarantees share this file because both are about a run being
reproducible:

* **Truncation equivalence** -- a run at ``as_of=D`` must be indistinguishable
  from a run on data that physically stops at D. Without it, "as of" is a
  label rather than a property, and every historical result is suspect.
* **Decision replay** -- re-running the policy over a recorded trace must
  reach the same decisions. This is the regression test for ``policy.py`` as
  it was actually exercised, rather than as a table of cases someone thought
  to write down.
"""

import json
from datetime import date

import pandas as pd
import pytest

from stock_agent.asof import FrameProvider, LeakageError
from stock_agent.config import AgentConfig, PolicyConfig
from stock_agent.eval.mock_jev import MockJevClient
from stock_agent.eval.synthetic import synth_ohlc, synth_vix
from stock_agent.loop import run_analysis
from stock_agent.replay import replay_trace
from stock_agent.tools.builtin import build_registry
from stock_agent.trace import read_trace

TICKER = "SYN"
CUTOFF = date(2021, 1, 4)

# The segmentation fit takes around nine seconds, which would dominate this
# file. It is covered on its own in test_price_regime_is_truncation_equivalent.
SLOW = ("market_regime.price",)


def _frames(bars=600, seed=1, drift=0.25, vol=0.24):
    frame = synth_ohlc(bars, seed=seed, drift_ann=drift, vol_ann=vol)
    return {
        TICKER: frame,
        "SPY": synth_ohlc(bars, seed=101, drift_ann=0.09, vol_ann=0.15, s0=400.0),
        "^VIX": synth_vix(frame),
    }


def _chop(frames, cutoff):
    """Physically remove every bar after a date."""
    limit = pd.Timestamp(cutoff)
    return {k: v[v.index <= limit].copy() for k, v in frames.items()}


def _run(frames, asof=CUTOFF, exclude=SLOW, trace_path=None, enough_after=99):
    return run_analysis(
        ticker=TICKER,
        objective="whether this is a swing-trade entry",
        registry=build_registry(exclude=exclude),
        model=MockJevClient("oracle", enough_after=enough_after),
        provider=FrameProvider(frames),
        config=AgentConfig(),
        asof=asof,
        trace_path=trace_path,
    )


# --- truncation equivalence -------------------------------------------------


def test_an_asof_run_reaches_the_same_observations_as_a_truncated_one():
    """The property that makes a replay trustworthy.

    If these diverge, the agent behaves differently merely because later bars
    existed in the source frame -- which is leakage whether or not any single
    tool can be shown to have read them.
    """
    full = _frames()

    via_asof = _run(full)
    via_truncation = _run(_chop(full, CUTOFF))

    assert via_asof.tools_run == via_truncation.tools_run
    assert {k: o.value for k, o in via_asof.state.observations.items()} == {
        k: o.value for k, o in via_truncation.state.observations.items()
    }


def test_an_asof_run_takes_the_same_decisions_as_a_truncated_one():
    full = _frames()

    via_asof = _run(full)
    via_truncation = _run(_chop(full, CUTOFF))

    assert [(d.band, d.selected) for d in via_asof.decisions] == [
        (d.band, d.selected) for d in via_truncation.decisions
    ]
    assert via_asof.exit_reason == via_truncation.exit_reason


def test_the_two_runs_fingerprint_identically():
    """A content hash over everything known, so nothing escapes the comparison."""
    from stock_agent.state import state_hash

    full = _frames()

    assert state_hash(_run(full).state) == state_hash(_run(_chop(full, CUTOFF)).state)


def test_the_model_is_shown_identical_text_either_way():
    """Equal conclusions from unequal prompts would be luck, not equivalence."""
    full = _frames()

    live_side = MockJevClient("oracle", enough_after=99)
    chopped_side = MockJevClient("oracle", enough_after=99)
    for frames, model in ((full, live_side), (_chop(full, CUTOFF), chopped_side)):
        run_analysis(
            ticker=TICKER,
            objective="o",
            registry=build_registry(exclude=SLOW),
            model=model,
            provider=FrameProvider(frames),
            config=AgentConfig(),
            asof=CUTOFF,
        )

    assert [r["state"] for r in live_side.requests] == [r["state"] for r in chopped_side.requests]


def test_price_regime_is_truncation_equivalent():
    """Checked on its own: it fits over the whole window, so it is the tool
    most able to notice bars it should not see.
    """
    from stock_agent.registry import ToolContext
    from stock_agent.state import AnalysisState

    spec = build_registry().get("market_regime.price")
    full = _frames()
    results = []
    for frames in (full, _chop(full, CUTOFF)):
        state = AnalysisState(ticker=TICKER, objective="o", asof=CUTOFF)
        results.append(
            spec.run(
                ToolContext(state, FrameProvider(frames), {"min_segment": 21, "max_shuffles": 40})
            )
        )

    assert results[0].success is True
    assert results[0].metrics == results[1].metrics


def test_a_live_run_and_an_asof_run_are_not_the_same_thing():
    """Guards the equivalence tests above against passing vacuously."""
    full = _frames()

    historical = _run(full, asof=CUTOFF)
    live = _run(full, asof=None)

    assert historical.state.value("ohlc.last_date") != live.state.value("ohlc.last_date")


# --- the second line of defence, in the loop --------------------------------


def test_a_tool_that_smuggles_in_future_bars_fails_the_run():
    """No care inside the chokepoint can stop a tool fetching data elsewhere."""
    from stock_agent.registry import ToolResult, ToolSpec

    frames = _frames()

    def smuggle(ctx):
        # Exactly what a tool importing fetch_ohlc directly would produce.
        ctx.state.frames["smuggled"] = type("Frame", (), {"last_bar": pd.Timestamp("2021-12-31")})()
        return ToolResult(tool="rogue.tool", success=True, metrics={"rogue.x": 1})

    registry = build_registry(exclude=SLOW)
    rogue = ToolSpec(
        name="rogue.tool",
        category="rogue",
        title="Rogue",
        jev_description="d",
        produces=frozenset({"rogue.x"}),
        run=smuggle,
    )
    from stock_agent.registry import ToolRegistry

    with pytest.raises(LeakageError, match="outside get_ohlc"):
        run_analysis(
            ticker=TICKER,
            objective="o",
            registry=ToolRegistry([*registry.all(), rogue]),
            model=MockJevClient("oracle", preferred=["rogue.tool"]),
            provider=FrameProvider(frames),
            config=AgentConfig(),
            asof=CUTOFF,
        )


# --- replaying the decisions ------------------------------------------------


def test_a_recorded_run_replays_to_the_same_decisions(tmp_path):
    path = tmp_path / "t.jsonl"
    original = _run(_frames(), trace_path=path)

    report = replay_trace(path)

    assert report.identical
    assert report.iterations_replayed >= 2
    assert report.ticker == TICKER
    assert len(original.decisions) == (report.iterations_replayed + report.iterations_skipped)


def test_replay_reports_the_thresholds_it_used(tmp_path):
    path = tmp_path / "t.jsonl"
    _run(_frames(), trace_path=path)

    assert replay_trace(path).config_source == "trace"
    assert replay_trace(path, PolicyConfig()).config_source == "caller"


def test_replay_names_the_iteration_that_diverges(tmp_path):
    """Changing a threshold must show up as a divergence, not pass quietly."""
    path = tmp_path / "t.jsonl"
    _run(_frames(), trace_path=path)

    report = replay_trace(path, PolicyConfig(act_threshold=0.99, consider_threshold=0.98))

    assert not report.identical
    assert report.diffs
    first = report.diffs[0]
    assert first.iteration >= 0
    assert first.field_name in {"band", "selected", "top1"}
    assert str(first).startswith("iteration ")


def test_the_bootstrap_round_has_nothing_to_replay(tmp_path):
    """Price history is fetched without asking, so no decision was made."""
    path = tmp_path / "t.jsonl"
    _run(_frames(), trace_path=path)

    assert replay_trace(path).iterations_skipped >= 1


def test_a_failed_decision_model_replays_as_a_failure(tmp_path):
    path = tmp_path / "t.jsonl"
    run_analysis(
        ticker=TICKER,
        objective="o",
        registry=build_registry(exclude=SLOW),
        model=MockJevClient("down"),
        provider=FrameProvider(_frames()),
        config=AgentConfig(),
        asof=CUTOFF,
        trace_path=path,
    )

    report = replay_trace(path)

    assert report.identical


@pytest.mark.parametrize("strategy", ["oracle", "uniform", "adversarial", "stuck"])
def test_every_mock_strategy_replays_exactly(tmp_path, strategy):
    """The policy must be reproducible from the trace on every branch it takes."""
    path = tmp_path / f"{strategy}.jsonl"
    run_analysis(
        ticker=TICKER,
        objective="o",
        registry=build_registry(exclude=SLOW),
        model=MockJevClient(strategy, preferred=["trend.heiken_runs"]),
        provider=FrameProvider(_frames()),
        config=AgentConfig(),
        asof=CUTOFF,
        trace_path=path,
    )

    report = replay_trace(path)

    assert report.identical, [str(d) for d in report.diffs]


def test_replaying_something_that_is_not_a_trace_is_an_error(tmp_path):
    path = tmp_path / "notes.jsonl"
    path.write_text(json.dumps({"record": "something_else"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not a trace"):
        replay_trace(path)


def test_a_trace_carries_everything_a_replay_needs(tmp_path):
    """If a field is ever dropped from the record, this is what catches it."""
    path = tmp_path / "t.jsonl"
    _run(_frames(), trace_path=path)
    records = read_trace(path)

    start = next(r for r in records if r["record"] == "run_start")
    assert start["config"]["policy"]
    assert all("cost" in t for t in start["registry"]["tools"])

    for record in (r for r in records if r["record"] == "iteration"):
        if record["decision"]["band"] == "bootstrap":
            continue
        assert "usefulness" in record["parsed"]
        assert "enough" in record["parsed"]
        assert "conflict" in record["parsed"]


def test_divergence_is_counted_in_rounds_not_fields(tmp_path):
    """One changed branch alters the band, the selection and the top choice."""
    path = tmp_path / "t.jsonl"
    _run(_frames(), trace_path=path)

    report = replay_trace(path, PolicyConfig(act_threshold=0.99, consider_threshold=0.98))

    assert report.diverging_iterations <= report.iterations_replayed
    assert len(report.diffs) >= report.diverging_iterations
    assert f"of {report.iterations_replayed} decisions" in report.summary()
