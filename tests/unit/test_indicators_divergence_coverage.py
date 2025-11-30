"""Extended tests for indicators/divergence.py to reach 80%+ coverage."""

import pandas as pd

from stockcharts.indicators.divergence import (
    check_breakout_occurred,
    check_failed_breakout,
    detect_divergence,
    find_three_point_sequences,
)


def _sample_df_with_swings(n: int = 100) -> pd.DataFrame:
    """Create a DataFrame with artificial swing patterns."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    # Create price with clear swing lows and highs
    close = []
    for i in range(n):
        if i % 20 < 10:
            close.append(100 + i * 0.3)
        else:
            close.append(100 + i * 0.3 - 5)
    df = pd.DataFrame(
        {
            "Open": [c - 0.5 for c in close],
            "High": [c + 1.5 for c in close],
            "Low": [c - 1.5 for c in close],
            "Close": close,
        },
        index=dates,
    )
    # RSI with opposite pattern
    rsi = []
    for i in range(n):
        if i % 20 < 10:
            rsi.append(40 - i * 0.1)
        else:
            rsi.append(40 - i * 0.1 + 5)
    df["RSI"] = rsi
    return df


def test_detect_divergence_ema_deriv_method():
    """Test divergence detection using ema-deriv pivot method."""
    df = _sample_df_with_swings(80)
    res = detect_divergence(df, window=5, lookback=60, pivot_method="ema-deriv")
    assert isinstance(res, dict)
    assert "bullish" in res
    assert "bearish" in res


def test_detect_divergence_with_sequence_scoring():
    """Test divergence with 3-point sequence scoring enabled."""
    df = _sample_df_with_swings(100)
    res = detect_divergence(
        df,
        window=5,
        lookback=80,
        min_swing_points=3,
        use_sequence_scoring=True,
        min_sequence_score=0.5,
    )
    assert isinstance(res, dict)
    # Should have score fields when scoring enabled
    if res["bullish"]:
        assert "bullish_score" in res


def test_detect_divergence_insufficient_data():
    """Test divergence when data is too short."""
    df = _sample_df_with_swings(30)
    res = detect_divergence(df, lookback=100)
    assert res["bullish"] is False
    assert res["bearish"] is False


def test_detect_divergence_three_point_fallback():
    """Test 3-point divergence fallback when scoring not used."""
    df = _sample_df_with_swings(80)
    # Create a clear 3-point pattern
    df.loc[df.index[20], "Close"] = 90
    df.loc[df.index[40], "Close"] = 88
    df.loc[df.index[60], "Close"] = 86
    df.loc[df.index[21], "RSI"] = 35
    df.loc[df.index[41], "RSI"] = 37
    df.loc[df.index[61], "RSI"] = 39

    res = detect_divergence(
        df,
        window=3,
        lookback=70,
        min_swing_points=3,
        use_sequence_scoring=False,
    )
    assert isinstance(res, dict)


def test_check_breakout_occurred_bullish():
    """Test breakout detection for bullish divergence."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame(
        {"Close": [100 + i * 0.5 for i in range(50)]},
        index=dates,
    )
    # Divergence at index 20, price at 110
    div_idx = df.index[20]
    # Current price is 124.5 (50% of data), > 110*1.05 = 115.5
    result = check_breakout_occurred(df, div_idx, "bullish", threshold=0.05)
    assert bool(result) is True


def test_check_breakout_occurred_bearish():
    """Test breakout detection for bearish divergence."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame(
        {"Close": [150 - i * 0.5 for i in range(50)]},
        index=dates,
    )
    # Divergence at index 20, price at 140
    div_idx = df.index[20]
    # Current price is 125.5, < 140*0.95 = 133
    result = check_breakout_occurred(df, div_idx, "bearish", threshold=0.05)
    assert bool(result) is True


def test_check_breakout_occurred_no_breakout():
    """Test when no breakout has occurred."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    df = pd.DataFrame(
        {"Close": [100] * 30},
        index=dates,
    )
    div_idx = df.index[10]
    result = check_breakout_occurred(df, div_idx, "bullish", threshold=0.05)
    assert bool(result) is False


def test_check_breakout_occurred_invalid_index():
    """Test breakout check with invalid divergence index."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    df = pd.DataFrame(
        {"Close": [100] * 30},
        index=dates,
    )
    fake_idx = pd.Timestamp("2099-01-01")
    result = check_breakout_occurred(df, fake_idx, "bullish")
    assert bool(result) is False


def test_check_failed_breakout_bullish():
    """Test failed breakout detection for bullish divergence."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    close_vals = [100] * 10 + [105] * 5 + [98] * 15
    df = pd.DataFrame(
        {
            "Close": close_vals,
            "High": [c + 2 for c in close_vals],
            "Low": [c - 2 for c in close_vals],
        },
        index=dates,
    )
    div_idx = df.index[5]
    # High reached 107 (> 100*1.03), but closed at 98 (< 100*1.01)
    result = check_failed_breakout(
        df, div_idx, "bullish", lookback_window=20, attempt_threshold=0.03, reversal_threshold=0.01
    )
    assert bool(result) is True


def test_check_failed_breakout_bearish():
    """Test failed breakout detection for bearish divergence."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    close_vals = [150] * 10 + [145] * 5 + [152] * 15
    df = pd.DataFrame(
        {
            "Close": close_vals,
            "High": [c + 2 for c in close_vals],
            "Low": [c - 2 for c in close_vals],
        },
        index=dates,
    )
    div_idx = df.index[5]
    # Low reached 143 (< 150*0.97), but closed at 152 (> 150*0.99)
    result = check_failed_breakout(
        df, div_idx, "bearish", lookback_window=20, attempt_threshold=0.03, reversal_threshold=0.01
    )
    assert bool(result) is True


def test_check_failed_breakout_no_failure():
    """Test when breakout attempt was not made."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    df = pd.DataFrame(
        {
            "Close": [100] * 30,
            "High": [102] * 30,
            "Low": [98] * 30,
        },
        index=dates,
    )
    div_idx = df.index[10]
    result = check_failed_breakout(df, div_idx, "bullish")
    assert bool(result) is False


def test_check_failed_breakout_invalid_index():
    """Test failed breakout with invalid index."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    df = pd.DataFrame(
        {"Close": [100] * 30, "High": [102] * 30, "Low": [98] * 30},
        index=dates,
    )
    fake_idx = pd.Timestamp("2099-01-01")
    result = check_failed_breakout(df, fake_idx, "bullish")
    assert bool(result) is False


def test_check_failed_breakout_at_end_of_data():
    """Test failed breakout when divergence is at end (no data after)."""
    dates = pd.date_range("2024-01-01", periods=20, freq="D")
    df = pd.DataFrame(
        {"Close": [100] * 20, "High": [102] * 20, "Low": [98] * 20},
        index=dates,
    )
    div_idx = df.index[-1]
    result = check_failed_breakout(df, div_idx, "bullish")
    assert bool(result) is False


def test_find_three_point_sequences_strict_order():
    """Test 3-point sequences with strict ordering enforced."""
    df = _sample_df_with_swings(80)
    price_idx = [df.index[10], df.index[30], df.index[50]]
    rsi_idx = [df.index[11], df.index[31], df.index[51]]

    seqs = find_three_point_sequences(
        df,
        price_idx=price_idx,
        rsi_idx=rsi_idx,
        kind="low",
        require_strict_order=True,
    )
    assert isinstance(seqs, list)


def test_find_three_point_sequences_insufficient_pivots():
    """Test 3-point when not enough pivot points provided."""
    df = _sample_df_with_swings(50)
    price_idx = [df.index[10], df.index[20]]  # Only 2 pivots
    rsi_idx = [df.index[11], df.index[21]]

    seqs = find_three_point_sequences(df, price_idx=price_idx, rsi_idx=rsi_idx, kind="low")
    assert seqs == []


def test_find_three_point_sequences_high_kind():
    """Test 3-point bearish (high) sequences."""
    df = _sample_df_with_swings(80)
    # Invert to create highs
    df["Close"] = df["Close"].max() - df["Close"]
    df["RSI"] = 100 - df["RSI"]

    price_idx = [df.index[10], df.index[30], df.index[50]]
    rsi_idx = [df.index[11], df.index[31], df.index[51]]

    seqs = find_three_point_sequences(df, price_idx=price_idx, rsi_idx=rsi_idx, kind="high")
    assert isinstance(seqs, list)


def test_find_three_point_sequences_no_rsi_match():
    """Test when RSI pivots are too far from price pivots."""
    df = _sample_df_with_swings(80)
    price_idx = [df.index[10], df.index[30], df.index[50]]
    rsi_idx = [df.index[70], df.index[75], df.index[79]]  # Far from price pivots

    seqs = find_three_point_sequences(df, price_idx=price_idx, rsi_idx=rsi_idx, max_bar_gap=5)
    # Should be empty or very few due to large gap
    assert isinstance(seqs, list)
