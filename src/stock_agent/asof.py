"""The single chokepoint through which every tool obtains price data.

Point-in-time correctness is the property most easily lost and hardest to
notice losing: a replay that quietly sees future bars produces confident,
plausible, worthless results.  Rather than trusting each tool to be careful,
all price access funnels through :func:`get_ohlc`, which slices to the
requested window and then *asserts* that nothing later survived.

Tools must never import ``fetch_ohlc`` directly; a test enforces that.

Public API:
    OhlcRequest, OhlcFrame, PriceProvider, LeakageError
    LiveProvider, FrameProvider, RecordingProvider, FixtureProvider
    get_ohlc(req: OhlcRequest, provider: PriceProvider) -> OhlcFrame
    audit_frames(frames, asof) -> None
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import pandas as pd

__all__ = [
    "FixtureProvider",
    "FrameProvider",
    "LeakageError",
    "LiveProvider",
    "OhlcFrame",
    "OhlcRequest",
    "PriceProvider",
    "RecordingProvider",
    "audit_frames",
    "fixture_name",
    "get_ohlc",
]

OHLC_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# Calendar days per bar, used to turn "N bars ending at D" into a start date.
# Generous on purpose: asking for too much history is cheap, asking for too
# little means a silent short frame.
_CALENDAR_PER_BAR: dict[str, float] = {"1d": 1.55, "1wk": 7.3, "1mo": 31.0}

# Multipliers tried, in order, when the first window comes back short. The
# calendar-day estimate above is only an estimate: holidays, trading halts and
# thinly traded names all produce fewer bars per calendar day than expected.
_WIDEN_STEPS: tuple[float, ...] = (2.5, 6.0)

# How many of the series' own bar gaps may sit between the window's start and
# its first bar before we conclude the provider has nothing earlier. Measured
# against the observed cadence rather than the assumed one: a series that
# prints weekly bars on a daily interval leaves a fortnight-wide gap at the
# start of every window, which says nothing about where its history begins.
_ORIGIN_TOLERANCE_GAPS = 3.0

# The guard is only trusted when the window came back at least this full. A
# response holding two of twenty bars says the calendar-day estimate missed,
# not that the series begins late -- and claiming origin there would silently
# return a short frame, which is far worse than paying for one more call.
_ORIGIN_MIN_FILL = 0.5

# How many bars' worth of calendar days the data may fall short of the
# window's end before it is called stale.
_STALE_AFTER_BARS = 5.0


class LeakageError(RuntimeError):
    """Raised when a frame contains bars later than the requested as-of date.

    This is deliberately an error rather than a warning. A leak that is merely
    logged becomes a quietly wrong backtest; a leak that raises becomes a test
    failure.
    """


@dataclass(frozen=True)
class OhlcRequest:
    """A request for price history, optionally as of a historical date.

    Attributes:
        ticker: Symbol to fetch.
        interval: Bar aggregation, one of ``1d``, ``1wk``, ``1mo``.
        bars: Number of bars wanted, counting back from ``asof``.
        asof: Inclusive last date. None means live, with no truncation.
    """

    ticker: str
    interval: str = "1d"
    bars: int = 504
    asof: date | None = None

    def __post_init__(self) -> None:
        """Validate the request.

        Raises:
            ValueError: If ``bars`` is below one or ``interval`` is unknown.
        """
        if self.bars < 1:
            raise ValueError(f"bars must be >= 1, got {self.bars}")
        if self.interval not in _CALENDAR_PER_BAR:
            raise ValueError(
                f"unsupported interval {self.interval!r}; "
                f"expected one of {sorted(_CALENDAR_PER_BAR)}"
            )


@dataclass(frozen=True)
class OhlcFrame:
    """Price history plus the provenance needed to audit it.

    Attributes:
        df: Bars, with exactly the OHLC columns, sorted and truncated.
        ticker: Symbol the bars belong to.
        interval: Bar aggregation.
        asof: The as-of date honoured, if any.
        requested_bars: Bars asked for.
        truncated: Whether anything was removed by the as-of cut.
        source: Where the data came from.
        fetch_calls: Provider calls it took to assemble this frame, so a
            widening retry is visible in the trace rather than hidden in the
            network bill.
        anchor: The date the window ends at -- ``asof``, or the day the live
            fetch happened. Staleness is measured against it.
    """

    df: pd.DataFrame
    ticker: str
    interval: str
    asof: date | None
    requested_bars: int
    truncated: bool
    source: Literal["live", "synthetic", "fixture", "replay"]
    fetch_calls: int = 1
    anchor: date | None = None

    @property
    def n_bars(self) -> int:
        """Return the number of bars held.

        Returns:
            Row count.
        """
        return len(self.df)

    @property
    def first_bar(self) -> pd.Timestamp | None:
        """Return the earliest bar's timestamp.

        Returns:
            The first index entry, or None when empty.
        """
        return None if self.df.empty else pd.Timestamp(self.df.index[0])

    @property
    def last_bar(self) -> pd.Timestamp | None:
        """Return the latest bar's timestamp.

        Returns:
            The last index entry, or None when empty.
        """
        return None if self.df.empty else pd.Timestamp(self.df.index[-1])

    @property
    def sufficient(self) -> bool:
        """Return whether the frame holds as many bars as were requested.

        Returns:
            True when at least ``requested_bars`` rows are present.
        """
        return self.n_bars >= self.requested_bars

    @property
    def staleness_days(self) -> int | None:
        """Return how far the last bar falls short of the window's end.

        A replay whose data stops a year before its as-of date is not leaking,
        but it is not answering the question asked either. That is a distinct
        failure from a leak and has to be visible as one.

        Returns:
            Days between the last bar and the anchor, or None when the frame
            is empty or has no anchor to measure against.
        """
        if self.anchor is None or self.last_bar is None:
            return None
        return max(0, (self.anchor - self.last_bar.date()).days)

    @property
    def stale(self) -> bool:
        """Report whether the data ends suspiciously early.

        Only meaningful for live data: a synthetic or fixture frame sits on a
        fictional calendar, so its distance from today means nothing.

        Returns:
            True when live data ends more than a few bars' worth of calendar
            days before the window's end.
        """
        gap = self.staleness_days
        if gap is None or self.source != "live":
            return False
        return gap > _CALENDAR_PER_BAR[self.interval] * _STALE_AFTER_BARS


@runtime_checkable
class PriceProvider(Protocol):
    """Source of raw price history.

    Implementations need not honour the window precisely; :func:`get_ohlc`
    slices and verifies. They must return the standard OHLC columns.
    """

    source: Literal["live", "synthetic", "fixture", "replay"]

    def get(
        self,
        ticker: str,
        interval: str,
        start: str | None,
        end: str | None,
    ) -> pd.DataFrame:
        """Return bars for a ticker over a window.

        Args:
            ticker: Symbol to fetch.
            interval: Bar aggregation.
            start: Inclusive start date as ``YYYY-MM-DD``, if any.
            end: Inclusive end date as ``YYYY-MM-DD``, if any.

        Returns:
            A frame with the OHLC columns, indexed by date.
        """
        ...


class LiveProvider:
    """Price history from the network, via stockcharts.

    Caching is disabled whenever an as-of date is set. The cache holds one
    frame per (ticker, interval) regardless of the window it was fetched for,
    so serving a historical request from it risks returning later bars; the
    chokepoint would catch that, but refusing the cache avoids the round trip.
    """

    source: Literal["live", "synthetic", "fixture", "replay"] = "live"

    def __init__(self) -> None:
        """Record how many network calls this provider has made."""
        self.calls = 0

    def get(
        self,
        ticker: str,
        interval: str,
        start: str | None,
        end: str | None,
    ) -> pd.DataFrame:
        """Fetch bars through stockcharts.

        Args:
            ticker: Symbol to fetch.
            interval: Bar aggregation.
            start: Inclusive start date, if any.
            end: Inclusive end date, if any.

        Returns:
            A frame with the OHLC columns, or an empty frame on failure.
        """
        from stockcharts.data.fetch import fetch_ohlc

        self.calls += 1
        frame = fetch_ohlc(
            ticker,
            interval=interval,
            start=start,
            end=end,
            use_cache=end is None,
        )
        return frame if frame is not None else pd.DataFrame(columns=OHLC_COLUMNS)


class FrameProvider:
    """Serves pre-built frames, for synthetic scenarios and fixtures."""

    def __init__(
        self,
        frames: dict[str, pd.DataFrame],
        source: Literal["live", "synthetic", "fixture", "replay"] = "synthetic",
    ) -> None:
        """Create a provider over in-memory frames.

        Args:
            frames: Mapping of ticker to its full history.
            source: Provenance label recorded on every frame served.
        """
        self._frames = frames
        self.source = source
        self.calls = 0

    def get(
        self,
        ticker: str,
        interval: str,
        start: str | None,
        end: str | None,
    ) -> pd.DataFrame:
        """Return the stored frame for a ticker.

        The window is deliberately ignored so that :func:`get_ohlc`'s
        truncation and leak check are exercised rather than bypassed.

        Args:
            ticker: Symbol to look up.
            interval: Bar aggregation, unused.
            start: Inclusive start date, unused.
            end: Inclusive end date, unused.

        Returns:
            The stored frame, or an empty frame when the ticker is unknown.
        """
        self.calls += 1
        frame = self._frames.get(ticker)
        return pd.DataFrame(columns=OHLC_COLUMNS) if frame is None else frame.copy()


def _start_for(req: OhlcRequest, widen: float = 1.0) -> str:
    """Compute the start date that should yield the requested bar count.

    Args:
        req: The request being served.
        widen: Multiplier applied when a first attempt came back short.

    Returns:
        A ``YYYY-MM-DD`` start date.
    """
    anchor = req.asof or date.today()
    span = req.bars * _CALENDAR_PER_BAR[req.interval] * widen + 10
    return (anchor - timedelta(days=int(span))).isoformat()


class RecordingProvider:
    """Wraps a provider and saves everything it serves.

    A live run is not reproducible: prices are revised, splits are applied
    retroactively, and a delisted ticker stops answering. Recording each
    frame as it is served turns one live run into a fixture that every later
    comparison can share, which is what makes an A-versus-B benchmark a
    comparison of routers rather than of download days.

    The raw frame is written, before truncation, so a recording made for one
    as-of date can serve an earlier one.
    """

    def __init__(self, inner: PriceProvider, directory: Path) -> None:
        """Create a recording wrapper.

        Args:
            inner: The provider doing the real work.
            directory: Where frames are written.
        """
        self.inner = inner
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.source: Literal["live", "synthetic", "fixture", "replay"] = getattr(
            inner, "source", "live"
        )
        self.calls = 0
        self.written: list[Path] = []

    def get(
        self,
        ticker: str,
        interval: str,
        start: str | None,
        end: str | None,
    ) -> pd.DataFrame:
        """Fetch through the wrapped provider and save the result.

        Args:
            ticker: Symbol to fetch.
            interval: Bar aggregation.
            start: Inclusive start date, if any.
            end: Inclusive end date, if any.

        Returns:
            Whatever the wrapped provider returned, unchanged.
        """
        self.calls += 1
        frame = self.inner.get(ticker, interval, start, end)
        if frame is not None and not frame.empty:
            path = self.directory / fixture_name(ticker, interval)
            # A widening retry calls twice for the same ticker; the longer
            # frame is the one worth keeping.
            if not path.exists() or len(_read_fixture(path)) < len(frame):
                frame.to_csv(path)
                if path not in self.written:
                    self.written.append(path)
        return frame


class FixtureProvider:
    """Serves frames recorded earlier by :class:`RecordingProvider`."""

    source: Literal["live", "synthetic", "fixture", "replay"] = "fixture"

    def __init__(self, directory: Path) -> None:
        """Open a fixture directory.

        Args:
            directory: Where recorded frames live.

        Raises:
            FileNotFoundError: If the directory does not exist, which usually
                means a benchmark was pointed at a recording never made.
        """
        self.directory = Path(directory)
        if not self.directory.is_dir():
            raise FileNotFoundError(f"no fixture directory at {self.directory}")
        self.calls = 0

    def available(self) -> list[str]:
        """List the tickers this directory can serve.

        Returns:
            Ticker symbols, in sorted order.
        """
        return sorted(
            path.stem.split("__")[0].replace("_CARET_", "^")
            for path in self.directory.glob("*.csv")
        )

    def get(
        self,
        ticker: str,
        interval: str,
        start: str | None,
        end: str | None,
    ) -> pd.DataFrame:
        """Return a recorded frame.

        The window is ignored, as with any fixture: :func:`get_ohlc` does the
        truncation, so the recording is exercised through the same code path
        as live data.

        Args:
            ticker: Symbol to look up.
            interval: Bar aggregation.
            start: Inclusive start date, unused.
            end: Inclusive end date, unused.

        Returns:
            The recorded frame, or an empty frame when none was recorded.
        """
        self.calls += 1
        path = self.directory / fixture_name(ticker, interval)
        if not path.exists():
            return pd.DataFrame(columns=OHLC_COLUMNS)
        return _read_fixture(path)


def fixture_name(ticker: str, interval: str) -> str:
    """Build the on-disk name for one recorded series.

    Args:
        ticker: Symbol, which may contain characters a filename cannot.
        interval: Bar aggregation.

    Returns:
        A filename safe on every platform.
    """
    safe = ticker.replace("^", "_CARET_").replace("/", "_SLASH_").replace("=", "_EQ_")
    return f"{safe}__{interval}.csv"


def _read_fixture(path: Path) -> pd.DataFrame:
    """Read one recorded frame back.

    Args:
        path: Recorded CSV.

    Returns:
        The frame, indexed by date.
    """
    return pd.read_csv(path, index_col=0, parse_dates=True)


def audit_frames(frames: dict[str, object], asof: date | None) -> None:
    """Verify that nothing in a run's accumulated frames postdates the as-of.

    :func:`get_ohlc` already guarantees this for every frame it returns. This
    is the second line: it catches a tool that obtained bars some other way
    and parked them in the state, which no amount of care inside the
    chokepoint can prevent.

    Args:
        frames: The run's memoised frames, keyed however the caller likes.
        asof: As-of date in force; None checks nothing.

    Raises:
        LeakageError: If any frame holds a bar later than ``asof``.
    """
    if asof is None:
        return
    limit = pd.Timestamp(asof)
    for key, frame in frames.items():
        last = getattr(frame, "last_bar", None)
        if last is not None and last > limit:
            raise LeakageError(
                f"frame {key!r} holds a bar at {last.date()}, after as-of "
                f"{asof}; something reached data outside get_ohlc"
            )


def _at_origin(df: pd.DataFrame, start: str, interval: str, bars: int) -> bool:
    """Report whether a frame already begins at the provider's own earliest bar.

    When a well-filled window still starts late, the provider has nothing
    earlier to give and asking again would buy the same rows at the price of
    another round trip. The judgement is deliberately conservative: an
    ambiguous response widens, because a wasted call is cheap and a silently
    short frame is not.

    Args:
        df: Normalised frame from the provider.
        start: The window start that was requested.
        interval: Bar aggregation.
        bars: Bars that were requested.

    Returns:
        True when widening cannot help.
    """
    if len(df) < max(2, int(bars * _ORIGIN_MIN_FILL)):
        # Too little came back to tell a late-starting series from a sparse
        # one, so widening is worth a try.
        return False

    # The series' own median gap, not the interval's nominal one. A thinly
    # traded name or an index that only prints monthly would otherwise look
    # like a series that begins late.
    gaps = pd.Series(df.index).diff().dt.days.dropna()
    cadence = float(gaps.median()) if not gaps.empty else _CALENDAR_PER_BAR[interval]
    cadence = max(cadence, _CALENDAR_PER_BAR[interval])

    slack = timedelta(days=int(cadence * _ORIGIN_TOLERANCE_GAPS) + 1)
    return pd.Timestamp(df.index[0]) > pd.Timestamp(start) + slack


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a provider's frame into the standard shape.

    Args:
        df: Raw frame from a provider.

    Returns:
        A frame with exactly the OHLC columns, a sorted unique DatetimeIndex.

    Raises:
        ValueError: If a required column is missing.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLC_COLUMNS)
    missing = [c for c in OHLC_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"provider frame missing columns: {missing}")
    out = df[OHLC_COLUMNS].copy()

    # Prices have been seen arriving as strings, which turns every downstream
    # comparison into a silent lexicographic one. Coerce rather than raise:
    # an unparseable price becomes NaN, which the tools already handle, while
    # a whole column of them shows up as an empty frame.
    for column in OHLC_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="coerce")

    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[out.index.notna()]
    out = out[~out.index.duplicated(keep="last")]
    out = out.sort_index()

    # A row with no close is not a bar; it is a gap the source left behind.
    return out[out["Close"].notna()]


def get_ohlc(req: OhlcRequest, provider: PriceProvider) -> OhlcFrame:
    """Fetch price history for a request, guaranteeing no future bars.

    The guarantee is enforced twice over: the frame is sliced to ``asof``, and
    the result is then checked. A provider that ignores the window -- which
    the live cache has historically done -- is caught here rather than
    contaminating an analysis.

    Args:
        req: What to fetch.
        provider: Where to fetch it from.

    Returns:
        The truncated frame with its provenance.

    Raises:
        LeakageError: If any bar later than ``asof`` survives truncation.
        ValueError: If the provider returns a frame missing OHLC columns.
    """
    anchor = req.asof or date.today()
    end = req.asof.isoformat() if req.asof else None

    start = _start_for(req)
    raw = _normalize(provider.get(req.ticker, req.interval, start, end))
    calls = 1

    # A short frame usually means the calendar-day estimate was tight rather
    # than that the history is absent: holidays, halts and thin names all
    # yield fewer bars per calendar day than the estimate assumes. Widen in
    # bounded steps, and stop as soon as widening stops helping.
    for factor in _WIDEN_STEPS:
        if len(raw) >= req.bars or _at_origin(raw, start, req.interval, req.bars):
            break
        start = _start_for(req, factor)
        wider = _normalize(provider.get(req.ticker, req.interval, start, end))
        calls += 1
        if len(wider) <= len(raw):
            break
        raw = wider

    before = len(raw)
    if req.asof is not None and not raw.empty:
        raw = raw[raw.index <= pd.Timestamp(req.asof)]

    # Keep the most recent `bars` rows; everything earlier is surplus.
    if len(raw) > req.bars:
        raw = raw.iloc[-req.bars :]

    frame = OhlcFrame(
        df=raw,
        ticker=req.ticker,
        interval=req.interval,
        asof=req.asof,
        requested_bars=req.bars,
        truncated=len(raw) < before,
        source=getattr(provider, "source", "live"),
        fetch_calls=calls,
        anchor=anchor,
    )

    # The whole reason this module exists.
    if req.asof is not None and frame.last_bar is not None:
        if frame.last_bar > pd.Timestamp(req.asof):
            raise LeakageError(
                f"{req.ticker}: last bar {frame.last_bar.date()} is after "
                f"as-of {req.asof}; the provider or the truncation is broken"
            )
    return frame
