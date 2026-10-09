"""The tool wrappers, and the registry they form together.

These tests concentrate on the ways a wrapper can be wrong *quietly*: a
default that turns a measurement into an absence, a dependency that is offered
before it can succeed, a hindsight label presented as current, and a live feed
reached during a historical replay. Each of those produces a plausible answer
rather than an error, so only a test catches it.
"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from stock_agent.asof import FrameProvider
from stock_agent.config import AgentConfig
from stock_agent.eval.mock_jev import MockJevClient
from stock_agent.eval.synthetic import synth_ohlc, synth_vix
from stock_agent.loop import run_analysis
from stock_agent.registry import ToolContext
from stock_agent.state import AnalysisState
from stock_agent.tools.builtin import build_registry

TICKER = "SYN"

# The analysis that fits a segmentation model is slow enough (around nine
# seconds) that running it in every loop test would dominate the suite. It is
# exercised once, cheaply, by test_price_regime_*.
SLOW = ("market_regime.price",)


# --- fixtures ---------------------------------------------------------------


def _provider(bars=400, seed=1, drift=0.30, vol=0.22, source="synthetic"):
    frame = synth_ohlc(bars, seed=seed, drift_ann=drift, vol_ann=vol)
    return FrameProvider(
        {
            TICKER: frame,
            "SPY": synth_ohlc(bars, seed=101, drift_ann=0.09, vol_ann=0.15, s0=400.0),
            "^VIX": synth_vix(frame),
        },
        source=source,
    )


def _ctx(tool, provider=None, state=None, **params):
    """Build a context for one tool, with its declared defaults applied."""
    spec = build_registry().get(tool)
    merged = {**spec.default_params, **params}
    held = (
        state
        if state is not None
        else AnalysisState(
            ticker=TICKER,
            objective="whether this is a swing-trade entry",
            data_source="live",
        )
    )
    return spec, ToolContext(held, provider or _provider(), merged)


def _measure(tool, provider=None, state=None, **params):
    spec, ctx = _ctx(tool, provider, state, **params)
    return spec.run(ctx)


def _stock_up(state, *tools: str, provider=None):
    """Run tools in order so a dependent tool has something to read."""
    source = provider or _provider()
    for name in tools:
        spec, ctx = _ctx(name, source, state)
        result = spec.run(ctx)
        if result.success:
            state.record(result.observations(0), spec.provenance(None, 0))
    return state


# --- the inventory ----------------------------------------------------------


def test_the_registry_holds_every_analysis_and_every_known_gap():
    registry = build_registry()

    assert [s.name for s in registry.implemented()] == [
        "events.insider",
        "macro.snapshot",
        "market_regime.price",
        "momentum.rsi_stochastic",
        "pattern.rsi_divergence",
        "price_history.ohlc",
        "relative_strength.beta_regime",
        "signal.mcglone",
        "trend.heiken_runs",
        "volatility.realised",
        "volatility.vix",
        "volume.surge",
    ]
    assert [s.name for s in registry.absent()] == [
        "backtest.replay",
        "correlation.matrix",
        "fundamentals.summary",
        "news.headlines",
        "portfolio.risk",
    ]


def test_every_absent_analysis_explains_itself():
    """The model is told what is missing, so it must be told why."""
    for spec in build_registry().absent():
        assert spec.absent_reason
        assert spec.run is None


def test_an_absent_analysis_is_named_the_way_a_reader_would_ask_for_it():
    """Its title is what appears in the model's UNAVAILABLE section."""
    titles = {s.name: s.title for s in build_registry().absent()}

    assert titles["fundamentals.summary"] == "Fundamentals (earnings, valuation, growth)"
    assert all(len(t.split()) >= 2 for t in titles.values())


def test_excluding_a_tool_removes_it_from_the_catalogue():
    registry = build_registry(exclude=SLOW)

    assert "market_regime.price" not in registry


def test_no_tool_reaches_the_price_feed_behind_the_chokepoint():
    """Direct fetching would bypass the as-of truncation and its assertion."""
    offenders = [
        path.name
        for path in Path("src/stock_agent/tools").glob("*.py")
        if "fetch_ohlc" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


# --- the dependency edge ----------------------------------------------------


def test_divergence_is_offered_before_momentum_and_pulls_it_along():
    """Dependencies are plumbing, not a routing decision.

    The model is asked whether divergence is worth measuring, not whether RSI
    needs computing first, so the tool stays on the menu and Python supplies
    what it needs.
    """
    registry = build_registry()
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")
    _stock_up(state, "price_history.ohlc")

    eligible, _ = registry.candidates(state)

    assert "pattern.rsi_divergence" in [s.name for s in eligible]
    assert registry.prerequisite_plan("pattern.rsi_divergence", state) == [
        "momentum.rsi_stochastic"
    ]


def test_a_satisfied_dependency_drops_out_of_the_plan():
    registry = build_registry()
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")
    _stock_up(state, "price_history.ohlc", "momentum.rsi_stochastic")

    assert registry.prerequisite_plan("pattern.rsi_divergence", state) == []


def test_divergence_says_so_rather_than_computing_its_own_rsi():
    """Recomputing it would hide a broken dependency behind a plausible answer."""
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")

    result = _measure("pattern.rsi_divergence", state=state)

    assert result.success is False
    assert "momentum" in result.error


def test_divergence_measures_once_rsi_is_present():
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")
    _stock_up(state, "price_history.ohlc", "momentum.rsi_stochastic")

    result = _measure("pattern.rsi_divergence", state=state)

    assert result.success is True
    assert isinstance(result.metrics["pattern.bullish_divergence"], bool)
    assert result.displays["pattern.last_signal"]


def test_a_tool_whose_prerequisite_has_failed_is_withheld_not_offered():
    """Offering it would spend a question and a tool call on a certainty."""
    registry = build_registry()
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")
    _stock_up(state, "price_history.ohlc")

    _, excluded = registry.candidates(state, exclude=["relative_strength.beta_regime"])

    reasons = dict(excluded)
    assert "prerequisite_unavailable" in reasons["signal.mcglone"]
    assert "relative_strength.beta_regime" in reasons["signal.mcglone"]


def test_blocking_is_transitive():
    registry = build_registry()
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")

    blocked = registry.unreachable_requirement(
        "pattern.rsi_divergence", state, {"price_history.ohlc"}
    )

    assert blocked is not None
    assert "price_history.ohlc" in blocked


# --- the two-frame analysis -------------------------------------------------


def test_relative_strength_measures_against_the_benchmark():
    result = _measure("relative_strength.beta_regime")

    assert result.success is True
    assert result.metrics["relative_strength.benchmark"] == "SPY"
    assert result.metrics["relative_strength.regime"] in {"risk-on", "risk-off"}
    assert "SPY" in result.displays["relative_strength.regime"]


def test_relative_strength_fetches_a_second_frame():
    provider = _provider()

    _measure("relative_strength.beta_regime", provider=provider)

    assert provider.calls >= 2


def test_relative_strength_fails_when_the_benchmark_is_unavailable():
    provider = FrameProvider({TICKER: synth_ohlc(400, seed=1)})

    result = _measure("relative_strength.beta_regime", provider=provider)

    assert result.success is False
    assert "SPY" in result.error


def test_a_ticker_is_not_compared_with_itself():
    result = _measure("relative_strength.beta_regime", benchmark=TICKER)

    assert result.success is False
    assert "itself" in result.error


# --- the retrospective analysis ---------------------------------------------


def test_price_regime_warns_the_model_that_its_label_is_hindsight():
    spec = build_registry().get("market_regime.price")

    assert spec.retrospective is True
    assert "hindsight" in spec.jev_description


def test_price_regime_attaches_the_caveat_to_every_observation():
    """A number that travels without its caveat will be read as current."""
    result = _measure("market_regime.price", max_shuffles=40)

    assert result.success is True
    assert result.caveat and "hindsight" in result.caveat
    assert all(o.caveat for o in result.observations(0).values())


def test_price_regime_labels_the_current_stretch():
    result = _measure("market_regime.price", max_shuffles=40)

    assert result.metrics["market_regime.current"] in {
        "bull",
        "bear",
        "sideways",
        "insufficient-data",
    }
    assert result.metrics["market_regime.n_segments"] >= 1


def test_price_regime_needs_enough_history():
    result = _measure("market_regime.price", provider=_provider(bars=80), max_shuffles=40)

    assert result.success is False
    assert "120" in result.error


# --- insider filings --------------------------------------------------------


def _fake_filing(**over):
    base = {
        "recent_bought_shares": 0.0,
        "recent_sold_shares": 0.0,
        "volume_ratio_increase": None,
    }
    return SimpleNamespace(**{**base, **over})


def test_insider_screening_disables_its_own_thresholds(monkeypatch):
    """Left at their defaults, unremarkable activity returns None -- which the
    state would record as "no filings found". The model cannot tell a quiet
    quarter from a missing data source, so the thresholds must be off.
    """
    seen = {}

    def spy(ticker, **kwargs):
        seen.update(kwargs)
        return _fake_filing(recent_bought_shares=1000.0)

    monkeypatch.setattr("stockcharts.screener.sec_insider.screen_insider_ticker", spy)

    result = _measure("events.insider")

    assert result.success is True
    assert seen["min_volume_increase"] is None
    assert seen["min_holding_increase"] is None


def test_insider_screening_passes_the_asof_date_through(monkeypatch):
    seen = {}

    def spy(ticker, **kwargs):
        seen.update(kwargs)
        return _fake_filing(recent_sold_shares=500.0)

    monkeypatch.setattr("stockcharts.screener.sec_insider.screen_insider_ticker", spy)
    state = AnalysisState(ticker=TICKER, objective="o", asof=date(2021, 1, 4), data_source="live")

    _measure("events.insider", state=state)

    assert seen["end_date"] == date(2021, 1, 4)


@pytest.mark.parametrize(
    ("bought", "sold", "expected"),
    [
        (1000.0, 0.0, "buying only"),
        (0.0, 1000.0, "selling only"),
        (1000.0, 500.0, "both directions"),
        (0.0, 0.0, "no open-market activity"),
    ],
)
def test_insider_direction_is_reported_plainly(monkeypatch, bought, sold, expected):
    monkeypatch.setattr(
        "stockcharts.screener.sec_insider.screen_insider_ticker",
        lambda ticker, **kw: _fake_filing(recent_bought_shares=bought, recent_sold_shares=sold),
    )

    result = _measure("events.insider")

    assert result.metrics["events.insider_direction"] == expected


def test_no_filings_is_reported_as_a_failure_not_as_no_activity(monkeypatch):
    monkeypatch.setattr(
        "stockcharts.screener.sec_insider.screen_insider_ticker",
        lambda ticker, **kw: None,
    )

    result = _measure("events.insider")

    assert result.success is False
    assert "no insider filings" in result.error


def test_a_broken_feed_does_not_end_the_run(monkeypatch):
    def explode(ticker, **kwargs):
        raise OSError("connection reset")

    monkeypatch.setattr("stockcharts.screener.sec_insider.screen_insider_ticker", explode)

    result = _measure("events.insider")

    assert result.success is False
    assert "connection reset" in result.error


# --- what is withheld, and why ----------------------------------------------


def test_the_macro_snapshot_is_withheld_from_a_replay():
    """Several of its components are revised series with no vintage source."""
    registry = build_registry()
    state = AnalysisState(ticker=TICKER, objective="o", asof=date(2021, 1, 4), data_source="live")

    _, excluded = registry.candidates(state)

    assert "asof_unsupported" in dict(excluded)["macro.snapshot"]


def test_the_macro_snapshot_refuses_a_replay_even_if_it_is_called():
    state = AnalysisState(ticker=TICKER, objective="o", asof=date(2021, 1, 4), data_source="live")

    result = _measure("macro.snapshot", state=state)

    assert result.success is False
    assert "replay" in result.error


@pytest.mark.parametrize("tool", ["macro.snapshot", "events.insider"])
def test_feeds_outside_the_price_provider_are_withheld_offline(tool):
    """A synthetic run must be genuinely offline, not nearly offline."""
    registry = build_registry()
    state = AnalysisState(ticker=TICKER, objective="o", data_source="synthetic")
    _stock_up(state, "price_history.ohlc")

    _, excluded = registry.candidates(state)

    assert "run.data_source" in dict(excluded)[tool]


def test_those_same_feeds_are_offered_on_live_data():
    registry = build_registry()
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")
    _stock_up(state, "price_history.ohlc")

    eligible = [s.name for s in registry.candidates(state)[0]]

    assert "events.insider" in eligible
    assert "macro.snapshot" in eligible


# --- volatility index, volume, and the signal that combines them ------------


def test_the_volatility_index_is_read_and_banded():
    result = _measure("volatility.vix")

    assert result.success is True
    assert result.metrics["volatility.vix"] > 0
    assert result.metrics["volatility.vix_status"] in {
        "calm",
        "elevated",
        "high fear",
        "extreme fear",
    }


def test_a_missing_volatility_index_is_a_failure_not_a_zero():
    provider = FrameProvider({TICKER: synth_ohlc(400, seed=1)})

    result = _measure("volatility.vix", provider=provider)

    assert result.success is False
    assert "^VIX" in result.error


def test_volume_surge_is_detected():
    frame = synth_ohlc(300, seed=7, volume_multipliers=[(295, 300, 6.0)])
    provider = FrameProvider({TICKER: frame})

    result = _measure("volume.surge", provider=provider)

    assert result.success is True
    assert result.metrics["volume.ratio"] > 3.0
    assert result.metrics["volume.shape"] == "sharp surge"


def test_ordinary_volume_is_called_ordinary():
    result = _measure("volume.surge")

    assert result.metrics["volume.shape"] == "normal"


def test_the_contrarian_signal_names_what_it_is_missing():
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")

    result = _measure("signal.mcglone", state=state)

    assert result.success is False
    assert "relative strength" in result.error


def test_the_contrarian_signal_fires_only_when_everything_lines_up():
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")
    # A sustained decline, so the benchmark comparison, the derived volatility
    # index and the drawdown all point the same way.
    provider = _provider(bars=400, seed=3, drift=-0.45, vol=0.40)
    _stock_up(
        state,
        "price_history.ohlc",
        "relative_strength.beta_regime",
        "volatility.realised",
        "volatility.vix",
        provider=provider,
    )

    result = _measure("signal.mcglone", provider=provider, state=state)

    assert result.success is True
    assert result.metrics["signal.conditions_met"] == 3
    assert result.metrics["signal.mcglone"] == "capitulation"


def test_the_contrarian_signal_stays_quiet_in_an_advance():
    state = AnalysisState(ticker=TICKER, objective="o", data_source="live")
    provider = _provider(bars=400, seed=1, drift=0.35, vol=0.16)
    _stock_up(
        state,
        "price_history.ohlc",
        "relative_strength.beta_regime",
        "volatility.realised",
        "volatility.vix",
        provider=provider,
    )

    result = _measure("signal.mcglone", provider=provider, state=state)

    assert result.metrics["signal.conditions_met"] <= 1
    assert result.metrics["signal.mcglone"] in {"none", "early"}


# --- the whole registry, end to end -----------------------------------------


def test_an_offline_run_exercises_most_of_the_registry():
    provider = _provider()
    registry = build_registry(exclude=SLOW)

    run = run_analysis(
        ticker=TICKER,
        objective="whether this is a swing-trade entry",
        registry=registry,
        model=MockJevClient("oracle", enough_after=99),
        provider=provider,
        config=AgentConfig(),
    )

    assert len(run.tools_run) >= 8
    assert "pattern.rsi_divergence" in run.tools_run
    assert "signal.mcglone" in run.tools_run
    # Nothing outside the price provider may be reached on synthetic data.
    assert "events.insider" not in run.tools_run
    assert "macro.snapshot" not in run.tools_run


def test_a_dependent_tool_never_runs_before_what_it_depends_on():
    provider = _provider()

    run = run_analysis(
        ticker=TICKER,
        objective="o",
        registry=build_registry(exclude=SLOW),
        model=MockJevClient("oracle", enough_after=99),
        provider=provider,
        config=AgentConfig(),
    )

    order = run.tools_run
    assert order.index("momentum.rsi_stochastic") < order.index("pattern.rsi_divergence")
    for upstream in ("relative_strength.beta_regime", "volatility.vix", "volatility.realised"):
        assert order.index(upstream) < order.index("signal.mcglone")


def test_the_synthetic_volatility_index_stays_plausible():
    """Generated independently it wandered to 5, which no real index prints."""
    index = synth_vix(synth_ohlc(400, seed=3, drift_ann=-0.40, vol_ann=0.38))

    assert index["Close"].min() >= 9.5
    assert index["Close"].max() < 150.0
    assert not index["Close"].isna().any()
    assert isinstance(index.index, pd.DatetimeIndex)
