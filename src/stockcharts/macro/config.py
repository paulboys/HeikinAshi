"""Watchlist thresholds, scenario definitions and key dates.

The ``alert`` levels below come from a written macro analysis of the 2026
Treasury selloff; the intermediate ``watch`` levels are interpolated to give
earlier warning.  **None of these are official trigger levels.**  They encode
one reader's judgment of where risk starts to rise and should be re-tuned as
conditions change.

Scenario definitions describe the paths by which the Federal Reserve might
resume buying Treasuries, ordered from most to least plausible.  Each sign
carries an ``auto`` flag: signs that the dashboard can compute are ticked
automatically, and their identifiers are kept disjoint from manually ticked
ones so neither can overwrite the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

Status = Literal["ok", "watch", "alert", "unknown"]
Direction = Literal["above", "below"]
Rule = Literal[
    "level",
    "yields",
    "term_premium",
    "auction",
    "erp",
    "repo",
]

# Ordering used when combining sub-signals into a row status (worst wins).
STATUS_RANK: dict[Status, int] = {"unknown": 0, "ok": 1, "watch": 2, "alert": 3}


@dataclass(frozen=True)
class Threshold:
    """A watchlist row's thresholds and how to evaluate them.

    Attributes:
        key: Stable row identifier.
        label: Display name.
        rule: Which evaluation function handles this row.
        direction: Which way is bad -- ``above`` or ``below``.
        watch: Value at which the row turns amber, if any.
        alert: Value at which the row turns red, if any.
        units: Unit used to format the displayed value.
        concerning: Human-readable threshold text, shown verbatim in the table.
        source: Where the value comes from, shown in the table.
        series_key: Catalog key in :mod:`stockcharts.macro.series`, if any.
    """

    key: str
    label: str
    rule: Rule
    direction: Direction
    watch: float | None
    alert: float | None
    units: str
    concerning: str
    source: str
    series_key: str | None = None


@dataclass(frozen=True)
class ScenarioSign:
    """One sign to watch within a scenario.

    Attributes:
        key: Identifier, unique across every scenario.
        label: Display text.
        auto: True when the dashboard computes this sign rather than the user.
    """

    key: str
    label: str
    auto: bool = False


@dataclass(frozen=True)
class Scenario:
    """A path by which the Fed might resume buying Treasuries.

    Attributes:
        key: Single-letter identifier.
        name: Short title.
        likelihood: Plain-language probability label.
        description: One-line summary of the mechanism.
        signs: Signs to watch.
    """

    key: str
    name: str
    likelihood: str
    description: str
    signs: tuple[ScenarioSign, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class KeyDate:
    """A scheduled event worth tracking.

    Attributes:
        day: Calendar date of the event.
        label: Short event name.
        note: Why it matters.
    """

    day: date
    label: str
    note: str = ""


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

WATCHLIST: tuple[Threshold, ...] = (
    Threshold(
        key="yields_10y_30y",
        label="10y / 30y yields",
        rule="yields",
        direction="above",
        watch=15.0,
        alert=25.0,
        units="pct",
        concerning="Fast moves: 25+ bp in a week, especially on a risk-off day",
        source="treasury",
        series_key="curve_nominal",
    ),
    Threshold(
        key="real_10y",
        label="10y real (TIPS) yield",
        rule="level",
        direction="above",
        watch=2.90,
        alert=3.00,
        units="pct",
        concerning="Above 3%",
        source="treasury",
        series_key="curve_real",
    ),
    Threshold(
        key="breakeven_10y",
        label="10y breakeven inflation",
        rule="level",
        direction="above",
        watch=2.50,
        alert=2.60,
        units="pct",
        concerning="Above 2.6%, a sign inflation expectations are un-anchoring",
        source="fred",
        series_key="breakeven_10y",
    ),
    Threshold(
        key="term_premium",
        label="Term premium (Kim-Wright)",
        rule="term_premium",
        direction="above",
        watch=10.0,
        alert=10.0,
        units="pct",
        concerning="Rising while expected short rates fall, a pure supply or fiscal signal",
        source="fred",
        series_key="term_premium_10y",
    ),
    Threshold(
        key="auction",
        label="Auction results",
        rule="auction",
        direction="below",
        watch=2.45,
        alert=2.30,
        units="x",
        concerning="Cover below 2.3x, falling indirect share, big tails",
        source="fiscaldata",
        series_key="auctions",
    ),
    Threshold(
        key="hyperscaler_coverage",
        label="Hyperscaler order coverage",
        rule="level",
        direction="below",
        watch=1.50,
        alert=1.20,
        units="x",
        concerning="Near 1x, or deals pulled",
        source="manual",
        series_key="hyperscaler_coverage",
    ),
    Threshold(
        key="brent",
        label="Brent crude",
        rule="level",
        direction="above",
        watch=110.0,
        alert=120.0,
        units="usd",
        concerning="Sustained above $110-120",
        source="yfinance",
        series_key="brent",
    ),
    Threshold(
        key="equity_risk_premium",
        label="Equity risk premium",
        rule="erp",
        direction="below",
        watch=0.25,
        alert=0.0,
        units="pct",
        concerning="A stock selloff with rising yields, meaning no hedge from bonds",
        source="derived",
        series_key="sp500",
    ),
    Threshold(
        key="repo_stress",
        label="Repo stress",
        rule="repo",
        direction="above",
        watch=0.0,
        alert=5.0,
        units="bp",
        concerning="Repo rates above the Fed's ceiling, heavy standing-repo-facility use",
        source="nyfed",
        series_key="sofr",
    ),
)

# Secondary thresholds for rows whose rule needs more than one number.
AUCTION_INDIRECT_WATCH = 74.0
AUCTION_INDIRECT_ALERT = 70.0
YIELD_LEVEL_WATCH_10Y = 5.25
YIELD_LEVEL_ALERT_10Y = 5.50
YIELD_LEVEL_WATCH_30Y = 5.50
YIELD_LEVEL_ALERT_30Y = 5.75
SRF_WATCH_BN = 5.0
SRF_ALERT_BN = 25.0
EQUITY_SELLOFF_PCT = -3.0


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        key="A",
        name="Market dysfunction",
        likelihood="Most likely",
        description=(
            "A shock triggers forced unwinding of the basis trade, dealers cannot absorb "
            "the selling, and the Fed buys to restore market function."
        ),
        signs=(
            ScenarioSign("a_risk_off_jump", "Yields jumping on a risk-off day", auto=True),
            ScenarioSign("a_repo_above_admin", "Repo rates above administered rates", auto=True),
            ScenarioSign("a_srf_heavy", "Heavy standing-repo-facility use", auto=True),
            ScenarioSign("a_wide_bid_ask", "Wider bid-ask on off-the-run bonds"),
            ScenarioSign("a_basis_blowout", "Swap spreads or cash-futures basis blowing out"),
        ),
    ),
    Scenario(
        key="B",
        name="AI credit event",
        likelihood="Possible",
        description=(
            "Hyperscaler spreads widen, a weaker issuer stumbles, and equities reprice "
            "sharply. Fed buying follows only if the damage becomes a recession."
        ),
        signs=(
            ScenarioSign("b_ig_spreads", "Investment-grade spreads widening vs index", auto=True),
            ScenarioSign("b_equity_drop_bond_rally", "S&P drops while Treasuries rally", auto=True),
            ScenarioSign("b_order_books", "Order-book coverage falling toward 1x"),
            ScenarioSign("b_deals_pulled", "Deals pulled or restructured"),
            ScenarioSign("b_credit_gates", "Private-credit redemption gates"),
        ),
    ),
    Scenario(
        key="C",
        name="Recession, then conventional QE",
        likelihood="2027 or later",
        description=(
            "The oil shock and high rates break the labor market, the Fed reverses and "
            "cuts toward zero, and only then restarts QE."
        ),
        signs=(
            ScenarioSign("c_claims_rising", "Unemployment claims trending up", auto=True),
            ScenarioSign("c_payrolls_negative", "Payrolls turning negative", auto=True),
            ScenarioSign("c_2y_below_ff", "2y yield far below fed funds", auto=True),
            ScenarioSign("c_core_falling", "Core inflation falling decisively", auto=True),
        ),
    ),
    Scenario(
        key="D",
        name="Fiscal dominance",
        likelihood="Lowest near term",
        description=(
            "Long yields keep climbing, interest costs become politically intolerable, "
            "and pressure builds to cap yields. The regime-change scenario."
        ),
        signs=(
            ScenarioSign("d_dollar_down_yields_up", "Dollar falling while yields rise", auto=True),
            ScenarioSign("d_buybacks_growing", "Buybacks past $6bn per operation or permanent"),
            ScenarioSign("d_buybacks_from_cash", "Buybacks funded from Treasury's cash account"),
            ScenarioSign("d_public_pressure", "Public pressure on the Fed about long rates"),
            ScenarioSign("d_ycc_talk", "Talk of yield curve control"),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Key dates
# ---------------------------------------------------------------------------
# Quoted from the source analysis. Confirm against official calendars before
# relying on them; the dashboard greys out anything more than 30 days past.

KEY_DATES: tuple[KeyDate, ...] = (
    KeyDate(date(2026, 10, 14), "September CPI", "Headline and core inflation print."),
    KeyDate(date(2026, 10, 27), "FOMC meeting begins", "Two-day meeting."),
    KeyDate(date(2026, 10, 28), "FOMC decision", "Rate decision and statement."),
    KeyDate(
        date(2026, 11, 4),
        "Enhanced buyback window ends",
        "Whether Treasury extends it signals how worried it is.",
    ),
    KeyDate(
        date(2026, 11, 4),
        "Quarterly refunding announcement",
        "Any shift in the mix of long-term issuance matters.",
    ),
)


# ---------------------------------------------------------------------------
# Manual input defaults
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManualEntry:
    """A hand-entered value with provenance.

    Attributes:
        value: The entered number.
        as_of: Date the value refers to.
        note: Free-text source note.
    """

    value: float
    as_of: date
    note: str = ""


MANUAL_DEFAULTS: dict[str, ManualEntry] = {
    "hyperscaler_coverage": ManualEntry(
        value=1.9,
        as_of=date(2026, 7, 31),
        note="Order books covering under 2x by July, down from ~5x in February.",
    ),
    "sp500_trailing_eps": ManualEntry(
        value=295.36,
        as_of=date(2026, 6, 30),
        note=(
            "S&P 500 trailing-twelve-month as-reported EPS, quarter ending 2026-06-30. "
            "Source: multpl.com/s-p-500-earnings or the S&P Dow Jones "
            "sp-500-eps-est.xlsx workbook. Operating EPS runs roughly 7 percent "
            "higher and gives a correspondingly smaller premium, so keep the basis "
            "consistent between updates."
        ),
    ),
}

DISCLAIMER = (
    "Thresholds are one reader's judgment of where risk rises, not official trigger "
    "levels. For research and education only; not investment advice."
)


def watchlist_keys() -> tuple[str, ...]:
    """Return the watchlist row keys in display order.

    Returns:
        Row keys, one per watchlist entry.
    """
    return tuple(row.key for row in WATCHLIST)


def scenario_sign_keys() -> tuple[str, ...]:
    """Return every scenario sign key across all scenarios.

    Returns:
        Sign keys in scenario order.
    """
    return tuple(sign.key for scenario in SCENARIOS for sign in scenario.signs)


def worst_status(statuses: list[Status]) -> Status:
    """Return the most severe status in a list.

    Args:
        statuses: Statuses to combine.

    Returns:
        The most severe status, or ``"unknown"`` when the list is empty.
    """
    if not statuses:
        return "unknown"
    return max(statuses, key=lambda s: STATUS_RANK[s])


__all__ = [
    "AUCTION_INDIRECT_ALERT",
    "AUCTION_INDIRECT_WATCH",
    "DISCLAIMER",
    "EQUITY_SELLOFF_PCT",
    "KEY_DATES",
    "MANUAL_DEFAULTS",
    "SCENARIOS",
    "SRF_ALERT_BN",
    "SRF_WATCH_BN",
    "STATUS_RANK",
    "WATCHLIST",
    "YIELD_LEVEL_ALERT_10Y",
    "YIELD_LEVEL_ALERT_30Y",
    "YIELD_LEVEL_WATCH_10Y",
    "YIELD_LEVEL_WATCH_30Y",
    "KeyDate",
    "ManualEntry",
    "Scenario",
    "ScenarioSign",
    "Status",
    "Threshold",
    "scenario_sign_keys",
    "watchlist_keys",
    "worst_status",
]
