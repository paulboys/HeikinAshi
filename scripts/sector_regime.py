"""McGlone-style contrarian sector regime analysis.

Implements Mike McGlone's framework for equity entry timing:
1. Beta (relative strength) BELOW 200-day MA = Risk-off regime
2. VIX spikes to 30-40 = Fear at extreme
3. Market correction = Prices discounted

BUY signal = All 3 conditions met (capitulation complete)

Reference: Bloomberg Intelligence, Mike McGlone
"""

from stockcharts.data.fetch import fetch_ohlc
from stockcharts.screener.beta_regime import screen_beta_regime

# =============================================================================
# S&P 500 GICS Sector ETFs (Select Sector SPDRs) - 11 Sectors
# =============================================================================
SP500_SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLC": "Communication",
    "XLY": "Cons Discret",
    "XLP": "Cons Staples",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
}

# =============================================================================
# S&P 500 Industry ETFs (SPDR Sub-Sectors)
# =============================================================================
SP500_INDUSTRY_ETFS = {
    # Technology
    "XSW": "Software&Svcs",
    "XSD": "Semiconductors",
    "XTL": "Telecom",
    # Financials
    "KBE": "Banks",
    "KRE": "Regional Banks",
    "KIE": "Insurance",
    "KCE": "Capital Mkts",
    # Health Care
    "XBI": "Biotech",
    "XHS": "HC Services",
    "XHE": "HC Equipment",
    "XPH": "Pharma",
    # Consumer
    "XHB": "Homebuilders",
    "XRT": "Retail",
    # Industrials
    "XTN": "Transport",
    "XAR": "Aerospace&Def",
    # Energy/Materials
    "XOP": "Oil&Gas E&P",
    "XES": "Oil&Gas Equip",
    "XME": "Metals&Mining",
}

# =============================================================================
# Invesco S&P SmallCap Sector ETFs (PSC* series)
# =============================================================================
SMALLCAP_SECTOR_ETFS = {
    "PSCT": "SC Tech",
    "PSCF": "SC Financials",
    "PSCE": "SC Energy",
    "PSCH": "SC Health",
    "PSCI": "SC Industrial",
    "PSCD": "SC Cons Disc",
    "PSCC": "SC Cons Stpl",
    "PSCU": "SC Utilities",
    "PSCM": "SC Materials",
}

# =============================================================================
# iShares Sector ETFs
# =============================================================================
ISHARES_SECTOR_ETFS = {
    "IGM": "Tech-Software",
    "IGV": "Exp Tech-Soft",
    "IGE": "Nat Resources",
    "IYT": "Transport",
}

# =============================================================================
# Leveraged Bull ETFs (2x, 3x) - Use for HIGH BETA regime signals
# =============================================================================
LEVERAGED_BULL_ETFS = {
    # 3x Bull
    "TECL": "3x Tech Bull",
    "FAS": "3x Financials",
    "ERX": "3x Energy Bull",
    "CURE": "3x Healthcare",
    "LABU": "3x Biotech Bul",
    "DRN": "3x Real Estate",
    "DPST": "3x Reg Banks",
    "DUSL": "3x Industrial",
    "GUSH": "3x Oil&Gas Bul",
    "RETL": "3x Retail Bull",
    "TPOR": "3x Transport",
    "UTSL": "3x Utilities",
    "WANT": "3x Cons Disc",
    # 2x Bull
    "ROM": "2x Tech Bull",
    "UYG": "2x Financials",
    "DIG": "2x Oil&Gas",
    "RXL": "2x Healthcare",
    "UXI": "2x Industrial",
    "UYM": "2x Materials",
    "URE": "2x Real Estate",
    "UPW": "2x Utilities",
    "UCC": "2x Cons Svcs",
    "UGE": "2x Cons Stpls",
    "LTL": "2x Telecom",
}

# =============================================================================
# Leveraged Bear/Inverse ETFs (2x, 3x) - Use for RISK-OFF hedging
# =============================================================================
LEVERAGED_BEAR_ETFS = {
    # 3x Bear
    "TECS": "3x Tech Bear",
    "FAZ": "3x Fin Bear",
    "ERY": "3x Energy Bear",
    "LABD": "3x Biotech Br",
    "DRV": "3x RE Bear",
    "DRIP": "3x Oil&Gas Br",
    # 2x Bear
    "REW": "2x Tech Bear",
    "SKF": "2x Fin Bear",
    "DUG": "2x Oil&Gas Br",
    "RXD": "2x HC Bear",
    "SIJ": "2x Indust Bear",
    "SMN": "2x Materials",
    "SRS": "2x RE Bear",
    "SDP": "2x Util Bear",
    "SCC": "2x Cons Svc Br",
    "SZK": "2x Cons Stpl",
    "SEF": "2x Fin Short",
    "REK": "2x RE Short",
}

# =============================================================================
# Thematic/Other ETFs
# =============================================================================
THEMATIC_ETFS = {
    "PILL": "3x Pharma",
    "TEXU": "2x Tech",
    "TTXU": "2x Tech",
    "TTXD": "-2x Tech",
    "SXT": "S&P Dividend",
    "SXI": "S&P Intl Div",
}

# =============================================================================
# Combined: All ETFs for comprehensive analysis
# =============================================================================
ALL_ETFS = {
    **SP500_SECTOR_ETFS,
    **SP500_INDUSTRY_ETFS,
    **SMALLCAP_SECTOR_ETFS,
    **ISHARES_SECTOR_ETFS,
    **LEVERAGED_BULL_ETFS,
    **LEVERAGED_BEAR_ETFS,
    **THEMATIC_ETFS,
}


def get_vix_level() -> tuple[float, str]:
    """Fetch current VIX level and return status."""
    try:
        vix_df = fetch_ohlc("^VIX", interval="1d", lookback="1mo")
        if vix_df is not None and not vix_df.empty:
            current_vix = vix_df["Close"].iloc[-1]

            if current_vix >= 40:
                status = "EXTREME_FEAR"
            elif current_vix >= 30:
                status = "HIGH_FEAR"
            elif current_vix >= 20:
                status = "ELEVATED"
            else:
                status = "CALM"

            return current_vix, status
    except Exception:
        pass
    return 0.0, "UNKNOWN"


def get_spy_drawdown() -> tuple[float, float, str]:
    """Calculate SPY drawdown from 52-week high."""
    try:
        spy_df = fetch_ohlc("SPY", interval="1d", lookback="1y")
        if spy_df is not None and not spy_df.empty:
            high_52wk = spy_df["High"].max()
            current_price = spy_df["Close"].iloc[-1]
            drawdown_pct = ((current_price - high_52wk) / high_52wk) * 100

            if drawdown_pct <= -20:
                status = "BEAR_MARKET"
            elif drawdown_pct <= -10:
                status = "CORRECTION"
            elif drawdown_pct <= -5:
                status = "PULLBACK"
            else:
                status = "NEAR_HIGHS"

            return current_price, drawdown_pct, status
    except Exception:
        pass
    return 0.0, 0.0, "UNKNOWN"


def get_mcglone_signal(
    regime: str,
    pct_from_ma: float,
    vix: float,
    drawdown_pct: float,
    beta: float,
) -> tuple[str, str]:
    """Determine McGlone-style contrarian signal.

    McGlone's BUY criteria:
    1. Beta below 200 DMA (risk-off regime)
    2. VIX spikes to 30-40 (fear extreme)
    3. Market correction (prices discounted)

    Returns:
        Tuple of (signal, explanation)
    """
    is_risk_off = regime == "risk-off"
    is_vix_spike = vix >= 30
    is_correction = drawdown_pct <= -10
    is_pullback = drawdown_pct <= -5

    # === McGlone Contrarian BUY Signals ===
    if is_risk_off and is_vix_spike and is_correction:
        return "BUY", "Capitulation - all 3 conditions met"

    if is_risk_off and is_vix_spike:
        return "WATCH_BUY", "Risk-off + VIX spike - wait for correction"

    if is_risk_off and is_correction:
        return "WATCH_BUY", "Risk-off + correction - wait for VIX spike"

    # === Approaching Buy Zone ===
    if is_risk_off and is_pullback:
        return "ACCUMULATE", "Risk-off + pullback - scale in slowly"

    if is_risk_off and pct_from_ma < -10:
        return "WATCH", "Deep risk-off - approaching buy zone"

    if is_risk_off:
        return "WAIT", "Risk-off but no capitulation yet"

    # === Risk-On (Trend Following, Not Entry) ===
    if regime == "risk-on" and pct_from_ma > 15:
        return "EXTENDED", "Far above MA - risky to chase"

    if regime == "risk-on" and pct_from_ma > 5:
        return "HOLD", "Uptrend intact - hold existing"

    if regime == "risk-on" and beta >= 1.0:
        return "HOLD", "Risk-on + high beta - momentum"

    return "NEUTRAL", "No clear signal"


def run_mcglone_analysis(
    etf_dict: dict,
    title: str,
    vix: float,
    vix_status: str,
    spy_price: float,
    drawdown: float,
    dd_status: str,
) -> None:
    """Run McGlone contrarian analysis on sector ETFs."""
    results = screen_beta_regime(
        tickers=list(etf_dict.keys()),
        interval="1wk",
        lookback="10y",
        regime_filter="all",
    )

    print()
    print("=" * 95)
    print(title)
    print("=" * 95)

    # Sort by % from MA (weakest first - those are closer to buy zone)
    sorted_results = sorted(results, key=lambda x: x.pct_from_ma)

    print()
    header = (
        f"{'Sector/Industry':<20} {'ETF':<5} {'Beta':>5} {'Regime':<8} "
        f"{'%FromMA':>8} {'Signal':<12} {'Action'}"
    )
    print(header)
    print("-" * 95)

    buy_signals = []
    watch_signals = []

    for r in sorted_results:
        sector_name = etf_dict.get(r.ticker, r.ticker)

        signal, explanation = get_mcglone_signal(
            regime=r.regime,
            pct_from_ma=r.pct_from_ma,
            vix=vix,
            drawdown_pct=drawdown,
            beta=r.beta,
        )

        # Signal icons
        if signal == "BUY":
            icon = ">>>"
            buy_signals.append((r.ticker, sector_name))
        elif signal in ("WATCH_BUY", "ACCUMULATE"):
            icon = " >>"
            watch_signals.append((r.ticker, sector_name))
        elif signal == "WATCH":
            icon = "  >"
        elif signal == "EXTENDED":
            icon = "  !"
        else:
            icon = "   "

        regime_char = "-" if r.regime == "risk-off" else "+"

        print(
            f"{sector_name:<20} {r.ticker:<5} {r.beta:>5.2f} {regime_char} {r.regime:<7} "
            f"{r.pct_from_ma:>+7.1f}% {signal:<12} {icon}"
        )

    # Summary
    risk_off = [r for r in results if r.regime == "risk-off"]

    print()
    print("-" * 95)
    print(f"REGIME: {len(risk_off)}/{len(results)} sectors in RISK-OFF")

    if buy_signals:
        print(f"\n>>> BUY SIGNALS: {', '.join([s[0] for s in buy_signals])}")
    if watch_signals:
        print(f" >> WATCH FOR BUY: {', '.join([s[0] for s in watch_signals])}")


def main() -> None:
    """Main entry point."""
    import sys

    print()
    print("=" * 95)
    print("McGLONE CONTRARIAN REGIME ANALYSIS")
    print("=" * 95)

    # Fetch market conditions
    print("\nFetching market conditions...")
    vix, vix_status = get_vix_level()
    spy_price, drawdown, dd_status = get_spy_drawdown()

    print()
    print("-" * 95)
    print("MARKET CONDITIONS (McGlone's 3 Criteria)")
    print("-" * 95)

    # Condition 1: VIX
    vix_check = "YES" if vix >= 30 else "NO"
    vix_icon = "[X]" if vix >= 30 else "[ ]"
    print(f"  {vix_icon} VIX Spike (>=30):     VIX = {vix:.1f} ({vix_status}) -> {vix_check}")

    # Condition 2: Drawdown
    dd_check = "YES" if drawdown <= -10 else "NO"
    dd_icon = "[X]" if drawdown <= -10 else "[ ]"
    print(
        f"  {dd_icon} Correction (>=-10%): SPY = ${spy_price:.2f}, "
        f"Drawdown = {drawdown:.1f}% ({dd_status}) -> {dd_check}"
    )

    # Condition 3 will be shown per-sector
    print("  [ ] Risk-Off Regime:   (See sector analysis below)")

    # Count conditions met at market level
    conditions = sum([vix >= 30, drawdown <= -10])
    print()
    print(f"  MARKET-LEVEL: {conditions}/2 macro conditions met")
    if conditions == 2:
        print("  >>> MACRO BUY SETUP - Look for risk-off sectors!")
    elif conditions == 1:
        print("  >> WATCH - One condition met, waiting for alignment")
    else:
        print("     WAIT - No capitulation signals yet")

    # Parse command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--industries":
        run_mcglone_analysis(
            SP500_INDUSTRY_ETFS,
            "S&P 500 INDUSTRY ETFs - McGlone Contrarian Analysis",
            vix,
            vix_status,
            spy_price,
            drawdown,
            dd_status,
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "--all":
        run_mcglone_analysis(
            SP500_SECTOR_ETFS,
            "S&P 500 GICS SECTORS - McGlone Contrarian Analysis",
            vix,
            vix_status,
            spy_price,
            drawdown,
            dd_status,
        )
        run_mcglone_analysis(
            SP500_INDUSTRY_ETFS,
            "S&P 500 INDUSTRIES - McGlone Contrarian Analysis",
            vix,
            vix_status,
            spy_price,
            drawdown,
            dd_status,
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "--smallcap":
        run_mcglone_analysis(
            SMALLCAP_SECTOR_ETFS,
            "S&P SMALLCAP SECTORS - McGlone Contrarian Analysis",
            vix,
            vix_status,
            spy_price,
            drawdown,
            dd_status,
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "--leveraged":
        run_mcglone_analysis(
            LEVERAGED_BULL_ETFS,
            "LEVERAGED BULL ETFs (2x/3x) - McGlone Contrarian Analysis",
            vix,
            vix_status,
            spy_price,
            drawdown,
            dd_status,
        )
        run_mcglone_analysis(
            LEVERAGED_BEAR_ETFS,
            "LEVERAGED BEAR ETFs (2x/3x) - McGlone Contrarian Analysis",
            vix,
            vix_status,
            spy_price,
            drawdown,
            dd_status,
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "--comprehensive":
        run_mcglone_analysis(
            ALL_ETFS,
            "ALL ETFs COMPREHENSIVE - McGlone Contrarian Analysis",
            vix,
            vix_status,
            spy_price,
            drawdown,
            dd_status,
        )
    else:
        run_mcglone_analysis(
            SP500_SECTOR_ETFS,
            "S&P 500 GICS SECTORS - McGlone Contrarian Analysis",
            vix,
            vix_status,
            spy_price,
            drawdown,
            dd_status,
        )

    print()
    print("=" * 95)
    print("McGLONE BUY CRITERIA:")
    print("  1. Sector in RISK-OFF (relative strength below 40-week MA)")
    print("  2. VIX spike to 30-40 (fear extreme)")
    print("  3. Market correction >= 10% (prices discounted)")
    print()
    print("SIGNALS:")
    print("  >>> BUY        = All 3 conditions met - capitulation complete")
    print("   >> WATCH_BUY  = 2/3 conditions - watch for final trigger")
    print("   >> ACCUMULATE = Risk-off + pullback - scale in slowly")
    print("    > WATCH      = Approaching buy zone")
    print("      WAIT       = Risk-off but no capitulation")
    print("      HOLD       = Risk-on uptrend - hold existing")
    print("    ! EXTENDED   = Far above MA - risky to chase")
    print("=" * 95)
    print("OPTIONS:")
    print("  python sector_regime.py                 # 11 GICS sectors only")
    print("  python sector_regime.py --industries    # Sub-sector ETFs")
    print("  python sector_regime.py --smallcap      # SmallCap sector ETFs")
    print("  python sector_regime.py --leveraged     # 2x/3x Bull & Bear ETFs")
    print("  python sector_regime.py --all           # Sectors + Industries")
    print("  python sector_regime.py --comprehensive # ALL ETFs (90+)")
    print("=" * 95)


if __name__ == "__main__":
    main()
