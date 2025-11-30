import numpy as np
import pandas as pd

from stockcharts.indicators.divergence import detect_divergence


def _df(prices, rsis):
    return pd.DataFrame(
        {
            "Open": prices,
            "High": prices,
            "Low": prices,
            "Close": prices,
            "Volume": [1000] * len(prices),
            "RSI": rsis,
        },
        index=pd.date_range("2025-01-01", periods=len(prices)),
    )


def test_divergence_empty_dataframe():
    df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "RSI"])
    result = detect_divergence(df)
    assert result["bullish"] is False and result["bearish"] is False


def test_divergence_insufficient_bars():
    df = _df([100], [50])
    result = detect_divergence(df, lookback=10, window=2)
    assert result["bullish"] is False and result["bearish"] is False


def test_divergence_with_nans():
    prices = [100, np.nan, 98, 97]
    rsis = [50, 49, np.nan, 48]
    df = _df(prices, rsis)
    result = detect_divergence(df, lookback=4, window=1)
    assert result["bullish"] in (False, True)  # Should not crash
    assert "details" in result or "bullish_details" in result or "bearish_details" in result


def test_divergence_invalid_columns():
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    # Should not raise; function may default to 'Close'/'RSI' missing and return no divergence
    result = detect_divergence(df, price_col="Close", rsi_col="RSI")
    assert result["bullish"] is False and result["bearish"] is False
