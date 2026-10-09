"""HTTP client and parsers for Treasury, FRED and New York Fed data.

All endpoints used here are keyless.  The FRED CSV endpoint throttles rapid
sequential requests -- a tight loop over nine series returns connection
failures -- so :class:`MacroClient` paces requests and retries with backoff.

Parsing is split from fetching: every ``parse_*`` function takes raw bytes and
is directly testable without a network or a mock server, following the same
shape as :func:`stockcharts.screener.sec_insider.parse_form4`.
"""

from __future__ import annotations

import io
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pandas as pd

from stockcharts.macro.series import (
    REAL_TENOR_FIELDS,
    TENOR_FIELDS,
    TREASURY_NOMINAL_DATASET,
    TREASURY_REAL_DATASET,
)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
TREASURY_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "pages/xml?data={dataset}&field_tdr_date_value={year}"
)
FISCALDATA_AUCTIONS_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/"
    "auctions_query?filter=original_security_term:eq:{term}&sort=-auction_date&page[size]={limit}"
)
NYFED_SOFR_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/{limit}.json"
NYFED_REPO_URL = "https://markets.newyorkfed.org/api/rp/all/all/results/last/{limit}.json"

DEFAULT_USER_AGENT = "StockCharts macro dashboard (educational)"
DEFAULT_REQUEST_DELAY = 1.1
# The Treasury XML feed returns a whole year at once and is often slow.
TREASURY_TIMEOUT = 60.0
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
CACHE_MAX_AGE_HOURS = 6.0
# Days of already-cached tail re-requested on a top-up, to absorb revisions.
TAIL_OVERLAP_DAYS = 10

_DEFAULT_MACRO_CACHE = Path(
    os.environ.get(
        "STOCKCHARTS_MACRO_CACHE",
        str(Path(__file__).resolve().parents[3] / "cache" / "macro"),
    )
)


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------
# Deliberately local rather than imported from screener.sec_insider: those are
# private helpers of an unrelated package, and coupling macro to the SEC
# screener for six lines of namespace handling would be the wrong trade.


def _local_name(tag: str) -> str:
    """Return an XML tag's local name, ignoring an optional namespace.

    Args:
        tag: Fully qualified or bare tag name.

    Returns:
        The tag's local portion.
    """
    return tag.rsplit("}", 1)[-1]


def _descendants(node: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    """Find all descendants with a given local name.

    Args:
        node: Element to search below.
        name: Local tag name to match.

    Returns:
        Matching elements in document order.
    """
    return [el for el in node.iter() if _local_name(el.tag) == name]


def _as_float(text: str | None) -> float | None:
    """Parse a numeric XML or JSON field, returning None when unusable.

    Args:
        text: Raw text value.

    Returns:
        The parsed float, or None for blank or non-numeric input.
    """
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned or cleaned in {".", "-", "--", "N/A", "n/a", "null"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_timestamp(value: object) -> pd.Timestamp:
    """Parse a value into a Timestamp, yielding NaT when unusable.

    The ignores below are because ``pd.NaT`` is typed as a distinct class from
    ``Timestamp``; every caller drops the resulting missing values.

    Args:
        value: Raw date value from XML or JSON.

    Returns:
        The parsed timestamp, or ``pd.NaT``.
    """
    if value is None:
        return pd.NaT  # type: ignore[return-value]
    return pd.to_datetime(str(value), errors="coerce")  # type: ignore[return-value]


def _as_text(content: bytes | str) -> str:
    """Decode bytes to text, tolerating a byte-order mark.

    Args:
        content: Raw response body.

    Returns:
        Decoded text.
    """
    if isinstance(content, bytes):
        return content.decode("utf-8-sig", errors="replace")
    return content


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_fred_csv(content: bytes | str, series_id: str) -> pd.Series:
    """Parse a FRED CSV export into a float Series indexed by date.

    FRED marks missing observations with ``.`` and has changed its date header
    from ``DATE`` to ``observation_date``, so columns are read positionally and
    values are coerced rather than string-matched.

    Args:
        content: Raw CSV body.
        series_id: Series identifier, used to name the result.

    Returns:
        Observations indexed by date with missing values dropped.  An empty
        body yields an empty Series rather than raising.
    """
    text = _as_text(content).strip()
    if not text:
        return pd.Series(dtype="float64", name=series_id)
    frame = pd.read_csv(io.StringIO(text))
    if frame.shape[1] < 2 or frame.empty:
        return pd.Series(dtype="float64", name=series_id)
    date_col, value_col = frame.columns[0], frame.columns[1]
    series = pd.Series(
        pd.to_numeric(frame[value_col], errors="coerce").to_numpy(),
        index=pd.to_datetime(frame[date_col], errors="coerce"),
        name=series_id,
        dtype="float64",
    )
    return series[series.index.notna()].dropna()


def parse_treasury_xml(content: bytes | str, real: bool = False) -> pd.DataFrame:
    """Parse the Treasury par-yield Atom feed into a curve DataFrame.

    Args:
        content: Raw XML body.
        real: True when parsing the real (TIPS) curve, which uses ``TC_``
            field names and a shorter set of tenors.

    Returns:
        Yields in percent, indexed by date, with tenors in years as columns.
        An empty or unparseable feed yields an empty DataFrame.
    """
    text = _as_text(content).strip()
    if not text:
        return pd.DataFrame()
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return pd.DataFrame()

    fields = REAL_TENOR_FIELDS if real else TENOR_FIELDS
    rows: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []

    for properties in _descendants(root, "properties"):
        values: dict[str, float] = {}
        observed: pd.Timestamp | None = None
        for child in properties:
            name = _local_name(child.tag)
            if name in {"NEW_DATE", "Date"}:
                observed = _to_timestamp(child.text)
            elif name in fields:
                parsed = _as_float(child.text)
                if parsed is not None:
                    values[str(fields[name])] = parsed
        if observed is not None and not pd.isna(observed) and values:
            index.append(observed)
            rows.append(values)

    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows, index=pd.DatetimeIndex(index))
    frame = frame.set_axis([float(c) for c in frame.columns], axis=1)
    return frame.sort_index().sort_index(axis=1)


def parse_auctions_json(content: bytes | str) -> pd.DataFrame:
    """Parse Treasury FiscalData auction results.

    The indirect bidder share is computed against *competitive* accepted
    amounts, which is the convention quoted in market commentary.  Dividing by
    total accepted instead understates it by roughly 18 points.

    Args:
        content: Raw JSON body.

    Returns:
        One row per auction with ``auction_date``, ``security_term``,
        ``bid_to_cover``, ``indirect_pct`` and ``high_yield``, newest first.
    """
    text = _as_text(content).strip()
    if not text:
        return pd.DataFrame()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return pd.DataFrame()

    records = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        competitive = _as_float(record.get("comp_accepted"))
        indirect = _as_float(record.get("indirect_bidder_accepted"))
        indirect_pct = (
            100.0 * indirect / competitive
            if competitive is not None and indirect is not None and competitive > 0
            else None
        )
        rows.append(
            {
                "auction_date": _to_timestamp(record.get("auction_date")),
                "security_term": record.get("security_term"),
                "original_security_term": record.get("original_security_term"),
                "bid_to_cover": _as_float(record.get("bid_to_cover_ratio")),
                "indirect_pct": indirect_pct,
                "high_yield": _as_float(record.get("high_yield")),
                "offering_amt": _as_float(record.get("offering_amt")),
            }
        )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).dropna(subset=["auction_date"])
    return frame.sort_values("auction_date", ascending=False).reset_index(drop=True)


def parse_sofr_json(content: bytes | str) -> pd.DataFrame:
    """Parse New York Fed secured reference rates.

    Args:
        content: Raw JSON body.

    Returns:
        SOFR observations indexed by effective date, with ``percentRate`` and
        ``volumeInBillions`` columns.
    """
    text = _as_text(content).strip()
    if not text:
        return pd.DataFrame()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return pd.DataFrame()

    records = payload.get("refRates") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        return pd.DataFrame()

    rows = [
        {
            "effective_date": _to_timestamp(r.get("effectiveDate")),
            "rate": _as_float(str(r.get("percentRate"))),
            "volume_bn": _as_float(str(r.get("volumeInBillions"))),
        }
        for r in records
        if isinstance(r, dict)
    ]
    frame = pd.DataFrame(rows).dropna(subset=["effective_date"])
    if frame.empty:
        return pd.DataFrame()
    return frame.set_index("effective_date").sort_index()


def parse_repo_ops_json(content: bytes | str) -> pd.DataFrame:
    """Parse New York Fed repo operation results.

    Args:
        content: Raw JSON body.

    Returns:
        Operations indexed by date with ``accepted_bn`` in billions of dollars,
        restricted to repo (not reverse repo) operations.
    """
    text = _as_text(content).strip()
    if not text:
        return pd.DataFrame()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return pd.DataFrame()

    container = payload.get("repo") if isinstance(payload, dict) else None
    operations = container.get("operations") if isinstance(container, dict) else None
    if not isinstance(operations, list) or not operations:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for op in operations:
        if not isinstance(op, dict):
            continue
        if str(op.get("operationType", "")).lower() != "repo":
            continue
        accepted = _as_float(str(op.get("totalAmtAccepted")))
        rows.append(
            {
                "operation_date": _to_timestamp(op.get("operationDate")),
                "accepted_bn": accepted / 1e9 if accepted is not None else None,
                "term": op.get("term"),
            }
        )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).dropna(subset=["operation_date"])
    if frame.empty:
        return pd.DataFrame()
    return frame.set_index("operation_date").sort_index()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class MacroClient:
    """Rate-limited client for the keyless macro data endpoints."""

    def __init__(
        self,
        user_agent: str | None = None,
        timeout: float = 20.0,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        max_retries: int = 3,
        cache_dir: Path | None = None,
        use_cache: bool = True,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        """Create a client.

        Args:
            user_agent: Descriptive User-Agent.  ``STOCKCHARTS_USER_AGENT`` is
                used when omitted.
            timeout: Per-request timeout in seconds.
            request_delay: Minimum seconds between requests.  The FRED CSV
                endpoint refuses connections below roughly one second.
            max_retries: Attempts per request before giving up.
            cache_dir: Parquet cache location.  Defaults to ``cache/macro``,
                a subdirectory the OHLC warmer's non-recursive glob ignores.
            use_cache: Whether to read and write the on-disk cache.
            opener: Optional ``urlopen``-compatible callable, for testing.
        """
        self.user_agent: str = (
            user_agent or os.environ.get("STOCKCHARTS_USER_AGENT") or DEFAULT_USER_AGENT
        )
        self.timeout = timeout
        self.request_delay = max(0.0, request_delay)
        self.max_retries = max(1, max_retries)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else _DEFAULT_MACRO_CACHE
        self.use_cache = use_cache
        self._opener = opener or urllib.request.urlopen
        self._last_request_at = 0.0
        self._memo: dict[str, bytes] = {}

    # -- transport ---------------------------------------------------------

    def _get_bytes(self, url: str, timeout: float | None = None) -> bytes:
        """Fetch a URL with pacing and retry.

        Args:
            url: Absolute URL to fetch.
            timeout: Per-request timeout override, for slower endpoints.

        Returns:
            The response body.

        Raises:
            OSError: If every attempt fails.
        """
        if url in self._memo:
            return self._memo[url]

        last_error: BaseException | None = None
        for attempt in range(self.max_retries):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.request_delay:
                time.sleep(self.request_delay - elapsed)
            # No Accept header. FRED's fredgraph.csv endpoint accepts the
            # connection and then never responds when one is present -- any
            # value, including the "*/*" that was here and a correct
            # "text/csv" -- which cost 63 seconds of retries per series and
            # made the whole snapshot unusable. Omitting it is semantically
            # identical under HTTP, and the Treasury, FiscalData and NY Fed
            # endpoints return byte-identical responses either way.
            request = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent},
            )
            try:
                response = self._opener(request, timeout=timeout or self.timeout)
                self._last_request_at = time.monotonic()
                try:
                    payload: bytes = response.read()
                finally:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
                self._memo[url] = payload
                return payload
            except urllib.error.HTTPError as error:
                self._last_request_at = time.monotonic()
                last_error = error
                if error.code not in RETRY_STATUS:
                    raise
            except OSError as error:
                # OSError covers URLError, TimeoutError (what a read timeout
                # actually raises) and reset connections. Catching only
                # URLError here silently skipped every timeout.
                self._last_request_at = time.monotonic()
                last_error = error
            if attempt < self.max_retries - 1:
                time.sleep(2.0**attempt)

        assert last_error is not None  # noqa: S101 - loop always sets it before exiting
        raise last_error

    # -- cache -------------------------------------------------------------

    def _cache_path(self, key: str) -> Path:
        """Return the parquet path for a cache key.

        Args:
            key: Cache key, typically a series identifier.

        Returns:
            Path inside the macro cache directory.
        """
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self.cache_dir / f"{safe}.parquet"

    def _read_cache(self, key: str, max_age_hours: float | None = None) -> pd.DataFrame | None:
        """Read a cached frame when it is fresh enough.

        Args:
            key: Cache key.
            max_age_hours: Override for the freshness window.  Used for data
                that cannot change, such as a completed calendar year.

        Returns:
            The cached frame, or None when absent, stale or unreadable.
        """
        if not self.use_cache:
            return None
        path = self._cache_path(key)
        if not path.exists():
            return None
        limit = CACHE_MAX_AGE_HOURS if max_age_hours is None else max_age_hours
        age_hours = (time.time() - path.stat().st_mtime) / 3600.0
        if age_hours > limit:
            return None
        try:
            return pd.read_parquet(path)
        except Exception:
            return None

    def _meta_path(self, key: str) -> Path:
        """Return the sidecar metadata path for a cache key.

        Args:
            key: Cache key.

        Returns:
            Path to the JSON sidecar beside the parquet file.
        """
        return self._cache_path(key).with_suffix(".meta.json")

    def _read_covered_start(self, key: str) -> date | None:
        """Return the earliest start previously requested for a series.

        Args:
            key: Cache key.

        Returns:
            The recorded start date, or None when unknown.
        """
        path = self._meta_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return date.fromisoformat(str(payload["covered_start"])[:10])
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            return None

    def _write_covered_start(self, key: str, start: date) -> None:
        """Record the earliest start covered by the cache, never narrowing it.

        Args:
            key: Cache key.
            start: Start date just requested.
        """
        existing = self._read_covered_start(key)
        earliest = min(existing, start) if existing else start
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._meta_path(key).write_text(
                json.dumps({"covered_start": earliest.isoformat()}), encoding="utf-8"
            )
        except OSError:
            return

    def _cache_age_hours(self, key: str) -> float | None:
        """Return how long ago a cache entry was written.

        Args:
            key: Cache key.

        Returns:
            Age in hours, or None when the entry does not exist.
        """
        path = self._cache_path(key)
        if not path.exists():
            return None
        return (time.time() - path.stat().st_mtime) / 3600.0

    def _write_cache(self, key: str, frame: pd.DataFrame) -> None:
        """Write a frame to the macro cache, ignoring failures.

        Args:
            key: Cache key.
            frame: Frame to persist.
        """
        if not self.use_cache or frame.empty:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(self._cache_path(key))
        except Exception:
            return

    # -- fetchers ----------------------------------------------------------

    def fetch_series(
        self,
        series_id: str,
        start: date | str | None = None,
        use_cache: bool | None = None,
    ) -> pd.Series:
        """Fetch one FRED series, accumulating history in the local cache.

        Downloaded observations are kept permanently.  A later call that needs
        no earlier history only downloads the recent tail, so a long lookback
        is slow exactly once.

        Args:
            series_id: FRED series identifier, such as ``DGS10``.
            start: Earliest observation date.  Defaults to five years back.
            use_cache: Overrides the client's cache setting for this call.

        Returns:
            Observations indexed by date, from ``start`` onward.
        """
        cache_enabled = self.use_cache if use_cache is None else use_cache
        if start is None:
            start = date.today() - timedelta(days=5 * 365)
        start_date = start if isinstance(start, date) else _parse_iso(str(start))
        key = f"fred_{series_id}"

        cached = self._read_cache(key, max_age_hours=float("inf")) if cache_enabled else None
        history: pd.Series | None = None
        if cached is not None and not cached.empty:
            history = cached.iloc[:, 0].rename(series_id)

        fetch_from = start_date
        if history is not None and len(history):
            # Compare against what was previously *requested*, not the earliest
            # observation returned: a weekend start never matches an
            # observation, and some series simply begin later than the window.
            covered = self._read_covered_start(key)
            covers_start = covered is not None and covered <= start_date
            age = self._cache_age_hours(key)
            if covers_start:
                if age is not None and age <= CACHE_MAX_AGE_HOURS:
                    return _since(history, start_date)
                # History is deep enough; top up only the recent tail. The
                # overlap absorbs revisions to already-published values.
                fetch_from = history.index.max().date() - timedelta(days=TAIL_OVERLAP_DAYS)

        payload = self._get_bytes(
            FRED_CSV_URL.format(series_id=series_id, start=fetch_from.isoformat())
        )
        fresh = parse_fred_csv(payload, series_id)
        merged = _merge_series(history, fresh, series_id)
        if cache_enabled and not merged.empty:
            self._write_cache(key, merged.to_frame())
            self._write_covered_start(key, min(start_date, fetch_from))
        return _since(merged, start_date)

    def fetch_many(
        self,
        series_ids: Sequence[str],
        start: date | str | None = None,
    ) -> tuple[dict[str, pd.Series], list[str]]:
        """Fetch several FRED series, tolerating individual failures.

        Args:
            series_ids: FRED identifiers.
            start: Earliest observation date.

        Returns:
            A mapping of identifier to observations, and a list of
            human-readable errors for the series that could not be fetched.
        """
        results: dict[str, pd.Series] = {}
        errors: list[str] = []
        for series_id in series_ids:
            try:
                results[series_id] = self.fetch_series(series_id, start=start)
            except Exception as error:
                errors.append(f"{series_id}: {type(error).__name__}: {error}")
        return results, errors

    def fetch_treasury_curve(self, year: int | None = None, real: bool = False) -> pd.DataFrame:
        """Fetch a full year of the Treasury par-yield curve in one request.

        Args:
            year: Calendar year to fetch.  Defaults to the current year.
            real: True for the real (TIPS) curve.

        Returns:
            Yields in percent, indexed by date, tenors in years as columns.
        """
        year = year or date.today().year
        dataset = TREASURY_REAL_DATASET if real else TREASURY_NOMINAL_DATASET
        key = f"treasury_{'real' if real else 'nominal'}_{year}"
        # A past year is final, so it never needs re-fetching.
        max_age = None if year >= date.today().year else float("inf")
        cached = self._read_cache(key, max_age_hours=max_age)
        if cached is not None and not cached.empty:
            return cached.set_axis([float(c) for c in cached.columns], axis=1)
        payload = self._get_bytes(
            TREASURY_XML_URL.format(dataset=dataset, year=year),
            timeout=TREASURY_TIMEOUT,
        )
        frame = parse_treasury_xml(payload, real=real)
        if not frame.empty:
            to_store = frame.set_axis([str(c) for c in frame.columns], axis=1)
            self._write_cache(key, to_store)
        return frame

    def fetch_treasury_history(
        self,
        lookback_days: int = 730,
        real: bool = False,
        end: date | None = None,
    ) -> pd.DataFrame:
        """Fetch the par-yield curve across as many years as the window needs.

        The Treasury feed is paginated by calendar year, so spanning a window
        longer than year-to-date takes one request per year.  Completed years
        are cached indefinitely, so only the current year is ever re-fetched.

        Args:
            lookback_days: Days of history required.
            real: True for the real (TIPS) curve.
            end: Last date of interest.  Defaults to today.

        Returns:
            Yields in percent, indexed by date, tenors in years as columns.
        """
        last = end or date.today()
        first = last - timedelta(days=max(1, lookback_days))
        frames: list[pd.DataFrame] = []
        for year in range(first.year, last.year + 1):
            try:
                frame = self.fetch_treasury_curve(year=year, real=real)
            except Exception:
                continue  # a missing year must not lose the others
            if not frame.empty:
                frames.append(frame)
        if not frames:
            return pd.DataFrame()
        combined = pd.concat(frames).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
        return combined.sort_index(axis=1)

    def fetch_auctions(self, term: str = "10-Year", limit: int = 8) -> pd.DataFrame:
        """Fetch recent auction results for one original security term.

        Reopenings are filed under terms such as ``9-Year 11-Month``, so the
        query filters on ``original_security_term`` rather than
        ``security_term``.

        Args:
            term: Original security term, such as ``10-Year``.
            limit: Maximum auctions to return.

        Returns:
            Auctions newest first.
        """
        url = FISCALDATA_AUCTIONS_URL.format(term=term.replace(" ", "%20"), limit=limit)
        return parse_auctions_json(self._get_bytes(url))

    def fetch_sofr(self, limit: int = 30) -> pd.DataFrame:
        """Fetch recent SOFR fixings from the New York Fed.

        Args:
            limit: Number of observations to request.

        Returns:
            SOFR observations indexed by effective date.
        """
        return parse_sofr_json(self._get_bytes(NYFED_SOFR_URL.format(limit=limit)))

    def fetch_repo_ops(self, limit: int = 30) -> pd.DataFrame:
        """Fetch recent Fed repo operation results.

        Args:
            limit: Number of operations to request.

        Returns:
            Repo operations indexed by operation date.
        """
        return parse_repo_ops_json(self._get_bytes(NYFED_REPO_URL.format(limit=limit)))


def _parse_iso(text: str) -> date:
    """Parse an ISO date, falling back to five years ago.

    Args:
        text: Date text.

    Returns:
        The parsed date.
    """
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return date.today() - timedelta(days=5 * 365)


def _since(series: pd.Series, start: date) -> pd.Series:
    """Restrict a series to observations on or after a date.

    Args:
        series: Observations indexed by date.
        start: Earliest date to keep.

    Returns:
        The trimmed series.
    """
    if series.empty:
        return series
    return series[series.index >= pd.Timestamp(start)]


def _merge_series(
    history: pd.Series | None,
    fresh: pd.Series,
    series_id: str,
) -> pd.Series:
    """Combine cached history with newly downloaded observations.

    Args:
        history: Previously cached observations, if any.
        fresh: Newly downloaded observations.
        series_id: Series identifier, used to name the result.

    Returns:
        The union of both, newest values winning on overlap.
    """
    if history is None or history.empty:
        return fresh.rename(series_id)
    if fresh.empty:
        return history.rename(series_id)
    combined = pd.concat([history, fresh])
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined.sort_index().rename(series_id)


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        Timestamp such as ``2026-09-26T14:02:11Z``.
    """
    # datetime.UTC is fine now the package floor is Python 3.11.
    return datetime.now(UTC).replace(microsecond=0, tzinfo=None).isoformat() + "Z"


__all__ = [
    "CACHE_MAX_AGE_HOURS",
    "TAIL_OVERLAP_DAYS",
    "TREASURY_TIMEOUT",
    "DEFAULT_REQUEST_DELAY",
    "DEFAULT_USER_AGENT",
    "MacroClient",
    "parse_auctions_json",
    "parse_fred_csv",
    "parse_repo_ops_json",
    "parse_sofr_json",
    "parse_treasury_xml",
    "utc_now_iso",
]
