"""Catalog of macro data series used by the Treasury yield dashboard.

Each entry names where a series comes from and how to display it.  Sources:

* ``treasury`` -- the Treasury.gov par-yield XML feed, which returns an entire
  year of the full curve in one request.
* ``fred`` -- the keyless FRED CSV endpoint, one request per series.
* ``yfinance`` -- the existing :func:`stockcharts.data.fetch.fetch_ohlc` path.
* ``nyfed`` -- the New York Fed markets API.
* ``fiscaldata`` -- the Treasury FiscalData auction query API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SeriesSource = Literal["treasury", "fred", "yfinance", "nyfed", "fiscaldata", "manual", "derived"]
SeriesUnits = Literal["pct", "bp", "ratio", "x", "usd", "index", "usd_bn", "count"]


@dataclass(frozen=True)
class SeriesSpec:
    """Metadata for one macro series.

    Attributes:
        key: Stable identifier used inside snapshots and manual overrides.
        label: Human-readable name for display.
        source: Which fetcher retrieves this series.
        units: Unit of the stored value, used for formatting.
        series_id: Provider-side identifier, when the source needs one.
        note: Short description of what the series measures.
    """

    key: str
    label: str
    source: SeriesSource
    units: SeriesUnits
    series_id: str | None = None
    note: str = ""


# ---------------------------------------------------------------------------
# Treasury.gov par yield curve datasets
# ---------------------------------------------------------------------------

TREASURY_NOMINAL_DATASET = "daily_treasury_yield_curve"
TREASURY_REAL_DATASET = "daily_treasury_real_yield_curve"

# Field name in the Treasury Atom feed -> tenor expressed in years.
TENOR_FIELDS: dict[str, float] = {
    "BC_1MONTH": 1 / 12,
    "BC_2MONTH": 2 / 12,
    "BC_3MONTH": 0.25,
    "BC_4MONTH": 4 / 12,
    "BC_6MONTH": 0.5,
    "BC_1YEAR": 1.0,
    "BC_2YEAR": 2.0,
    "BC_3YEAR": 3.0,
    "BC_5YEAR": 5.0,
    "BC_7YEAR": 7.0,
    "BC_10YEAR": 10.0,
    "BC_20YEAR": 20.0,
    "BC_30YEAR": 30.0,
}

# The real-yield feed publishes a shorter curve under different field names.
REAL_TENOR_FIELDS: dict[str, float] = {
    "TC_5YEAR": 5.0,
    "TC_7YEAR": 7.0,
    "TC_10YEAR": 10.0,
    "TC_20YEAR": 20.0,
    "TC_30YEAR": 30.0,
}

# Tenors surfaced on the dashboard's nominal panel.
HEADLINE_TENORS: tuple[float, ...] = (2.0, 5.0, 10.0, 20.0, 30.0)


# ---------------------------------------------------------------------------
# Series catalog
# ---------------------------------------------------------------------------

SERIES: dict[str, SeriesSpec] = {
    # --- FRED -------------------------------------------------------------
    "breakeven_10y": SeriesSpec(
        key="breakeven_10y",
        label="10y breakeven inflation",
        source="fred",
        units="pct",
        series_id="T10YIE",
        note="Market-implied 10-year average inflation.",
    ),
    "breakeven_5y": SeriesSpec(
        key="breakeven_5y",
        label="5y breakeven inflation",
        source="fred",
        units="pct",
        series_id="T5YIE",
    ),
    "term_premium_10y": SeriesSpec(
        key="term_premium_10y",
        label="10y term premium (Kim-Wright)",
        source="fred",
        units="pct",
        series_id="THREEFYTP10",
        note="Publishes with a lag; check the as-of date before relying on it.",
    ),
    "zero_coupon_10y": SeriesSpec(
        key="zero_coupon_10y",
        label="10y zero-coupon yield",
        source="fred",
        units="pct",
        series_id="THREEFY10",
        note="Paired with the term premium to derive the expected short rate.",
    ),
    "iorb": SeriesSpec(
        key="iorb",
        label="Interest on reserve balances",
        source="fred",
        units="pct",
        series_id="IORB",
        note="Administered-rate ceiling that SOFR is compared against.",
    ),
    "srf_usage": SeriesSpec(
        key="srf_usage",
        label="Fed repo operations outstanding",
        source="fred",
        units="usd_bn",
        series_id="RPONTSYD",
    ),
    "fed_funds_upper": SeriesSpec(
        key="fed_funds_upper",
        label="Fed funds target (upper)",
        source="fred",
        units="pct",
        series_id="DFEDTARU",
    ),
    "ig_oas": SeriesSpec(
        key="ig_oas",
        label="Investment-grade credit OAS",
        source="fred",
        units="pct",
        series_id="BAMLC0A0CM",
        note="Closest free proxy for hyperscaler spread stress.",
    ),
    "hy_oas": SeriesSpec(
        key="hy_oas",
        label="High-yield credit OAS",
        source="fred",
        units="pct",
        series_id="BAMLH0A0HYM2",
    ),
    "dollar_index": SeriesSpec(
        key="dollar_index",
        label="Broad dollar index",
        source="fred",
        units="index",
        series_id="DTWEXBGS",
    ),
    "initial_claims": SeriesSpec(
        key="initial_claims",
        label="Initial jobless claims",
        source="fred",
        units="count",
        series_id="ICSA",
    ),
    "payrolls": SeriesSpec(
        key="payrolls",
        label="Nonfarm payrolls",
        source="fred",
        units="count",
        series_id="PAYEMS",
    ),
    "core_cpi": SeriesSpec(
        key="core_cpi",
        label="Core CPI",
        source="fred",
        units="index",
        series_id="CPILFESL",
    ),
    "brent_fred": SeriesSpec(
        key="brent_fred",
        label="Brent crude (FRED fallback)",
        source="fred",
        units="usd",
        series_id="DCOILBRENTEU",
        note="Lags about a week; BZ=F via yfinance is the primary source.",
    ),
    # --- yfinance ---------------------------------------------------------
    "brent": SeriesSpec(
        key="brent",
        label="Brent crude",
        source="yfinance",
        units="usd",
        series_id="BZ=F",
    ),
    "sp500": SeriesSpec(
        key="sp500",
        label="S&P 500",
        source="yfinance",
        units="index",
        series_id="^GSPC",
    ),
    # --- New York Fed -----------------------------------------------------
    "sofr": SeriesSpec(
        key="sofr",
        label="SOFR",
        source="nyfed",
        units="pct",
        note="Fresher than the FRED mirror and carries percentiles and volume.",
    ),
    "repo_ops": SeriesSpec(
        key="repo_ops",
        label="Fed repo operation results",
        source="nyfed",
        units="usd_bn",
    ),
    # --- Treasury ---------------------------------------------------------
    "curve_nominal": SeriesSpec(
        key="curve_nominal",
        label="Nominal par yield curve",
        source="treasury",
        units="pct",
        series_id=TREASURY_NOMINAL_DATASET,
        note="One request returns a full year of all 13 tenors.",
    ),
    "curve_real": SeriesSpec(
        key="curve_real",
        label="Real (TIPS) par yield curve",
        source="treasury",
        units="pct",
        series_id=TREASURY_REAL_DATASET,
    ),
    "auctions": SeriesSpec(
        key="auctions",
        label="Treasury auction results",
        source="fiscaldata",
        units="ratio",
    ),
    # --- Manual -----------------------------------------------------------
    "hyperscaler_coverage": SeriesSpec(
        key="hyperscaler_coverage",
        label="Hyperscaler bond order coverage",
        source="manual",
        units="x",
        note="Syndicate data; no free API exists.",
    ),
    "sp500_trailing_eps": SeriesSpec(
        key="sp500_trailing_eps",
        label="S&P 500 trailing EPS",
        source="manual",
        units="usd",
        note="Entered quarterly; combined with ^GSPC to derive the earnings yield.",
    ),
}

# FRED series fetched on every refresh.  Kept small because the keyless CSV
# endpoint throttles rapid sequential requests.
CORE_FRED_KEYS: tuple[str, ...] = (
    "breakeven_10y",
    "term_premium_10y",
    "zero_coupon_10y",
    "iorb",
    "srf_usage",
    # Needed by the automatic scenario signs. Every sign marked ``auto`` in
    # the scenario config renders as a disabled checkbox, so its series must
    # be fetched or the box can never tick.
    "ig_oas",
    "initial_claims",
    "payrolls",
    "core_cpi",
    "dollar_index",
    "fed_funds_upper",
)


def fred_series_id(key: str) -> str:
    """Return the FRED identifier for a catalog key.

    Args:
        key: Catalog key, which must name a series whose source is FRED.

    Returns:
        The FRED series identifier.

    Raises:
        KeyError: If the key is not in the catalog.
        ValueError: If the named series is not a FRED series.
    """
    spec = SERIES[key]
    if spec.source != "fred" or spec.series_id is None:
        raise ValueError(f"{key!r} is not a FRED series")
    return spec.series_id


__all__ = [
    "CORE_FRED_KEYS",
    "HEADLINE_TENORS",
    "REAL_TENOR_FIELDS",
    "SERIES",
    "TENOR_FIELDS",
    "TREASURY_NOMINAL_DATASET",
    "TREASURY_REAL_DATASET",
    "SeriesSpec",
    "fred_series_id",
]
