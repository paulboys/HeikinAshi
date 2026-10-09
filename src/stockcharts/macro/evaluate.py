"""Threshold evaluation for the macro watchlist.

Every function here is pure: it takes numbers and returns a status plus a
short human explanation.  That keeps each rule directly callable from a test
without constructing a snapshot, following the same contract as
``scripts/sector_regime.py::get_mcglone_signal``.

Compound rules each get their own named function rather than a generic
dispatcher, because the compound conditions differ in kind -- one compares two
changes, another pairs a level with an equity move -- and naming them keeps
each self-documenting.

Missing data always yields ``("unknown", ...)``.  Nothing here raises, so one
absent series can never blank the whole table.
"""

from __future__ import annotations

from stockcharts.macro.config import (
    AUCTION_INDIRECT_ALERT,
    AUCTION_INDIRECT_WATCH,
    EQUITY_SELLOFF_PCT,
    SRF_ALERT_BN,
    SRF_WATCH_BN,
    YIELD_LEVEL_ALERT_10Y,
    YIELD_LEVEL_ALERT_30Y,
    YIELD_LEVEL_WATCH_10Y,
    YIELD_LEVEL_WATCH_30Y,
    Status,
    Threshold,
    worst_status,
)

NO_DATA: tuple[Status, str] = ("unknown", "no data")


def evaluate_level(value: float | None, spec: Threshold) -> tuple[Status, str]:
    """Compare a level against a threshold's watch and alert values.

    Args:
        value: Observed level.
        spec: Threshold carrying the direction and cut-offs.

    Returns:
        Status and a short explanation.
    """
    if value is None:
        return NO_DATA
    if spec.direction == "above":
        if spec.alert is not None and value >= spec.alert:
            return "alert", f"{value:.2f} at or above {spec.alert:.2f}"
        if spec.watch is not None and value >= spec.watch:
            return "watch", f"{value:.2f} at or above {spec.watch:.2f}"
        if spec.watch is not None:
            return "ok", f"{value:.2f} below {spec.watch:.2f}"
        return "ok", f"{value:.2f}"
    if spec.alert is not None and value <= spec.alert:
        return "alert", f"{value:.2f} at or below {spec.alert:.2f}"
    if spec.watch is not None and value <= spec.watch:
        return "watch", f"{value:.2f} at or below {spec.watch:.2f}"
    if spec.watch is not None:
        return "ok", f"{value:.2f} above {spec.watch:.2f}"
    return "ok", f"{value:.2f}"


def evaluate_move(
    change_bp: float | None,
    watch_bp: float = 15.0,
    alert_bp: float = 25.0,
) -> tuple[Status, str]:
    """Judge the size of a yield move in basis points.

    Args:
        change_bp: Change over the lookback window, in basis points.
        watch_bp: Move at which the status turns amber.
        alert_bp: Move at which the status turns red.

    Returns:
        Status and a short explanation.
    """
    if change_bp is None:
        return NO_DATA
    magnitude = abs(change_bp)
    direction = "up" if change_bp >= 0 else "down"
    if magnitude >= alert_bp:
        return "alert", f"{magnitude:.0f}bp {direction}"
    if magnitude >= watch_bp:
        return "watch", f"{magnitude:.0f}bp {direction}"
    return "ok", f"{magnitude:.0f}bp {direction}"


def evaluate_yields(
    ten_year: float | None,
    thirty_year: float | None,
    ten_year_change_bp: float | None,
    spec: Threshold,
) -> tuple[Status, str]:
    """Judge the 10y and 30y levels together with the recent 10y move.

    Args:
        ten_year: Current 10-year yield in percent.
        thirty_year: Current 30-year yield in percent.
        ten_year_change_bp: 10-year change over the lookback, in basis points.
        spec: Threshold carrying the move cut-offs.

    Returns:
        The worst of the level and move signals, with the reason naming it.
    """
    if ten_year is None and thirty_year is None and ten_year_change_bp is None:
        return NO_DATA

    statuses: list[Status] = []
    reasons: list[str] = []

    if ten_year is not None:
        if ten_year >= YIELD_LEVEL_ALERT_10Y:
            statuses.append("alert")
            reasons.append(f"10y {ten_year:.2f} at or above {YIELD_LEVEL_ALERT_10Y:.2f}")
        elif ten_year >= YIELD_LEVEL_WATCH_10Y:
            statuses.append("watch")
            reasons.append(f"10y {ten_year:.2f} at or above {YIELD_LEVEL_WATCH_10Y:.2f}")
        else:
            statuses.append("ok")

    if thirty_year is not None:
        if thirty_year >= YIELD_LEVEL_ALERT_30Y:
            statuses.append("alert")
            reasons.append(f"30y {thirty_year:.2f} at or above {YIELD_LEVEL_ALERT_30Y:.2f}")
        elif thirty_year >= YIELD_LEVEL_WATCH_30Y:
            statuses.append("watch")
            reasons.append(f"30y {thirty_year:.2f} at or above {YIELD_LEVEL_WATCH_30Y:.2f}")
        else:
            statuses.append("ok")

    watch_bp = spec.watch if spec.watch is not None else 15.0
    alert_bp = spec.alert if spec.alert is not None else 25.0
    move_status, move_reason = evaluate_move(ten_year_change_bp, watch_bp, alert_bp)
    if move_status != "unknown":
        statuses.append(move_status)
        if move_status != "ok":
            reasons.append(f"10y moved {move_reason}")

    status = worst_status(statuses)
    if not reasons:
        reasons.append("levels and move within range")
    return status, "; ".join(reasons)


def evaluate_term_premium(
    tp_level: float | None,
    tp_change_bp: float | None,
    expected_short_change_bp: float | None,
) -> tuple[Status, str]:
    """Flag a term premium rising while expected short rates fall.

    That divergence is the tell that supply or fiscal concern, rather than
    policy expectations, is driving long yields.

    Args:
        tp_level: Current term premium in percent.
        tp_change_bp: Term-premium change over the lookback, in basis points.
        expected_short_change_bp: Expected-short-rate change, in basis points.

    Returns:
        Status and a short explanation.
    """
    if tp_change_bp is None:
        return NO_DATA
    rising = tp_change_bp >= 10.0
    level_text = f"{tp_level:.2f}%" if tp_level is not None else "n/a"

    if rising and expected_short_change_bp is not None and expected_short_change_bp <= -5.0:
        return (
            "alert",
            f"term premium {level_text} up {tp_change_bp:.0f}bp while expected short rates "
            f"fell {abs(expected_short_change_bp):.0f}bp",
        )
    if rising:
        return "watch", f"term premium {level_text} up {tp_change_bp:.0f}bp"
    return "ok", f"term premium {level_text}, {tp_change_bp:+.0f}bp"


def evaluate_auction(
    cover: float | None,
    indirect_pct: float | None,
    spec: Threshold,
) -> tuple[Status, str]:
    """Judge the most recent auction's cover ratio and indirect share.

    Args:
        cover: Bid-to-cover ratio.
        indirect_pct: Indirect bidder share of competitive accepted, in percent.
        spec: Threshold carrying the cover cut-offs.

    Returns:
        The worst of the two signals, with the reason naming which fired.
    """
    if cover is None and indirect_pct is None:
        return NO_DATA

    statuses: list[Status] = []
    reasons: list[str] = []

    if cover is not None:
        if spec.alert is not None and cover <= spec.alert:
            statuses.append("alert")
            reasons.append(f"cover {cover:.2f}x at or below {spec.alert:.2f}x")
        elif spec.watch is not None and cover <= spec.watch:
            statuses.append("watch")
            reasons.append(f"cover {cover:.2f}x at or below {spec.watch:.2f}x")
        else:
            statuses.append("ok")
            reasons.append(f"cover {cover:.2f}x")

    if indirect_pct is not None:
        if indirect_pct <= AUCTION_INDIRECT_ALERT:
            statuses.append("alert")
            reasons.append(
                f"indirect {indirect_pct:.0f}% at or below {AUCTION_INDIRECT_ALERT:.0f}%"
            )
        elif indirect_pct <= AUCTION_INDIRECT_WATCH:
            statuses.append("watch")
            reasons.append(
                f"indirect {indirect_pct:.0f}% at or below {AUCTION_INDIRECT_WATCH:.0f}%"
            )
        else:
            statuses.append("ok")
            reasons.append(f"indirect {indirect_pct:.0f}%")

    return worst_status(statuses), "; ".join(reasons)


def evaluate_repo_stress(
    sofr: float | None,
    iorb: float | None,
    srf_billions: float | None,
) -> tuple[Status, str]:
    """Judge funding stress from SOFR against the administered ceiling.

    Args:
        sofr: Current SOFR fixing in percent.
        iorb: Interest on reserve balances in percent.
        srf_billions: Fed repo operations accepted, in billions of dollars.

    Returns:
        The worst of the spread and facility-use signals.
    """
    if sofr is None and iorb is None and srf_billions is None:
        return NO_DATA

    statuses: list[Status] = []
    reasons: list[str] = []

    if sofr is not None and iorb is not None:
        spread_bp = (sofr - iorb) * 100.0
        if spread_bp >= 5.0:
            statuses.append("alert")
            reasons.append(f"SOFR {spread_bp:+.0f}bp vs IORB")
        elif spread_bp >= 0.0:
            statuses.append("watch")
            reasons.append(f"SOFR {spread_bp:+.0f}bp vs IORB")
        else:
            statuses.append("ok")
            reasons.append(f"SOFR {spread_bp:+.0f}bp vs IORB")

    if srf_billions is not None:
        if srf_billions >= SRF_ALERT_BN:
            statuses.append("alert")
            reasons.append(f"repo facility ${srf_billions:.0f}bn")
        elif srf_billions >= SRF_WATCH_BN:
            statuses.append("watch")
            reasons.append(f"repo facility ${srf_billions:.0f}bn")
        else:
            statuses.append("ok")
            reasons.append(f"repo facility ${srf_billions:.0f}bn")

    return worst_status(statuses), "; ".join(reasons)


def evaluate_erp(
    erp_pct: float | None,
    equity_change_pct: float | None,
    yield_change_bp: float | None,
) -> tuple[Status, str]:
    """Judge the equity risk premium, escalating when bonds stop hedging.

    A thin premium alone is a watch.  It becomes an alert only alongside an
    equity selloff with rising yields, which is the combination that means
    Treasuries are no longer hedging equity risk.

    Args:
        erp_pct: Earnings yield minus the 10-year yield, in percentage points.
        equity_change_pct: Equity return over the lookback, in percent.
        yield_change_bp: 10-year change over the lookback, in basis points.

    Returns:
        Status and a short explanation.
    """
    if erp_pct is None:
        return NO_DATA

    selloff = equity_change_pct is not None and equity_change_pct <= EQUITY_SELLOFF_PCT
    yields_up = yield_change_bp is not None and yield_change_bp > 0

    if erp_pct <= 0.0 and selloff and yields_up:
        return (
            "alert",
            f"ERP {erp_pct:+.2f} with equities {equity_change_pct:.1f}% and yields up "
            f"{yield_change_bp:.0f}bp -- no hedge from bonds",
        )
    if erp_pct <= 0.25:
        return "watch", f"ERP {erp_pct:+.2f}, thin cushion"
    return "ok", f"ERP {erp_pct:+.2f}"


def evaluate_risk_off_yield_jump(
    yield_change_bp: float | None,
    equity_change_pct: float | None,
) -> tuple[Status, str]:
    """Flag yields rising on a day equities fall.

    Treasuries normally rally when equities sell off.  Yields rising instead
    is the clearest tell of market dysfunction.

    Args:
        yield_change_bp: 10-year change, in basis points.
        equity_change_pct: Equity return over the same window, in percent.

    Returns:
        Status and a short explanation.
    """
    if yield_change_bp is None or equity_change_pct is None:
        return NO_DATA
    if equity_change_pct < 0 and yield_change_bp > 0:
        if equity_change_pct <= EQUITY_SELLOFF_PCT and yield_change_bp >= 10.0:
            return (
                "alert",
                f"equities {equity_change_pct:.1f}% with yields +{yield_change_bp:.0f}bp",
            )
        return "watch", f"equities {equity_change_pct:.1f}% with yields +{yield_change_bp:.0f}bp"
    return "ok", "bonds still hedging equities"


__all__ = [
    "NO_DATA",
    "evaluate_auction",
    "evaluate_erp",
    "evaluate_level",
    "evaluate_move",
    "evaluate_repo_stress",
    "evaluate_risk_off_yield_jump",
    "evaluate_term_premium",
    "evaluate_yields",
]
