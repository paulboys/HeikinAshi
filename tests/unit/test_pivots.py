import pandas as pd

from stockcharts.indicators.pivots import ema_derivative_pivots


def test_ema_derivative_pivots_structure():
    prices = [100, 101, 102, 101, 103, 102, 104]
    rsis = [50, 52, 53, 52, 54, 53, 55]
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [1000] * len(prices),
            "RSI": rsis,
        },
        index=pd.date_range("2025-01-01", periods=len(prices), freq="D"),
    )

    piv = ema_derivative_pivots(df, price_col="Close", rsi_col="RSI", price_span=3, rsi_span=3)
    for key in ["price_highs", "price_lows", "rsi_highs", "rsi_lows"]:
        assert key in piv
        assert hasattr(piv[key], "__iter__")

    # Ensure meta present
    assert "meta" in piv
    assert "price_span" in piv["meta"] and "rsi_span" in piv["meta"]
