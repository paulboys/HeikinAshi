"""Assemble a point-in-time view of the Treasury and macro data.

:func:`build_snapshot` fetches everything the dashboard needs, derives the
quantities that are not published directly -- the expected short rate, curve
spreads, the equity risk premium -- and records per-source staleness.  Any
source that fails is recorded in ``errors`` rather than raised, so a single
throttled endpoint degrades one row instead of blanking the page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from stockcharts.macro.client import MacroClient, utc_now_iso
from stockcharts.macro.config import (
    WATCHLIST,
    Status,
    Threshold,
)
from stockcharts.macro.evaluate import (
    evaluate_auction,
    evaluate_erp,
    evaluate_level,
    evaluate_repo_stress,
    evaluate_risk_off_yield_jump,
    evaluate_term_premium,
    evaluate_yields,
)
from stockcharts.macro.manual import ManualInputs, load_manual_inputs
from stockcharts.macro.series import CORE_FRED_KEYS, SERIES, fred_series_id

DEFAULT_MOVE_WINDOW_DAYS = 5
DEFAULT_TREND_WINDOW_DAYS = 20


@dataclass
class WatchRow:
    """One evaluated watchlist row.

    Attributes:
        key: Row identifier.
        label: Display name.
        now: Formatted current value.
        concerning: Threshold text from the configuration.
        status: Evaluated status.
        reason: Short explanation of the status.
        as_of: Date of the underlying observation.
        source: Where the value came from.
    """

    key: str
    label: str
    now: str
    concerning: str
    status: Status
    reason: str
    as_of: date | None
    source: str


@dataclass
class MacroSnapshot:
    """Everything the dashboard needs for one refresh.

    Attributes:
        fetched_at: UTC timestamp of the refresh.
        curve: Nominal par yield curve, tenors in years as columns.
        real_curve: Real (TIPS) par yield curve.
        series: FRED series keyed by catalog key.
        auctions: Recent auction results, newest first.
        sofr: SOFR fixings.
        repo_ops: Fed repo operation results.
        equity: S&P 500 close prices.
        brent: Brent crude close prices.
        manual: Hand-entered values and checklist state.
        errors: Human-readable failures encountered while fetching.
        as_of_by_source: Latest observation date per source key.
    """

    fetched_at: str = ""
    curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    real_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    series: dict[str, pd.Series] = field(default_factory=dict)
    auctions: pd.DataFrame = field(default_factory=pd.DataFrame)
    sofr: pd.DataFrame = field(default_factory=pd.DataFrame)
    repo_ops: pd.DataFrame = field(default_factory=pd.DataFrame)
    equity: pd.Series = field(default_factory=lambda: pd.Series(dtype="float64"))
    brent: pd.Series = field(default_factory=lambda: pd.Series(dtype="float64"))
    manual: ManualInputs = field(default_factory=ManualInputs)
    errors: list[str] = field(default_factory=list)
    as_of_by_source: dict[str, date] = field(default_factory=dict)

    # -- accessors ---------------------------------------------------------

    def tenor(self, years: float, real: bool = False) -> float | None:
        """Return the latest yield for one tenor.

        Args:
            years: Tenor in years.
            real: True to read the real curve.

        Returns:
            The most recent yield, or None when unavailable.
        """
        frame = self.real_curve if real else self.curve
        if frame.empty or years not in frame.columns:
            return None
        column = frame[years].dropna()
        return float(column.iloc[-1]) if not column.empty else None

    def tenor_change_bp(self, years: float, window: int = DEFAULT_MOVE_WINDOW_DAYS) -> float | None:
        """Return a tenor's change over a trailing window, in basis points.

        Args:
            years: Tenor in years.
            window: Number of observations to look back.

        Returns:
            Change in basis points, or None when there is too little history.
        """
        if self.curve.empty or years not in self.curve.columns:
            return None
        column = self.curve[years].dropna()
        if len(column) < 2:
            return None
        earlier = column.iloc[-min(window + 1, len(column))]
        return float((column.iloc[-1] - earlier) * 100.0)

    def latest(self, key: str) -> float | None:
        """Return the latest value of a FRED series.

        Args:
            key: Catalog key.

        Returns:
            The most recent observation, or None.
        """
        series = self.series.get(key)
        if series is None or series.empty:
            return None
        return float(series.iloc[-1])

    def change_bp(self, key: str, window: int = DEFAULT_TREND_WINDOW_DAYS) -> float | None:
        """Return a FRED series' change over a window, in basis points.

        Args:
            key: Catalog key.
            window: Number of observations to look back.

        Returns:
            Change in basis points, or None when there is too little history.
        """
        series = self.series.get(key)
        if series is None or len(series) < 2:
            return None
        earlier = series.iloc[-min(window + 1, len(series))]
        return float((series.iloc[-1] - earlier) * 100.0)

    # -- derived quantities ------------------------------------------------

    def expected_short_rate(self) -> float | None:
        """Return the expected average short rate implied by the 10y.

        Computed as the 10-year zero-coupon yield minus the term premium.

        Returns:
            The expected short rate in percent, or None.
        """
        zero = self.latest("zero_coupon_10y")
        premium = self.latest("term_premium_10y")
        if zero is None or premium is None:
            return None
        return zero - premium

    def expected_short_change_bp(self, window: int = DEFAULT_TREND_WINDOW_DAYS) -> float | None:
        """Return the change in the expected short rate, in basis points.

        Args:
            window: Number of observations to look back.

        Returns:
            Change in basis points, or None.
        """
        zero_change = self.change_bp("zero_coupon_10y", window)
        premium_change = self.change_bp("term_premium_10y", window)
        if zero_change is None or premium_change is None:
            return None
        return zero_change - premium_change

    def curve_spread_bp(self, short_years: float, long_years: float) -> float | None:
        """Return a curve spread in basis points.

        Args:
            short_years: Shorter tenor.
            long_years: Longer tenor.

        Returns:
            The spread in basis points, or None.
        """
        short = self.tenor(short_years)
        long = self.tenor(long_years)
        if short is None or long is None:
            return None
        return (long - short) * 100.0

    def equity_change_pct(self, window: int = DEFAULT_MOVE_WINDOW_DAYS) -> float | None:
        """Return the equity return over a trailing window, in percent.

        Args:
            window: Number of observations to look back.

        Returns:
            Percentage return, or None.
        """
        if len(self.equity) < 2:
            return None
        earlier = self.equity.iloc[-min(window + 1, len(self.equity))]
        if earlier == 0:
            return None
        return float((self.equity.iloc[-1] / earlier - 1.0) * 100.0)

    def equity_risk_premium(self) -> float | None:
        """Return the trailing earnings yield minus the 10-year yield.

        Uses the hand-entered S&P trailing EPS against the latest index level,
        matching the convention used in the source analysis.

        Returns:
            The premium in percentage points, or None.
        """
        eps = self.manual.value("sp500_trailing_eps")
        ten_year = self.tenor(10.0)
        if eps is None or ten_year is None or self.equity.empty:
            return None
        price = float(self.equity.iloc[-1])
        if price <= 0:
            return None
        return (eps / price) * 100.0 - ten_year

    def latest_auction(self) -> dict[str, Any] | None:
        """Return the most recent auction as a plain mapping.

        Returns:
            The newest auction row, or None when unavailable.
        """
        if self.auctions.empty:
            return None
        row = self.auctions.iloc[0]
        return {
            "auction_date": row.get("auction_date"),
            "bid_to_cover": row.get("bid_to_cover"),
            "indirect_pct": row.get("indirect_pct"),
            "security_term": row.get("security_term"),
        }

    def srf_billions(self) -> float | None:
        """Return the most recent Fed repo acceptance, in billions.

        Returns:
            Accepted amount in billions of dollars, or None.
        """
        if not self.repo_ops.empty and "accepted_bn" in self.repo_ops:
            values = self.repo_ops["accepted_bn"].dropna()
            if not values.empty:
                return float(values.iloc[-1])
        return self.latest("srf_usage")

    def sofr_rate(self) -> float | None:
        """Return the latest SOFR fixing.

        Returns:
            SOFR in percent, or None.
        """
        if not self.sofr.empty and "rate" in self.sofr:
            values = self.sofr["rate"].dropna()
            if not values.empty:
                return float(values.iloc[-1])
        return None


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def _last_index_date(obj: pd.DataFrame | pd.Series) -> date | None:
    """Return the latest index date of a frame or series.

    Args:
        obj: Object with a datetime index.

    Returns:
        The last index entry as a date, or None when empty.
    """
    if obj is None or len(obj) == 0:
        return None
    try:
        return pd.Timestamp(obj.index[-1]).date()
    except (TypeError, ValueError):
        return None


def build_snapshot(
    client: MacroClient | None = None,
    manual: ManualInputs | None = None,
    lookback_days: int = 730,
    include_equities: bool = True,
) -> MacroSnapshot:
    """Fetch and assemble a macro snapshot.

    Every fetch is wrapped: failures land in ``errors`` rather than raising,
    so the dashboard degrades one row at a time.

    Args:
        client: Reusable client.  A default one is created when omitted.
        manual: Hand-entered values.  Loaded from disk when omitted.
        lookback_days: History to request for FRED series.
        include_equities: Whether to fetch yfinance series, which are slower
            and unnecessary for a config-only smoke test.

    Returns:
        The assembled snapshot.
    """
    macro_client = client or MacroClient()
    snapshot = MacroSnapshot(fetched_at=utc_now_iso())
    snapshot.manual = manual if manual is not None else load_manual_inputs()
    snapshot.errors.extend(snapshot.manual.warnings)

    start = date.today() - pd.Timedelta(days=lookback_days).to_pytimedelta()

    # Treasury curves. The feed is paginated by calendar year, so a window
    # longer than year-to-date needs one request per year; completed years are
    # cached indefinitely.
    for real, attr in ((False, "curve"), (True, "real_curve")):
        try:
            frame = macro_client.fetch_treasury_history(lookback_days=lookback_days, real=real)
            setattr(snapshot, attr, frame)
            observed = _last_index_date(frame)
            if observed:
                snapshot.as_of_by_source["treasury_real" if real else "treasury"] = observed
        except Exception as error:
            snapshot.errors.append(f"treasury curve ({attr}): {type(error).__name__}: {error}")

    # FRED series, paced by the client's request delay.
    fred_ids = {key: fred_series_id(key) for key in CORE_FRED_KEYS}
    fetched, errors = macro_client.fetch_many(list(fred_ids.values()), start=start)
    snapshot.errors.extend(errors)
    for key, series_id in fred_ids.items():
        if series_id in fetched:
            snapshot.series[key] = fetched[series_id]
            observed = _last_index_date(fetched[series_id])
            if observed:
                snapshot.as_of_by_source[key] = observed

    # Auctions, SOFR and repo operations.
    for label, call, attr in (
        ("auctions", lambda: macro_client.fetch_auctions("10-Year", limit=8), "auctions"),
        ("sofr", lambda: macro_client.fetch_sofr(limit=30), "sofr"),
        ("repo operations", lambda: macro_client.fetch_repo_ops(limit=30), "repo_ops"),
    ):
        try:
            frame = call()
            setattr(snapshot, attr, frame)
            if attr == "auctions" and not frame.empty:
                newest = frame.iloc[0].get("auction_date")
                if newest is not None and not pd.isna(newest):
                    snapshot.as_of_by_source["auctions"] = pd.Timestamp(newest).date()
            else:
                observed = _last_index_date(frame)
                if observed:
                    snapshot.as_of_by_source[attr] = observed
        except Exception as error:
            snapshot.errors.append(f"{label}: {type(error).__name__}: {error}")

    if include_equities:
        _fetch_market_series(snapshot, lookback_days)

    return snapshot


def _fetch_market_series(snapshot: MacroSnapshot, lookback_days: int) -> None:
    """Fetch Brent and the S&P 500 through the existing yfinance path.

    Args:
        snapshot: Snapshot to populate in place.
        lookback_days: History to request.
    """
    from stockcharts.data.fetch import fetch_ohlc

    lookback = "2y" if lookback_days > 365 else "1y"
    for key, attr in (("brent", "brent"), ("sp500", "equity")):
        ticker = SERIES[key].series_id
        if ticker is None:
            continue
        try:
            frame = fetch_ohlc(ticker, interval="1d", lookback=lookback)
            closes = frame["Close"].dropna()
            setattr(snapshot, attr, closes)
            observed = _last_index_date(closes)
            if observed:
                snapshot.as_of_by_source[key] = observed
        except Exception as error:
            snapshot.errors.append(f"{ticker}: {type(error).__name__}: {error}")


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _format(value: float | None, units: str) -> str:
    """Format a value for the watchlist table.

    Args:
        value: Value to format.
        units: Unit hint from the threshold.

    Returns:
        Display text, or an em dash when unavailable.
    """
    if value is None:
        return "--"
    if units == "pct":
        return f"{value:.2f}%"
    if units == "usd":
        return f"${value:,.2f}"
    if units == "x":
        return f"{value:.2f}x"
    if units == "bp":
        return f"{value:+.0f}bp"
    return f"{value:,.2f}"


def _row(
    spec: Threshold,
    now: str,
    status: Status,
    reason: str,
    snapshot: MacroSnapshot,
    as_of_key: str | None = None,
) -> WatchRow:
    """Build a watchlist row.

    Args:
        spec: Threshold definition.
        now: Formatted current value.
        status: Evaluated status.
        reason: Short explanation.
        snapshot: Snapshot, used for the as-of date.
        as_of_key: Source key to read the as-of date from.

    Returns:
        The assembled row.
    """
    key = as_of_key or spec.series_key or spec.source
    return WatchRow(
        key=spec.key,
        label=spec.label,
        now=now,
        concerning=spec.concerning,
        status=status,
        reason=reason,
        as_of=snapshot.as_of_by_source.get(key),
        source=spec.source,
    )


def evaluate_watchlist(snapshot: MacroSnapshot) -> list[WatchRow]:
    """Evaluate every watchlist row against the snapshot.

    Args:
        snapshot: Assembled macro data.

    Returns:
        One row per configured threshold, in display order.  Always the same
        length regardless of which sources failed.
    """
    rows: list[WatchRow] = []
    ten_year = snapshot.tenor(10.0)
    ten_year_move = snapshot.tenor_change_bp(10.0)

    for spec in WATCHLIST:
        if spec.key == "yields_10y_30y":
            thirty = snapshot.tenor(30.0)
            status, reason = evaluate_yields(ten_year, thirty, ten_year_move, spec)
            now = f"{_format(ten_year, 'pct')} / {_format(thirty, 'pct')}"
            rows.append(_row(spec, now, status, reason, snapshot, "treasury"))

        elif spec.key == "real_10y":
            value = snapshot.tenor(10.0, real=True)
            status, reason = evaluate_level(value, spec)
            rows.append(
                _row(spec, _format(value, "pct"), status, reason, snapshot, "treasury_real")
            )

        elif spec.key == "breakeven_10y":
            value = snapshot.latest("breakeven_10y")
            status, reason = evaluate_level(value, spec)
            rows.append(_row(spec, _format(value, "pct"), status, reason, snapshot))

        elif spec.key == "term_premium":
            value = snapshot.latest("term_premium_10y")
            status, reason = evaluate_term_premium(
                value, snapshot.change_bp("term_premium_10y"), snapshot.expected_short_change_bp()
            )
            rows.append(_row(spec, _format(value, "pct"), status, reason, snapshot))

        elif spec.key == "auction":
            auction = snapshot.latest_auction()
            cover = auction["bid_to_cover"] if auction else None
            indirect = auction["indirect_pct"] if auction else None
            status, reason = evaluate_auction(cover, indirect, spec)
            now = f"{_format(cover, 'x')}, {indirect:.0f}% ind." if indirect is not None else "--"
            rows.append(_row(spec, now, status, reason, snapshot, "auctions"))

        elif spec.key == "hyperscaler_coverage":
            value = snapshot.manual.value("hyperscaler_coverage")
            status, reason = evaluate_level(value, spec)
            row = _row(spec, _format(value, "x"), status, reason, snapshot)
            row.as_of = snapshot.manual.as_of("hyperscaler_coverage")
            rows.append(row)

        elif spec.key == "brent":
            value = float(snapshot.brent.iloc[-1]) if not snapshot.brent.empty else None
            status, reason = evaluate_level(value, spec)
            rows.append(_row(spec, _format(value, "usd"), status, reason, snapshot, "brent"))

        elif spec.key == "equity_risk_premium":
            value = snapshot.equity_risk_premium()
            status, reason = evaluate_erp(value, snapshot.equity_change_pct(), ten_year_move)
            rows.append(_row(spec, _format(value, "pct"), status, reason, snapshot, "sp500"))

        elif spec.key == "repo_stress":
            sofr = snapshot.sofr_rate()
            iorb = snapshot.latest("iorb")
            status, reason = evaluate_repo_stress(sofr, iorb, snapshot.srf_billions())
            spread = (sofr - iorb) * 100.0 if sofr is not None and iorb is not None else None
            rows.append(_row(spec, _format(spread, "bp"), status, reason, snapshot, "sofr"))

    return rows


def auto_scenario_signs(snapshot: MacroSnapshot) -> dict[str, bool]:
    """Compute the scenario signs the dashboard can determine itself.

    Keys here are disjoint from the manually ticked ones, so a computed value
    can never overwrite a user's tick or the reverse.

    Args:
        snapshot: Assembled macro data.

    Returns:
        Sign key to whether it is currently met.
    """
    ten_year_move = snapshot.tenor_change_bp(10.0)
    equity_move = snapshot.equity_change_pct()
    sofr = snapshot.sofr_rate()
    iorb = snapshot.latest("iorb")
    srf = snapshot.srf_billions()

    risk_off_status, _ = evaluate_risk_off_yield_jump(ten_year_move, equity_move)

    # Every key here is one the scenario config marks ``auto``. They are always
    # present, because an auto sign renders as a disabled checkbox: a missing
    # key would leave a box that can never be ticked either way. A sign whose
    # series failed to fetch simply reports False.
    ig_change = snapshot.change_bp("ig_oas")
    claims_change = snapshot.change_bp("initial_claims")
    payrolls_change = snapshot.change_bp("payrolls")
    core_cpi_change = snapshot.change_bp("core_cpi", window=60)
    dollar_change = snapshot.change_bp("dollar_index")
    two_year = snapshot.tenor(2.0)
    fed_funds = snapshot.latest("fed_funds_upper")

    return {
        # A: market dysfunction
        "a_risk_off_jump": risk_off_status in {"watch", "alert"},
        "a_repo_above_admin": bool(sofr is not None and iorb is not None and sofr >= iorb),
        "a_srf_heavy": bool(srf is not None and srf >= 5.0),
        # B: AI credit event
        "b_ig_spreads": bool(ig_change is not None and ig_change > 10.0),
        "b_equity_drop_bond_rally": bool(
            equity_move is not None
            and equity_move < 0
            and ten_year_move is not None
            and ten_year_move < 0
        ),
        # C: recession, then conventional QE
        "c_claims_rising": bool(claims_change is not None and claims_change > 0),
        "c_payrolls_negative": bool(payrolls_change is not None and payrolls_change < 0),
        "c_core_falling": bool(core_cpi_change is not None and core_cpi_change < 0),
        "c_2y_below_ff": bool(
            two_year is not None and fed_funds is not None and (fed_funds - two_year) >= 0.5
        ),
        # D: fiscal dominance
        "d_dollar_down_yields_up": bool(
            dollar_change is not None
            and ten_year_move is not None
            and dollar_change < 0
            and ten_year_move > 0
        ),
    }


__all__ = [
    "DEFAULT_MOVE_WINDOW_DAYS",
    "DEFAULT_TREND_WINDOW_DAYS",
    "MacroSnapshot",
    "WatchRow",
    "auto_scenario_signs",
    "build_snapshot",
    "evaluate_watchlist",
]
