"""Point-in-time guarantees of the price chokepoint.

These are the highest-value tests in the agent: a leak here does not crash,
it produces a confident and plausible analysis of data that did not exist
yet. Every other correctness property is recoverable by inspection; this one
is not.
"""

from datetime import date

import pandas as pd
import pytest

from stock_agent.asof import (
    OHLC_COLUMNS,
    FrameProvider,
    LeakageError,
    OhlcFrame,
    OhlcRequest,
    get_ohlc,
)


def _history(start="2015-01-02", periods=2000):
    idx = pd.bdate_range(start, periods=periods)
    return pd.DataFrame(
        {
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.0,
            "Volume": 1_000_000,
        },
        index=idx,
    )


class _LeakyProvider:
    """A provider that ignores the window entirely.

    This is not hypothetical: stockcharts' cache fast-path behaved exactly
    this way, returning its whole stored frame regardless of start or end.
    """

    source = "fixture"

    def __init__(self, frame):
        self.frame = frame
        self.calls = []

    def get(self, ticker, interval, start, end):
        self.calls.append({"ticker": ticker, "start": start, "end": end})
        return self.frame.copy()


# --- the core guarantee -----------------------------------------------------


def test_asof_truncates_a_provider_that_ignores_the_window():
    provider = _LeakyProvider(_history())

    frame = get_ohlc(OhlcRequest("SYN", bars=100, asof=date(2016, 6, 30)), provider)

    assert frame.last_bar <= pd.Timestamp("2016-06-30")
    assert frame.truncated is True


def test_leakage_raises_when_truncation_is_defeated(monkeypatch):
    """If the slice is ever removed, the assertion must still fire."""
    provider = _LeakyProvider(_history())

    # Simulate a regression that drops the truncation step.
    import stock_agent.asof as asof_mod

    real_frame = OhlcFrame
    monkeypatch.setattr(
        asof_mod,
        "OhlcFrame",
        lambda **kw: real_frame(**{**kw, "df": provider.frame}),
    )

    with pytest.raises(LeakageError, match="after as-of"):
        get_ohlc(OhlcRequest("SYN", bars=100, asof=date(2016, 6, 30)), provider)


def test_live_run_is_not_truncated():
    provider = _LeakyProvider(_history())

    frame = get_ohlc(OhlcRequest("SYN", bars=50, asof=None), provider)

    assert frame.asof is None
    assert frame.n_bars == 50


def test_end_is_never_passed_without_a_start():
    """An end-only window is dropped upstream, so never send one."""
    provider = _LeakyProvider(_history())

    get_ohlc(OhlcRequest("SYN", bars=100, asof=date(2016, 6, 30)), provider)

    assert provider.calls
    for call in provider.calls:
        if call["end"] is not None:
            assert call["start"] is not None


def test_requested_bar_count_is_respected():
    frame = get_ohlc(
        OhlcRequest("SYN", bars=120, asof=date(2018, 1, 2)),
        FrameProvider({"SYN": _history()}),
    )

    assert frame.n_bars == 120
    assert frame.sufficient is True


def test_short_history_is_reported_not_faked():
    provider = FrameProvider({"SYN": _history(periods=30)})

    frame = get_ohlc(OhlcRequest("SYN", bars=500), provider)

    assert frame.n_bars == 30
    assert frame.sufficient is False


# --- truncation equivalence: the end-to-end guarantee -----------------------


def test_asof_equals_a_physically_truncated_history():
    """An as-of run must equal a run on data that physically stops there.

    This is the property that makes a replay trustworthy: it proves the
    agent cannot behave differently merely because later bars existed in the
    source frame.
    """
    cutoff = date(2018, 6, 29)
    full = _history()
    chopped = full[full.index <= pd.Timestamp(cutoff)]

    via_asof = get_ohlc(OhlcRequest("SYN", bars=200, asof=cutoff), FrameProvider({"SYN": full}))
    via_truncation = get_ohlc(
        OhlcRequest("SYN", bars=200, asof=cutoff), FrameProvider({"SYN": chopped})
    )

    pd.testing.assert_frame_equal(via_asof.df, via_truncation.df)


# --- shape and validation ---------------------------------------------------


def test_frame_has_exactly_the_ohlc_columns():
    frame = get_ohlc(OhlcRequest("SYN", bars=10), FrameProvider({"SYN": _history()}))

    assert list(frame.df.columns) == OHLC_COLUMNS


def test_index_is_sorted_and_unique():
    scrambled = _history(periods=50)
    scrambled = pd.concat([scrambled, scrambled.iloc[:5]]).sample(frac=1, random_state=0)

    frame = get_ohlc(OhlcRequest("SYN", bars=50), FrameProvider({"SYN": scrambled}))

    assert frame.df.index.is_monotonic_increasing
    assert not frame.df.index.has_duplicates


def test_unknown_ticker_yields_an_empty_frame():
    frame = get_ohlc(OhlcRequest("NOPE", bars=10), FrameProvider({}))

    assert frame.n_bars == 0
    assert frame.first_bar is None
    assert frame.last_bar is None
    assert frame.sufficient is False


def test_missing_columns_raise():
    bad = pd.DataFrame({"Close": [1.0]}, index=pd.bdate_range("2024-01-01", periods=1))

    with pytest.raises(ValueError, match="missing columns"):
        get_ohlc(OhlcRequest("SYN", bars=1), FrameProvider({"SYN": bad}))


@pytest.mark.parametrize(
    ("kwargs", "needle"),
    [
        ({"bars": 0}, "bars"),
        ({"interval": "1h"}, "interval"),
    ],
)
def test_bad_requests_raise(kwargs, needle):
    with pytest.raises(ValueError, match=needle):
        OhlcRequest("SYN", **kwargs)


# --- live provider wiring ---------------------------------------------------


def test_live_provider_disables_cache_for_historical_requests(monkeypatch):
    """A warm cache can hold bars past the as-of date, so it is refused."""
    seen = {}

    def fake_fetch(ticker, **kwargs):
        seen.update(kwargs)
        return _history(periods=50)

    monkeypatch.setattr("stockcharts.data.fetch.fetch_ohlc", fake_fetch)
    from stock_agent.asof import LiveProvider

    get_ohlc(OhlcRequest("AAPL", bars=20, asof=date(2016, 1, 4)), LiveProvider())

    assert seen["use_cache"] is False
    assert seen["start"] is not None
    assert seen["end"] == "2016-01-04"


def test_live_provider_keeps_cache_for_live_requests(monkeypatch):
    seen = {}

    def fake_fetch(ticker, **kwargs):
        seen.update(kwargs)
        return _history(periods=50)

    monkeypatch.setattr("stockcharts.data.fetch.fetch_ohlc", fake_fetch)
    from stock_agent.asof import LiveProvider

    get_ohlc(OhlcRequest("AAPL", bars=20, asof=None), LiveProvider())

    # Nothing to leak when there is no as-of, so caching stays on.
    assert seen["use_cache"] is True


# --- the widening retry -----------------------------------------------------


class _CountingProvider:
    """Honours the window, and counts how often it is asked."""

    source = "fixture"

    def __init__(self, frame):
        self.frame = frame
        self.windows = []

    def get(self, ticker, interval, start, end):
        self.windows.append((start, end))
        out = self.frame
        if start is not None:
            out = out[out.index >= pd.Timestamp(start)]
        if end is not None:
            out = out[out.index <= pd.Timestamp(end)]
        return out.copy()


def test_a_short_window_is_widened_until_it_holds_enough():
    """The calendar-day estimate is an estimate; holidays make it optimistic."""
    # Bars only on Mondays, so roughly a fifth of the bars per calendar day
    # that the daily estimate assumes.
    sparse = _history(periods=2000)
    sparse = sparse[sparse.index.dayofweek == 0]
    provider = _CountingProvider(sparse)

    frame = get_ohlc(OhlcRequest("SYN", bars=200, asof=date(2019, 12, 30)), provider)

    assert frame.n_bars == 200
    assert frame.fetch_calls > 1
    assert len(provider.windows) == frame.fetch_calls


def test_an_empty_window_is_retried_rather_than_accepted():
    """A window that catches no bars at all is the strongest case for widening."""
    monthly = _history(periods=3000)
    monthly = monthly[monthly.index.day <= 2]
    provider = _CountingProvider(monthly[monthly.index <= pd.Timestamp("2016-01-01")])

    frame = get_ohlc(OhlcRequest("SYN", bars=20, asof=date(2015, 12, 31)), provider)

    assert frame.fetch_calls > 1
    assert frame.n_bars > 0


def test_widening_stops_once_it_stops_helping():
    provider = FrameProvider({"SYN": _history(periods=40)})

    frame = get_ohlc(OhlcRequest("SYN", bars=500), provider)

    assert frame.n_bars == 40
    assert frame.sufficient is False
    # Bounded: it must not keep widening against a provider that has no more.
    assert provider.calls <= 3


def test_data_from_another_era_yields_nothing_rather_than_endless_widening():
    """Asking for this month's bars of a series that stopped in 2015.

    An honest provider returns nothing, and that is the right answer: the
    bars asked for do not exist. Widening must not chase them indefinitely.
    """
    provider = _CountingProvider(_history(start="2015-01-02", periods=40))

    frame = get_ohlc(OhlcRequest("SYN", bars=500), provider)

    assert frame.n_bars == 0
    assert frame.fetch_calls <= len(provider.windows) <= 3


def test_no_second_call_when_a_full_window_still_starts_late():
    """Re-asking cannot conjure bars from before the series began."""
    provider = _CountingProvider(_history(start="2022-06-01", periods=600))

    frame = get_ohlc(OhlcRequest("SYN", bars=500, asof=date(2023, 12, 29)), provider)

    # Most of the window came back, and it still begins after the requested
    # start, so there is demonstrably nothing earlier.
    assert frame.n_bars >= 250
    assert frame.n_bars < 500
    assert frame.fetch_calls == 1


def test_an_ambiguous_short_window_widens_rather_than_assuming_the_worst():
    """Two of twenty bars could be a late start or a sparse series."""
    provider = _CountingProvider(_history(start="2015-01-02", periods=600))

    frame = get_ohlc(OhlcRequest("SYN", bars=500, asof=date(2015, 2, 2)), provider)

    assert frame.fetch_calls > 1


# --- post-conditions on the frame itself ------------------------------------


def test_prices_arriving_as_strings_are_coerced_not_compared_as_text():
    """A string column turns every later comparison into a lexicographic one."""
    text = _history(periods=30).astype(str)

    frame = get_ohlc(OhlcRequest("SYN", bars=30), FrameProvider({"SYN": text}))

    assert frame.n_bars == 30
    assert frame.df["Close"].dtype.kind == "f"
    assert frame.df["Close"].iloc[-1] == 100.0


def test_rows_with_no_close_are_dropped_rather_than_carried():
    holed = _history(periods=30).copy()
    holed.iloc[5:8, holed.columns.get_loc("Close")] = None

    frame = get_ohlc(OhlcRequest("SYN", bars=30), FrameProvider({"SYN": holed}))

    assert frame.n_bars == 27
    assert not frame.df["Close"].isna().any()


def test_an_unparseable_index_entry_is_discarded():
    bad = _history(periods=10)
    bad.index = [*[str(d.date()) for d in bad.index[:-1]], "not-a-date"]

    frame = get_ohlc(OhlcRequest("SYN", bars=10), FrameProvider({"SYN": bad}))

    assert frame.n_bars == 9
    assert isinstance(frame.df.index, pd.DatetimeIndex)


def test_staleness_is_measured_against_the_window_not_today():
    frame = get_ohlc(
        OhlcRequest("SYN", bars=50, asof=date(2016, 6, 30)),
        FrameProvider({"SYN": _history()}),
    )

    # The fixture has bars right up to the cut, so nothing is missing.
    assert frame.staleness_days == 0


def test_data_ending_early_is_reported_as_stale_not_as_a_leak():
    """A replay answering with year-old prices is a different failure from a leak."""
    ends_early = _history(start="2015-01-02", periods=100)

    frame = get_ohlc(
        OhlcRequest("SYN", bars=50, asof=date(2017, 1, 3)),
        FrameProvider({"SYN": ends_early}, source="live"),
    )

    assert frame.staleness_days > 500
    assert frame.stale is True
    assert frame.last_bar <= pd.Timestamp("2017-01-03")


def test_a_synthetic_frame_is_never_called_stale():
    """Fixture data sits on a fictional calendar, so its age means nothing."""
    frame = get_ohlc(
        OhlcRequest("SYN", bars=50, asof=date(2017, 1, 3)),
        FrameProvider({"SYN": _history(periods=100)}),
    )

    assert frame.staleness_days > 500
    assert frame.stale is False


# --- the second line of defence ---------------------------------------------


def test_audit_catches_a_frame_that_arrived_outside_the_chokepoint():
    """No care inside get_ohlc can stop a tool fetching data some other way."""
    from stock_agent.asof import audit_frames

    clean = get_ohlc(
        OhlcRequest("SYN", bars=20, asof=date(2016, 6, 30)),
        FrameProvider({"SYN": _history()}),
    )
    smuggled = get_ohlc(OhlcRequest("SYN", bars=20), FrameProvider({"SYN": _history()}))

    audit_frames({"ok": clean}, date(2016, 6, 30))

    with pytest.raises(LeakageError, match="outside get_ohlc"):
        audit_frames({"ok": clean, "smuggled": smuggled}, date(2016, 6, 30))


def test_audit_checks_nothing_on_a_live_run():
    from stock_agent.asof import audit_frames

    frame = get_ohlc(OhlcRequest("SYN", bars=20), FrameProvider({"SYN": _history()}))

    audit_frames({"any": frame}, None)


# --- recording and replaying price data -------------------------------------


def test_a_recorded_run_can_be_served_back_from_disk(tmp_path):
    from stock_agent.asof import FixtureProvider, RecordingProvider

    live = FrameProvider({"SYN": _history(periods=300), "^VIX": _history(periods=300)})
    recorder = RecordingProvider(live, tmp_path / "frames")

    for ticker in ("SYN", "^VIX"):
        get_ohlc(OhlcRequest(ticker, bars=100), recorder)

    fixtures = FixtureProvider(tmp_path / "frames")
    assert fixtures.available() == ["SYN", "^VIX"]

    original = get_ohlc(OhlcRequest("SYN", bars=100), live)
    recovered = get_ohlc(OhlcRequest("SYN", bars=100), fixtures)

    # The CSV round trip does not preserve the index's inferred frequency,
    # which is metadata no tool reads.
    pd.testing.assert_frame_equal(original.df, recovered.df, check_freq=False)
    assert recovered.source == "fixture"


def test_recording_keeps_the_longer_frame_when_a_retry_fetches_twice(tmp_path):
    from stock_agent.asof import FixtureProvider, RecordingProvider

    sparse = _history(periods=2000)
    sparse = sparse[sparse.index.dayofweek == 0]
    recorder = RecordingProvider(_CountingProvider(sparse), tmp_path / "frames")

    frame = get_ohlc(OhlcRequest("SYN", bars=200, asof=date(2019, 12, 30)), recorder)

    assert frame.fetch_calls > 1
    recovered = FixtureProvider(tmp_path / "frames").get("SYN", "1d", None, None)
    assert len(recovered) >= frame.n_bars


def test_a_missing_fixture_directory_is_an_error_not_an_empty_run(tmp_path):
    from stock_agent.asof import FixtureProvider

    with pytest.raises(FileNotFoundError, match="no fixture directory"):
        FixtureProvider(tmp_path / "never-recorded")


def test_an_unrecorded_ticker_yields_an_empty_frame(tmp_path):
    from stock_agent.asof import FixtureProvider, RecordingProvider

    recorder = RecordingProvider(FrameProvider({"SYN": _history(periods=50)}), tmp_path / "frames")
    get_ohlc(OhlcRequest("SYN", bars=50), recorder)

    frame = get_ohlc(OhlcRequest("OTHER", bars=50), FixtureProvider(tmp_path / "frames"))

    assert frame.n_bars == 0
