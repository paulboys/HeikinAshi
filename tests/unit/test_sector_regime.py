"""Unit tests for sector_regime.py McGlone contrarian analysis."""

from __future__ import annotations

import os
import sys

# Add scripts directory to path for import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from sector_regime import (
    ALL_ETFS,
    ISHARES_SECTOR_ETFS,
    LEVERAGED_BEAR_ETFS,
    LEVERAGED_BULL_ETFS,
    SMALLCAP_SECTOR_ETFS,
    SP500_INDUSTRY_ETFS,
    SP500_SECTOR_ETFS,
    THEMATIC_ETFS,
    get_mcglone_signal,
)

# ============================================================================
# ETF Dictionary Tests
# ============================================================================


def test_sp500_sector_etfs_count() -> None:
    """Should have 11 GICS sector ETFs."""
    assert len(SP500_SECTOR_ETFS) == 11


def test_sp500_sector_etfs_keys() -> None:
    """Should contain key sector SPDR ETFs."""
    expected = {
        "XLK",
        "XLF",
        "XLE",
        "XLV",
        "XLI",
        "XLC",
        "XLY",
        "XLP",
        "XLU",
        "XLRE",
        "XLB",
    }
    assert set(SP500_SECTOR_ETFS.keys()) == expected


def test_sp500_industry_etfs_not_empty() -> None:
    """Industry ETFs should have entries."""
    assert len(SP500_INDUSTRY_ETFS) > 10


def test_smallcap_sector_etfs_prefix() -> None:
    """SmallCap ETFs should have PSC prefix."""
    for ticker in SMALLCAP_SECTOR_ETFS.keys():
        assert ticker.startswith("PSC"), f"{ticker} should start with PSC"


def test_leveraged_bull_etfs_not_empty() -> None:
    """Leveraged bull ETFs should have entries."""
    assert len(LEVERAGED_BULL_ETFS) > 10


def test_leveraged_bear_etfs_not_empty() -> None:
    """Leveraged bear ETFs should have entries."""
    assert len(LEVERAGED_BEAR_ETFS) > 10


def test_all_etfs_combines_all() -> None:
    """ALL_ETFS should combine all other dictionaries."""
    expected_count = (
        len(SP500_SECTOR_ETFS)
        + len(SP500_INDUSTRY_ETFS)
        + len(SMALLCAP_SECTOR_ETFS)
        + len(ISHARES_SECTOR_ETFS)
        + len(LEVERAGED_BULL_ETFS)
        + len(LEVERAGED_BEAR_ETFS)
        + len(THEMATIC_ETFS)
    )
    assert len(ALL_ETFS) == expected_count


def test_etf_names_are_strings() -> None:
    """All ETF descriptions should be strings."""
    for etf_dict in [
        SP500_SECTOR_ETFS,
        SP500_INDUSTRY_ETFS,
        SMALLCAP_SECTOR_ETFS,
        LEVERAGED_BULL_ETFS,
        LEVERAGED_BEAR_ETFS,
    ]:
        for ticker, name in etf_dict.items():
            assert isinstance(ticker, str), f"Ticker {ticker} should be str"
            assert isinstance(name, str), f"Name for {ticker} should be str"


# ============================================================================
# McGlone Signal Logic Tests - BUY Signals
# ============================================================================


def test_buy_signal_all_conditions_met() -> None:
    """BUY when risk-off + VIX >= 30 + drawdown <= -10%."""
    signal, explanation = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=35.0,
        drawdown_pct=-12.0,
        beta=1.2,
    )
    assert signal == "BUY"
    assert "capitulation" in explanation.lower()


def test_buy_signal_vix_at_30() -> None:
    """BUY threshold at VIX exactly 30."""
    signal, _ = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=30.0,
        drawdown_pct=-10.0,
        beta=1.0,
    )
    assert signal == "BUY"


def test_buy_signal_extreme_vix() -> None:
    """BUY with extreme VIX (40+)."""
    signal, _ = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-15.0,
        vix=45.0,
        drawdown_pct=-20.0,
        beta=0.8,
    )
    assert signal == "BUY"


# ============================================================================
# McGlone Signal Logic Tests - WATCH_BUY Signals
# ============================================================================


def test_watch_buy_risk_off_plus_vix() -> None:
    """WATCH_BUY when risk-off + VIX spike but no correction."""
    signal, explanation = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=35.0,
        drawdown_pct=-5.0,  # Only pullback, not correction
        beta=1.0,
    )
    assert signal == "WATCH_BUY"
    assert "correction" in explanation.lower()


def test_watch_buy_risk_off_plus_correction() -> None:
    """WATCH_BUY when risk-off + correction but no VIX spike."""
    signal, explanation = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=22.0,  # Elevated but not spike
        drawdown_pct=-12.0,
        beta=1.0,
    )
    assert signal == "WATCH_BUY"
    assert "vix" in explanation.lower()


# ============================================================================
# McGlone Signal Logic Tests - ACCUMULATE Signals
# ============================================================================


def test_accumulate_risk_off_plus_pullback() -> None:
    """ACCUMULATE when risk-off + pullback (5-10%)."""
    signal, explanation = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=18.0,
        drawdown_pct=-7.0,  # Between -5% and -10%
        beta=1.0,
    )
    assert signal == "ACCUMULATE"
    assert "scale" in explanation.lower()


def test_accumulate_at_pullback_threshold() -> None:
    """ACCUMULATE at exactly -5% drawdown."""
    signal, _ = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-3.0,
        vix=15.0,
        drawdown_pct=-5.0,
        beta=1.0,
    )
    assert signal == "ACCUMULATE"


# ============================================================================
# McGlone Signal Logic Tests - WATCH Signals
# ============================================================================


def test_watch_deep_risk_off() -> None:
    """WATCH when deeply below MA (pct_from_ma < -10%)."""
    signal, explanation = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-12.0,  # Deep risk-off
        vix=18.0,
        drawdown_pct=-3.0,  # No pullback
        beta=1.0,
    )
    assert signal == "WATCH"
    assert "approaching" in explanation.lower()


# ============================================================================
# McGlone Signal Logic Tests - WAIT Signals
# ============================================================================


def test_wait_risk_off_no_capitulation() -> None:
    """WAIT when risk-off but no other conditions."""
    signal, explanation = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-3.0,  # Mild risk-off
        vix=18.0,
        drawdown_pct=-2.0,  # Near highs
        beta=1.0,
    )
    assert signal == "WAIT"
    assert "no capitulation" in explanation.lower()


# ============================================================================
# McGlone Signal Logic Tests - Risk-On Signals
# ============================================================================


def test_extended_far_above_ma() -> None:
    """EXTENDED when risk-on and very far above MA (>15%)."""
    signal, explanation = get_mcglone_signal(
        regime="risk-on",
        pct_from_ma=18.0,
        vix=15.0,
        drawdown_pct=-1.0,
        beta=1.2,
    )
    assert signal == "EXTENDED"
    assert "risky" in explanation.lower() or "chase" in explanation.lower()


def test_hold_uptrend_above_5_pct() -> None:
    """HOLD when risk-on and moderately above MA (5-15%)."""
    signal, explanation = get_mcglone_signal(
        regime="risk-on",
        pct_from_ma=8.0,
        vix=15.0,
        drawdown_pct=-1.0,
        beta=1.0,
    )
    assert signal == "HOLD"
    assert "uptrend" in explanation.lower()


def test_hold_risk_on_high_beta() -> None:
    """HOLD when risk-on with high beta (momentum)."""
    signal, explanation = get_mcglone_signal(
        regime="risk-on",
        pct_from_ma=3.0,  # Just above MA
        vix=15.0,
        drawdown_pct=-1.0,
        beta=1.2,  # High beta
    )
    assert signal == "HOLD"
    assert "beta" in explanation.lower() or "momentum" in explanation.lower()


def test_neutral_risk_on_low_beta() -> None:
    """NEUTRAL when risk-on with low beta and near MA."""
    signal, explanation = get_mcglone_signal(
        regime="risk-on",
        pct_from_ma=2.0,  # Just barely above MA
        vix=15.0,
        drawdown_pct=-1.0,
        beta=0.7,  # Low beta
    )
    assert signal == "NEUTRAL"
    assert "no clear" in explanation.lower()


# ============================================================================
# McGlone Signal Logic Tests - Edge Cases
# ============================================================================


def test_vix_at_boundary_29() -> None:
    """VIX at 29 should NOT trigger spike condition."""
    signal, _ = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=29.9,  # Just below 30
        drawdown_pct=-12.0,
        beta=1.0,
    )
    assert signal == "WATCH_BUY", "Should be WATCH_BUY (waiting for VIX spike)"


def test_drawdown_at_boundary_9() -> None:
    """Drawdown at -9% should NOT trigger correction condition."""
    signal, _ = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=35.0,
        drawdown_pct=-9.0,  # Just above -10%
        beta=1.0,
    )
    assert signal == "WATCH_BUY", "Should be WATCH_BUY (waiting for correction)"


def test_zero_values() -> None:
    """Handle zero values gracefully."""
    signal, _ = get_mcglone_signal(
        regime="risk-on",
        pct_from_ma=0.0,
        vix=0.0,
        drawdown_pct=0.0,
        beta=0.0,
    )
    assert signal in ("NEUTRAL", "HOLD")


def test_negative_beta() -> None:
    """Handle negative beta (inverse correlation)."""
    signal, _ = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=35.0,
        drawdown_pct=-12.0,
        beta=-0.5,  # Inverse correlation
    )
    assert signal == "BUY"  # Still BUY since conditions met


# ============================================================================
# Signal Priority Tests
# ============================================================================


def test_buy_takes_priority_over_watch_buy() -> None:
    """When all conditions met, BUY should be returned, not WATCH_BUY."""
    # All conditions: risk-off + VIX >= 30 + drawdown <= -10%
    signal, _ = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=40.0,
        drawdown_pct=-15.0,
        beta=1.0,
    )
    assert signal == "BUY"


def test_watch_buy_priority_over_accumulate() -> None:
    """WATCH_BUY (2 conditions) should take priority over ACCUMULATE."""
    # risk-off + VIX spike should be WATCH_BUY even with pullback
    signal, _ = get_mcglone_signal(
        regime="risk-off",
        pct_from_ma=-5.0,
        vix=35.0,
        drawdown_pct=-7.0,  # Pullback but not correction
        beta=1.0,
    )
    assert signal == "WATCH_BUY"


def test_risk_off_required_for_buy_signals() -> None:
    """Risk-on should never produce BUY/WATCH_BUY even with VIX + correction."""
    signal, _ = get_mcglone_signal(
        regime="risk-on",  # NOT risk-off
        pct_from_ma=5.0,
        vix=40.0,  # VIX spike
        drawdown_pct=-15.0,  # Correction
        beta=1.0,
    )
    assert signal not in ("BUY", "WATCH_BUY", "ACCUMULATE", "WATCH", "WAIT")


# ============================================================================
# Integration-style Tests
# ============================================================================


def test_get_mcglone_signal_returns_tuple() -> None:
    """get_mcglone_signal should always return (signal, explanation) tuple."""
    result = get_mcglone_signal(
        regime="risk-on",
        pct_from_ma=0.0,
        vix=15.0,
        drawdown_pct=-1.0,
        beta=1.0,
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)


def test_all_possible_signals() -> None:
    """Verify all documented signals can be produced."""
    expected_signals = {
        "BUY",
        "WATCH_BUY",
        "ACCUMULATE",
        "WATCH",
        "WAIT",
        "HOLD",
        "EXTENDED",
        "NEUTRAL",
    }
    produced_signals = set()

    test_cases = [
        # BUY
        ("risk-off", -5.0, 35.0, -12.0, 1.0),
        # WATCH_BUY (VIX spike)
        ("risk-off", -5.0, 35.0, -5.0, 1.0),
        # WATCH_BUY (correction)
        ("risk-off", -5.0, 22.0, -12.0, 1.0),
        # ACCUMULATE
        ("risk-off", -5.0, 18.0, -7.0, 1.0),
        # WATCH
        ("risk-off", -12.0, 18.0, -3.0, 1.0),
        # WAIT
        ("risk-off", -3.0, 18.0, -2.0, 1.0),
        # HOLD (uptrend)
        ("risk-on", 8.0, 15.0, -1.0, 1.0),
        # EXTENDED
        ("risk-on", 18.0, 15.0, -1.0, 1.2),
        # NEUTRAL
        ("risk-on", 2.0, 15.0, -1.0, 0.7),
    ]

    for regime, pct, vix, dd, beta in test_cases:
        signal, _ = get_mcglone_signal(regime, pct, vix, dd, beta)
        produced_signals.add(signal)

    assert (
        produced_signals == expected_signals
    ), f"Missing signals: {expected_signals - produced_signals}"
