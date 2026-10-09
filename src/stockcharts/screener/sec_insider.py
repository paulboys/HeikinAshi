"""SEC Form 4 insider-trading data and relative-activity screening.

The module uses the SEC submissions API to discover Form 4 filings and the
EDGAR archive to retrieve their XML documents.  It then compares a recent
window with an immediately preceding baseline window using two ratios:

* insider shares transacted / total market shares traded; and
* insider shares transacted / total reported insider holdings.

Only open-market purchases (``P``) and sales (``S``) are included in the
trading-activity numerator by default.  Other Form 4 transaction codes can be
included with ``transaction_codes`` when a broader definition of activity is
desired.

SEC requests must identify the caller with a descriptive User-Agent.  Set the
``SEC_USER_AGENT`` environment variable or pass ``user_agent`` to
:class:`SECClient`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from xml.etree import ElementTree

import pandas as pd

from stockcharts.data.fetch import fetch_ohlc

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_SEC_USER_AGENT = "StockCharts/0.6.1 (+https://github.com/paulboys/HeikinAshi)"
DEFAULT_TRANSACTION_CODES = ("P", "S")
DEFAULT_HOLDINGS_LOOKBACK_DAYS = 365


@dataclass(frozen=True)
class SECFiling:
    """Metadata for a filing listed in a company's SEC submissions history."""

    cik: str
    accession_number: str
    form: str
    filing_date: date
    report_date: date | None
    primary_document: str

    @property
    def document_url(self) -> str:
        """Return the archive URL for the filing's primary document.

        The SEC lists Form 4 primary documents under an ``xsl.../`` prefix that
        serves the XSL-rendered HTML view.  That prefix is stripped so the raw
        XML is fetched instead, because only the XML is parseable.
        """
        cik_number = str(int(self.cik))
        accession_path = self.accession_number.replace("-", "")
        document = self.primary_document
        prefix, separator, remainder = document.partition("/")
        if separator and prefix.startswith("xsl"):
            document = remainder
        return f"{SEC_ARCHIVES_URL}/{cik_number}/{accession_path}/{document}"


@dataclass(frozen=True)
class SECInsiderTransaction:
    """A non-derivative transaction reported on SEC Form 4."""

    cik: str
    accession_number: str
    filing_date: date
    report_date: date | None
    transaction_date: date
    insider_name: str
    insider_title: str | None
    security_title: str
    transaction_code: str | None
    acquired_disposed: str | None
    shares: float
    price_per_share: float | None
    shares_owned_following: float | None
    ownership_form: str | None
    filing_url: str

    @property
    def transaction_shares(self) -> float:
        """Alias for ``shares`` that makes the metric's meaning explicit."""
        return self.shares


@dataclass(frozen=True)
class InsiderHolding:
    """A point-in-time non-derivative holding reported by an insider."""

    cik: str
    accession_number: str
    observation_date: date
    filing_date: date
    insider_name: str
    security_title: str
    shares_owned: float
    ownership_form: str | None


@dataclass(frozen=True)
class Form4Data:
    """Parsed Form 4 transactions and holding observations."""

    transactions: tuple[SECInsiderTransaction, ...]
    holdings: tuple[InsiderHolding, ...]


@dataclass(frozen=True)
class InsiderTradingScreenResult:
    """Relative insider-trading measurements for one ticker.

    ``*_ratio_increase`` is the recent-window ratio divided by the baseline
    ratio.  It is ``None`` when the comparison has no finite value, and the
    matching ``*_increase_unbounded`` flag distinguishes the two reasons:
    ``True`` means the baseline ratio was zero while the recent ratio was
    positive, ``False`` means a ratio could not be computed at all.
    """

    ticker: str
    cik: str
    recent_start: date
    recent_end: date
    baseline_start: date
    baseline_end: date
    recent_insider_shares: float
    baseline_insider_shares: float
    recent_market_volume: float
    baseline_market_volume: float
    recent_insider_volume_ratio: float | None
    baseline_insider_volume_ratio: float | None
    volume_ratio_increase: float | None
    recent_insider_holdings: float
    baseline_insider_holdings: float
    recent_insider_holding_ratio: float | None
    baseline_insider_holding_ratio: float | None
    holding_ratio_increase: float | None
    recent_bought_shares: float
    recent_sold_shares: float
    baseline_bought_shares: float
    baseline_sold_shares: float
    transactions: tuple[SECInsiderTransaction, ...]
    volume_increase_unbounded: bool = False
    holding_increase_unbounded: bool = False


def _parse_date(value: object) -> date | None:
    """Parse an ISO-like date value without raising for blank SEC fields."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _as_float(value: object) -> float | None:
    """Convert an SEC numeric value to float, returning ``None`` if blank."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "--", "N/A", "n/a"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _local_name(tag: str) -> str:
    """Return an XML tag's local name, ignoring an optional namespace."""
    return tag.rsplit("}", 1)[-1]


def _direct_child(node: ElementTree.Element, name: str) -> ElementTree.Element | None:
    """Find a direct child by local XML name."""
    for child in list(node):
        if _local_name(child.tag) == name:
            return child
    return None


def _field_value(node: ElementTree.Element, *path: str) -> str | None:
    """Read a Form 4 value nested below direct XML elements."""
    current: ElementTree.Element | None = node
    for part in path:
        if current is None:
            return None
        current = _direct_child(current, part)
    if current is None:
        return None
    value_node = _direct_child(current, "value")
    text = value_node.text if value_node is not None else current.text
    return text.strip() if text else None


def _table_rows(
    root: ElementTree.Element, table_name: str, row_name: str
) -> list[ElementTree.Element]:
    """Return rows from a Form 4 table while tolerating XML namespaces."""
    table = _direct_child(root, table_name)
    if table is None:
        return []
    return [child for child in list(table) if _local_name(child.tag) == row_name]


def parse_form4(content: bytes | str, filing: SECFiling) -> Form4Data:
    """Parse a Form 4 XML document.

    Args:
        content: XML bytes or text returned by the EDGAR archive.
        filing: Metadata for the document being parsed.

    Returns:
        Parsed non-derivative transactions and holding observations.  Malformed
        or non-ownership documents return empty tuples so one bad filing does
        not stop a universe scan.
    """
    try:
        root = ElementTree.fromstring(content)
    except (ElementTree.ParseError, TypeError, ValueError):
        return Form4Data(transactions=(), holdings=())

    report_date = filing.report_date or _parse_date(_field_value(root, "periodOfReport"))
    owners = [child for child in list(root) if _local_name(child.tag) == "reportingOwner"]
    if not owners:
        owners = [root]

    transactions: list[SECInsiderTransaction] = []
    holdings: list[InsiderHolding] = []
    transaction_rows = _table_rows(root, "nonDerivativeTable", "nonDerivativeTransaction")
    holding_rows = _table_rows(root, "nonDerivativeTable", "nonDerivativeHolding")

    for owner in owners:
        insider_name = (
            _field_value(owner, "reportingOwnerId", "rptOwnerName")
            or _field_value(root, "issuer", "issuerName")
            or "Unknown insider"
        )
        insider_title = _field_value(owner, "reportingOwnerRelationship", "officerTitle")

        for row in transaction_rows:
            transaction_date = (
                _parse_date(_field_value(row, "transactionDate"))
                or report_date
                or filing.filing_date
            )
            security_title = _field_value(row, "securityTitle") or ""
            transaction_code = _field_value(row, "transactionCoding", "transactionCode")
            acquired_disposed = _field_value(
                row, "transactionAmounts", "transactionAcquiredDisposedCode"
            )
            shares = _as_float(_field_value(row, "transactionAmounts", "transactionShares")) or 0.0
            price = _as_float(_field_value(row, "transactionAmounts", "transactionPricePerShare"))
            shares_following = _as_float(
                _field_value(row, "postTransactionAmounts", "sharesOwnedFollowingTransaction")
            )
            ownership_form = _field_value(row, "ownershipNature", "directOrIndirectOwnership")

            transactions.append(
                SECInsiderTransaction(
                    cik=filing.cik,
                    accession_number=filing.accession_number,
                    filing_date=filing.filing_date,
                    report_date=report_date,
                    transaction_date=transaction_date,
                    insider_name=insider_name,
                    insider_title=insider_title,
                    security_title=security_title,
                    transaction_code=transaction_code,
                    acquired_disposed=acquired_disposed,
                    shares=abs(shares),
                    price_per_share=price,
                    shares_owned_following=shares_following,
                    ownership_form=ownership_form,
                    filing_url=filing.document_url,
                )
            )

            if shares_following is not None:
                holdings.append(
                    InsiderHolding(
                        cik=filing.cik,
                        accession_number=filing.accession_number,
                        observation_date=transaction_date,
                        filing_date=filing.filing_date,
                        insider_name=insider_name,
                        security_title=security_title,
                        shares_owned=max(0.0, shares_following),
                        ownership_form=ownership_form,
                    )
                )

        for row in holding_rows:
            security_title = _field_value(row, "securityTitle") or ""
            shares_following = _as_float(
                _field_value(row, "postTransactionAmounts", "sharesOwnedFollowingTransaction")
            )
            if shares_following is None:
                continue
            ownership_form = _field_value(row, "ownershipNature", "directOrIndirectOwnership")
            holdings.append(
                InsiderHolding(
                    cik=filing.cik,
                    accession_number=filing.accession_number,
                    observation_date=report_date or filing.filing_date,
                    filing_date=filing.filing_date,
                    insider_name=insider_name,
                    security_title=security_title,
                    shares_owned=max(0.0, shares_following),
                    ownership_form=ownership_form,
                )
            )

    return Form4Data(tuple(transactions), tuple(holdings))


class SECClient:
    """Small client for the SEC submissions and EDGAR archive endpoints."""

    def __init__(
        self,
        user_agent: str | None = None,
        timeout: float = 20.0,
        request_delay: float = 0.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        """Create a client.

        Args:
            user_agent: Descriptive SEC User-Agent, preferably including a
                contact email.  ``SEC_USER_AGENT`` is used when omitted.
            timeout: Per-request timeout in seconds.
            request_delay: Minimum delay between requests, useful for larger
                universe scans.
            opener: Optional ``urlopen``-compatible callable for testing.
        """
        self.user_agent = user_agent or os.environ.get("SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT
        self.timeout = timeout
        self.request_delay = max(0.0, request_delay)
        self._opener = opener or urllib.request.urlopen
        self._last_request_at = 0.0
        self._ticker_map: dict[str, str] | None = None
        self._submissions_cache: dict[str, dict[str, Any]] = {}
        self._document_cache: dict[str, bytes] = {}

    def _get_bytes(self, url: str) -> bytes:
        """Fetch bytes with the SEC-required identification header."""
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, application/xml, text/xml, */*",
            },
        )
        response = self._opener(request, timeout=self.timeout)
        self._last_request_at = time.monotonic()
        try:
            return response.read()
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def _get_json(self, url: str) -> dict[str, Any]:
        """Fetch and decode a JSON SEC response."""
        payload = json.loads(self._get_bytes(url).decode("utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected SEC response from {url}")
        return payload

    @staticmethod
    def _normalize_cik(value: str) -> str:
        """Normalize a numeric CIK to the SEC's ten-digit representation."""
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise ValueError(f"Invalid SEC CIK: {value!r}")
        return cleaned.zfill(10)

    def resolve_cik(self, identifier: str) -> str:
        """Resolve a ticker or numeric CIK to a zero-padded CIK."""
        value = identifier.strip()
        if value.isdigit():
            return self._normalize_cik(value)
        if self._ticker_map is None:
            payload = self._get_json(SEC_COMPANY_TICKERS_URL)
            ticker_map: dict[str, str] = {}
            records = payload.values() if isinstance(payload, dict) else []
            for record in records:
                if not isinstance(record, dict):
                    continue
                ticker = str(record.get("ticker", "")).upper()
                cik = str(record.get("cik_str", ""))
                if ticker and cik.isdigit():
                    ticker_map[ticker] = self._normalize_cik(cik)
            self._ticker_map = ticker_map

        ticker = value.upper()
        ticker_map = self._ticker_map
        if ticker_map is None:  # pragma: no cover - initialized above
            raise RuntimeError("SEC ticker map was not initialized")
        resolved_cik = ticker_map.get(ticker)
        if resolved_cik is None:
            # Some data vendors use BRK.B while SEC uses BRK-B, or vice versa.
            compact = ticker.replace(".", "-")
            resolved_cik = ticker_map.get(compact)
        if resolved_cik is None:
            raise ValueError(f"Ticker {identifier!r} was not found in SEC company tickers")
        return resolved_cik

    @staticmethod
    def _submission_rows(payload: dict[str, Any]) -> Iterable[dict[str, str]]:
        """Expand the SEC's column-oriented submissions JSON."""
        filings = payload.get("filings")
        recent = filings.get("recent", {}) if isinstance(filings, dict) else payload
        if not isinstance(recent, dict):
            return
        forms = recent.get("form", [])
        row_count = len(forms) if isinstance(forms, list) else 0
        for index in range(row_count):
            row: dict[str, str] = {}
            for key in ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument"):
                values = recent.get(key, [])
                if isinstance(values, list) and index < len(values):
                    row[key] = str(values[index])
            yield row

    def get_filings(
        self,
        identifier: str,
        start: date | None = None,
        end: date | None = None,
        forms: Sequence[str] = ("4", "4/A"),
    ) -> list[SECFiling]:
        """Return Form 4 filings in an inclusive filing-date range."""
        cik = self.resolve_cik(identifier)
        if cik not in self._submissions_cache:
            self._submissions_cache[cik] = self._get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
        payload = self._submissions_cache[cik]
        allowed_forms = set(forms)
        rows = list(self._submission_rows(payload))

        history_files = payload.get("filings", {}).get("files", [])
        if isinstance(history_files, list):
            for history in history_files:
                if not isinstance(history, dict):
                    continue
                history_from = _parse_date(history.get("filingFrom"))
                history_to = _parse_date(history.get("filingTo"))
                if start and history_to and history_to < start:
                    continue
                if end and history_from and history_from > end:
                    continue
                name = history.get("name")
                if isinstance(name, str) and name:
                    history_payload = self._get_json(f"https://data.sec.gov/submissions/{name}")
                    rows.extend(self._submission_rows(history_payload))

        filings: list[SECFiling] = []
        seen: set[str] = set()
        for row in rows:
            form = row.get("form", "")
            accession = row.get("accessionNumber", "")
            filing_date = _parse_date(row.get("filingDate"))
            if form not in allowed_forms or not accession or filing_date is None:
                continue
            if start and filing_date < start:
                continue
            if end and filing_date > end:
                continue
            if accession in seen:
                continue
            seen.add(accession)
            filings.append(
                SECFiling(
                    cik=cik,
                    accession_number=accession,
                    form=form,
                    filing_date=filing_date,
                    report_date=_parse_date(row.get("reportDate")),
                    primary_document=row.get("primaryDocument", ""),
                )
            )
        return sorted(filings, key=lambda filing: (filing.filing_date, filing.accession_number))

    def fetch_filing_document(self, filing: SECFiling) -> bytes:
        """Fetch and cache a filing's primary document."""
        if filing.accession_number not in self._document_cache:
            self._document_cache[filing.accession_number] = self._get_bytes(filing.document_url)
        return self._document_cache[filing.accession_number]


def fetch_form4_data(
    identifier: str,
    start: date,
    end: date,
    client: SECClient | None = None,
    filing_lag_days: int = 45,
    holdings_lookback_days: int = DEFAULT_HOLDINGS_LOOKBACK_DAYS,
) -> Form4Data:
    """Fetch and parse Form 4 data for a transaction-date range.

    Filing dates are expanded on both sides by ``filing_lag_days`` because a
    Form 4 is normally filed after its transaction date.  Transactions are
    filtered back to the requested date range.

    Holdings are a point-in-time level rather than a flow, so they are also
    collected from up to ``holdings_lookback_days`` before ``start``.  Without
    that lookback an insider appears to hold nothing whenever they happen to
    file no Form 4 inside the window, which is a reporting gap rather than a
    real zero.
    """
    if start > end:
        raise ValueError("start must be on or before end")
    if filing_lag_days < 0:
        raise ValueError("filing_lag_days must be non-negative")
    if holdings_lookback_days < 0:
        raise ValueError("holdings_lookback_days must be non-negative")
    sec_client = client or SECClient()
    cik = sec_client.resolve_cik(identifier)
    holdings_start = start - timedelta(days=holdings_lookback_days)
    filing_start = holdings_start - timedelta(days=filing_lag_days)
    filing_end = end + timedelta(days=filing_lag_days)
    filings = sec_client.get_filings(cik, start=filing_start, end=filing_end)

    transactions: list[SECInsiderTransaction] = []
    holdings: list[InsiderHolding] = []
    for filing in filings:
        parsed = parse_form4(sec_client.fetch_filing_document(filing), filing)
        transactions.extend(
            transaction
            for transaction in parsed.transactions
            if start <= transaction.transaction_date <= end
        )
        holdings.extend(
            holding
            for holding in parsed.holdings
            if holdings_start <= holding.observation_date <= end
        )
    return Form4Data(tuple(transactions), tuple(holdings))


def fetch_insider_transactions(
    identifier: str,
    start: date,
    end: date,
    client: SECClient | None = None,
    filing_lag_days: int = 45,
) -> list[SECInsiderTransaction]:
    """Fetch SEC Form 4 non-derivative transactions for a date range."""
    return list(
        fetch_form4_data(
            identifier,
            start=start,
            end=end,
            client=client,
            filing_lag_days=filing_lag_days,
        ).transactions
    )


def _sum_market_volume(df: pd.DataFrame, start: date, end: date) -> float:
    """Sum OHLCV volume between two inclusive dates."""
    if df.empty or "Volume" not in df.columns:
        return 0.0
    index = pd.to_datetime(df.index).date
    mask = (index >= start) & (index <= end)
    values = pd.to_numeric(df.loc[mask, "Volume"], errors="coerce")
    return float(values.fillna(0.0).sum())


def _activity_totals(
    transactions: Iterable[SECInsiderTransaction],
    start: date,
    end: date,
    transaction_codes: set[str],
) -> tuple[float, float, float]:
    """Return total, bought, and sold shares for an inclusive date range."""
    total = bought = sold = 0.0
    for transaction in transactions:
        if not start <= transaction.transaction_date <= end:
            continue
        if transaction.transaction_code not in transaction_codes:
            continue
        shares = abs(transaction.shares)
        total += shares
        if transaction.acquired_disposed == "A":
            bought += shares
        elif transaction.acquired_disposed == "D":
            sold += shares
    return total, bought, sold


def _total_holdings(
    holdings: Iterable[InsiderHolding],
    as_of: date,
) -> float:
    """Sum the latest reported holding for each insider/security/ownership."""
    latest: dict[tuple[str, str, str], InsiderHolding] = {}
    for holding in holdings:
        if holding.observation_date > as_of:
            continue
        key = (
            holding.insider_name,
            holding.security_title,
            holding.ownership_form or "",
        )
        previous = latest.get(key)
        if previous is None or (
            holding.observation_date,
            holding.filing_date,
            holding.accession_number,
        ) >= (
            previous.observation_date,
            previous.filing_date,
            previous.accession_number,
        ):
            latest[key] = holding
    return float(sum(holding.shares_owned for holding in latest.values()))


def _ratio(numerator: float, denominator: float) -> float | None:
    """Return a non-negative ratio, or ``None`` where the denominator is zero."""
    if denominator <= 0.0:
        return None
    return numerator / denominator


def _ratio_increase(
    current: float | None,
    baseline: float | None,
) -> tuple[float | None, bool]:
    """Compare two ratios, reporting an unbounded increase separately.

    Returns the recent-to-baseline multiple and a flag for the case where the
    baseline ratio was zero while the recent ratio was positive.  That
    comparison is reported as ``(None, True)`` rather than ``float('inf')``,
    because an infinity is not JSON-serializable and collapses every
    zero-baseline ticker onto a single value that cannot be ranked.  Callers
    should rank those tickers by the recent ratio instead.
    """
    if current is None or baseline is None:
        return None, False
    if baseline == 0.0:
        if current > 0.0:
            return None, True
        return 1.0, False
    return current / baseline, False


def _as_screen_date(value: date | str | None) -> date:
    """Normalize a screen end date, defaulting to today."""
    if value is None:
        return date.today()
    parsed = _parse_date(value)
    if parsed is None:
        raise ValueError(f"Invalid end date: {value!r}")
    return parsed


def screen_insider_ticker(
    ticker: str,
    recent_days: int = 30,
    baseline_days: int | None = None,
    end_date: date | str | None = None,
    min_volume_ratio: float | None = None,
    min_holding_ratio: float | None = None,
    min_volume_increase: float | None = 1.0,
    min_holding_increase: float | None = 1.0,
    transaction_codes: Sequence[str] = DEFAULT_TRANSACTION_CODES,
    filing_lag_days: int = 45,
    holdings_lookback_days: int = DEFAULT_HOLDINGS_LOOKBACK_DAYS,
    client: SECClient | None = None,
    ohlc: pd.DataFrame | None = None,
) -> InsiderTradingScreenResult | None:
    """Screen one ticker for increased insider-trading intensity.

    The recent and baseline windows have equal length by default.  A ticker
    passes only when both ratio increases meet their thresholds.  Set either
    ``min_*_increase`` to ``None`` to disable that comparison, and use
    ``min_volume_ratio`` or ``min_holding_ratio`` for absolute floors.

    Args:
        ticker: Exchange ticker or SEC CIK.
        recent_days: Number of days in the recent window.
        baseline_days: Number of days in the prior window; defaults to
            ``recent_days``.
        end_date: Inclusive end of the recent window; defaults to today.
        min_volume_ratio: Optional absolute minimum recent insider/market
            volume ratio.
        min_holding_ratio: Optional absolute minimum recent insider/holdings
            ratio.
        min_volume_increase: Minimum recent-to-baseline volume-ratio multiple.
        min_holding_increase: Minimum recent-to-baseline holding-ratio multiple.
        transaction_codes: Form 4 transaction codes counted as activity.
        filing_lag_days: Extra filing-date range on either side of the windows.
        holdings_lookback_days: Extra history searched for the last reported
            holding of each insider, so a window containing no filings does
            not read as zero holdings.
        client: Reusable SEC client, useful for scans and tests.
        ohlc: Optional pre-fetched daily OHLCV DataFrame.

    Returns:
        A result when both comparisons pass, otherwise ``None``.  A zero
        baseline with positive recent activity counts as passing any
        ``min_*_increase`` threshold, and is marked by the result's
        ``*_increase_unbounded`` flag.
    """
    if recent_days <= 0:
        raise ValueError("recent_days must be positive")
    if baseline_days is None:
        baseline_days = recent_days
    if baseline_days <= 0:
        raise ValueError("baseline_days must be positive")
    if min_volume_increase is not None and min_volume_increase < 0:
        raise ValueError("min_volume_increase must be non-negative")
    if min_holding_increase is not None and min_holding_increase < 0:
        raise ValueError("min_holding_increase must be non-negative")

    recent_end = _as_screen_date(end_date)
    recent_start = recent_end - timedelta(days=recent_days - 1)
    baseline_end = recent_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=baseline_days - 1)
    codes = {code.upper() for code in transaction_codes}
    if not codes:
        raise ValueError("transaction_codes must contain at least one code")

    sec_client = client or SECClient()
    data = fetch_form4_data(
        ticker,
        start=baseline_start,
        end=recent_end,
        client=sec_client,
        filing_lag_days=filing_lag_days,
        holdings_lookback_days=holdings_lookback_days,
    )
    if ohlc is None:
        ohlc = fetch_ohlc(
            ticker,
            interval="1d",
            start=baseline_start.isoformat(),
            end=(recent_end + timedelta(days=1)).isoformat(),
        )

    recent_shares, recent_bought, recent_sold = _activity_totals(
        data.transactions, recent_start, recent_end, codes
    )
    baseline_shares, baseline_bought, baseline_sold = _activity_totals(
        data.transactions, baseline_start, baseline_end, codes
    )
    recent_market_volume = _sum_market_volume(ohlc, recent_start, recent_end)
    baseline_market_volume = _sum_market_volume(ohlc, baseline_start, baseline_end)
    recent_volume_ratio = _ratio(recent_shares, recent_market_volume)
    baseline_volume_ratio = _ratio(baseline_shares, baseline_market_volume)
    volume_ratio_increase, volume_increase_unbounded = _ratio_increase(
        recent_volume_ratio, baseline_volume_ratio
    )

    recent_holdings = _total_holdings(data.holdings, recent_end)
    baseline_holdings = _total_holdings(data.holdings, baseline_end)
    recent_holding_ratio = _ratio(recent_shares, recent_holdings)
    baseline_holding_ratio = _ratio(baseline_shares, baseline_holdings)
    holding_ratio_increase, holding_increase_unbounded = _ratio_increase(
        recent_holding_ratio, baseline_holding_ratio
    )

    if min_volume_ratio is not None and (
        recent_volume_ratio is None or recent_volume_ratio < min_volume_ratio
    ):
        return None
    if min_holding_ratio is not None and (
        recent_holding_ratio is None or recent_holding_ratio < min_holding_ratio
    ):
        return None
    if (
        min_volume_increase is not None
        and not volume_increase_unbounded
        and (volume_ratio_increase is None or volume_ratio_increase < min_volume_increase)
    ):
        return None
    if (
        min_holding_increase is not None
        and not holding_increase_unbounded
        and (holding_ratio_increase is None or holding_ratio_increase < min_holding_increase)
    ):
        return None

    return InsiderTradingScreenResult(
        ticker=ticker.upper(),
        cik=data.transactions[0].cik if data.transactions else sec_client.resolve_cik(ticker),
        recent_start=recent_start,
        recent_end=recent_end,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        recent_insider_shares=recent_shares,
        baseline_insider_shares=baseline_shares,
        recent_market_volume=recent_market_volume,
        baseline_market_volume=baseline_market_volume,
        recent_insider_volume_ratio=recent_volume_ratio,
        baseline_insider_volume_ratio=baseline_volume_ratio,
        volume_ratio_increase=volume_ratio_increase,
        recent_insider_holdings=recent_holdings,
        baseline_insider_holdings=baseline_holdings,
        recent_insider_holding_ratio=recent_holding_ratio,
        baseline_insider_holding_ratio=baseline_holding_ratio,
        holding_ratio_increase=holding_ratio_increase,
        recent_bought_shares=recent_bought,
        recent_sold_shares=recent_sold,
        baseline_bought_shares=baseline_bought,
        baseline_sold_shares=baseline_sold,
        transactions=tuple(data.transactions),
        volume_increase_unbounded=volume_increase_unbounded,
        holding_increase_unbounded=holding_increase_unbounded,
    )


def screen_insider_trading(
    ticker: str,
    recent_days: int = 30,
    baseline_days: int | None = None,
    end_date: date | str | None = None,
    min_volume_ratio: float | None = None,
    min_holding_ratio: float | None = None,
    min_volume_increase: float | None = 1.0,
    min_holding_increase: float | None = 1.0,
    transaction_codes: Sequence[str] = DEFAULT_TRANSACTION_CODES,
    filing_lag_days: int = 45,
    holdings_lookback_days: int = DEFAULT_HOLDINGS_LOOKBACK_DAYS,
    client: SECClient | None = None,
    ohlc: pd.DataFrame | None = None,
) -> InsiderTradingScreenResult | None:
    """Alias for :func:`screen_insider_ticker` with a concise public name."""
    return screen_insider_ticker(
        ticker=ticker,
        recent_days=recent_days,
        baseline_days=baseline_days,
        end_date=end_date,
        min_volume_ratio=min_volume_ratio,
        min_holding_ratio=min_holding_ratio,
        min_volume_increase=min_volume_increase,
        min_holding_increase=min_holding_increase,
        transaction_codes=transaction_codes,
        filing_lag_days=filing_lag_days,
        holdings_lookback_days=holdings_lookback_days,
        client=client,
        ohlc=ohlc,
    )


def screen_insider_universe(
    tickers: Iterable[str],
    delay: float = 0.0,
    recent_days: int = 30,
    baseline_days: int | None = None,
    end_date: date | str | None = None,
    min_volume_ratio: float | None = None,
    min_holding_ratio: float | None = None,
    min_volume_increase: float | None = 1.0,
    min_holding_increase: float | None = 1.0,
    transaction_codes: Sequence[str] = DEFAULT_TRANSACTION_CODES,
    filing_lag_days: int = 45,
    holdings_lookback_days: int = DEFAULT_HOLDINGS_LOOKBACK_DAYS,
    client: SECClient | None = None,
) -> list[InsiderTradingScreenResult]:
    """Screen multiple tickers, skipping tickers whose data cannot be fetched."""
    if delay < 0:
        raise ValueError("delay must be non-negative")
    results: list[InsiderTradingScreenResult] = []
    shared_client = client or SECClient(request_delay=delay)
    for index, ticker in enumerate(tickers):
        if index and delay and not shared_client.request_delay:
            time.sleep(delay)
        try:
            result = screen_insider_ticker(
                ticker=ticker,
                recent_days=recent_days,
                baseline_days=baseline_days,
                end_date=end_date,
                min_volume_ratio=min_volume_ratio,
                min_holding_ratio=min_holding_ratio,
                min_volume_increase=min_volume_increase,
                min_holding_increase=min_holding_increase,
                transaction_codes=transaction_codes,
                filing_lag_days=filing_lag_days,
                holdings_lookback_days=holdings_lookback_days,
                client=shared_client,
            )
        except Exception:
            result = None
        if result is not None:
            results.append(result)
    return sorted(results, key=lambda result: result.ticker)


__all__ = [
    "DEFAULT_HOLDINGS_LOOKBACK_DAYS",
    "DEFAULT_TRANSACTION_CODES",
    "Form4Data",
    "InsiderHolding",
    "InsiderTradingScreenResult",
    "SECClient",
    "SECFiling",
    "SECInsiderTransaction",
    "fetch_form4_data",
    "fetch_insider_transactions",
    "parse_form4",
    "screen_insider_ticker",
    "screen_insider_trading",
    "screen_insider_universe",
]
