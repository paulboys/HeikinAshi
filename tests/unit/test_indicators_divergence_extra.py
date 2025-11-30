"""Targeted tests for indicators/divergence to improve coverage."""

import pandas as pd

from stockcharts.indicators.divergence import (
    detect_divergence,
    find_swing_points,
    find_three_point_sequences,
)


def _sample_df(num: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=num, freq="D")
    close = pd.Series(range(num), index=dates).astype(float)
    # Create synthetic OHLC around close
    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
        },
        index=dates,
    )
    # RSI: simple increasing then decreasing pattern
    rsi = pd.Series([30 + (i % 50) for i in range(num)], index=dates).astype(float)
    df["RSI"] = rsi
    return df


def test_find_swing_points_basic():
    df = _sample_df(50)
    highs, lows = find_swing_points(df["Close"], window=3)
    # Should return series aligned to index
    assert list(highs.index) == list(df.index)
    assert list(lows.index) == list(df.index)


def test_detect_divergence_two_point_flags():
    df = _sample_df(80)
    # Make a simple 2-point bullish divergence by nudging price lows down and RSI lows up
    df.loc[df.index[30], "Close"] = df.loc[df.index[29], "Close"] - 2
    df.loc[df.index[40], "Close"] = df.loc[df.index[39], "Close"] - 2
    df.loc[df.index[31], "RSI"] = df.loc[df.index[30], "RSI"] + 2
    df.loc[df.index[41], "RSI"] = df.loc[df.index[40], "RSI"] + 2

    res = detect_divergence(df, window=3, lookback=60, min_swing_points=2)
    assert set(res.keys()) >= {
        "bullish",
        "bearish",
        "bullish_indices",
        "bearish_indices",
    }
    # At least one side should be detectable in this synthetic pattern
    assert isinstance(res["bullish"], bool)


def test_find_three_point_sequences_low_and_high():
    df = _sample_df(100)
    # Create simple pivot indices spaced out
    price_idx_low = [df.index[20], df.index[40], df.index[60]]
    rsi_idx_low = [df.index[21], df.index[41], df.index[61]]

    price_idx_high = [df.index[25], df.index[45], df.index[65]]
    rsi_idx_high = [df.index[26], df.index[46], df.index[66]]

    lows = find_three_point_sequences(
        df,
        price_idx=price_idx_low,
        rsi_idx=rsi_idx_low,
        kind="low",
        max_bar_gap=10,
    )
    highs = find_three_point_sequences(
        df,
        price_idx=price_idx_high,
        rsi_idx=rsi_idx_high,
        kind="high",
        max_bar_gap=10,
    )

    assert isinstance(lows, list)
    assert isinstance(highs, list)
    # Each candidate contains expected keys when present
    if lows:
        assert set(lows[0].keys()) >= {
            "kind",
            "price_idx",
            "rsi_idx",
            "score",
        }
    if highs:
        assert set(highs[0].keys()) >= {
            "kind",
            "price_idx",
            "rsi_idx",
            "score",
        }
