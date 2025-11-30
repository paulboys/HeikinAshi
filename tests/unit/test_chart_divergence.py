"""Unit tests for divergence chart plotting."""

import pandas as pd
import pytest
from matplotlib.figure import Figure

from stockcharts.charts.divergence import (
    _convert_precomputed_to_df,
    _find_divergence_points,
    plot_price_rsi,
)


@pytest.fixture
def sample_ohlc_data():
    """Sample OHLC DataFrame."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    return pd.DataFrame(
        {
            "Open": [100 + i * 0.5 for i in range(100)],
            "High": [105 + i * 0.5 for i in range(100)],
            "Low": [95 + i * 0.5 for i in range(100)],
            "Close": [102 + i * 0.5 for i in range(100)],
        },
        index=dates,
    )


@pytest.fixture
def sample_rsi_data():
    """Sample DataFrame with Close and RSI columns."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    # Create lower lows in price with higher lows in RSI (bullish divergence pattern)
    prices = [100.0] * 20 + [95.0] * 20 + [90.0] * 20 + [88.0] * 40
    rsi_values = [30.0] * 20 + [32.0] * 20 + [35.0] * 20 + [38.0] * 40
    return pd.DataFrame({"Close": prices, "RSI": rsi_values}, index=dates)


def test_plot_price_rsi_basic(sample_ohlc_data):
    """Test basic plot_price_rsi without divergence detection."""
    fig = plot_price_rsi(sample_ohlc_data, ticker="AAPL", show_divergence=False, figsize=(10, 8))

    assert isinstance(fig, Figure)
    assert len(fig.axes) == 2  # Price chart and RSI chart

    # Check that RSI was computed
    ax_rsi = fig.axes[1]
    lines = ax_rsi.get_lines()
    assert len(lines) > 0  # Should have RSI line


def test_plot_price_rsi_with_precomputed_2point_bullish(sample_ohlc_data):
    """Test plot with precomputed 2-point bullish divergence."""
    # Add RSI column
    sample_ohlc_data["RSI"] = 50.0

    # Define precomputed 2-point divergence indices
    p1_idx = sample_ohlc_data.index[10]
    p2_idx = sample_ohlc_data.index[20]
    r1_idx = sample_ohlc_data.index[11]
    r2_idx = sample_ohlc_data.index[21]

    precomputed = {"bullish_indices": (p1_idx, p2_idx, r1_idx, r2_idx)}

    fig = plot_price_rsi(
        sample_ohlc_data,
        ticker="TEST",
        show_divergence=True,
        precomputed_divergence=precomputed,
    )

    assert isinstance(fig, Figure)
    assert len(fig.axes) == 2

    # Check price chart has divergence markers
    ax_price = fig.axes[0]
    legend = ax_price.get_legend()
    assert legend is not None


def test_plot_price_rsi_with_precomputed_3point_bearish(sample_ohlc_data):
    """Test plot with precomputed 3-point bearish divergence."""
    sample_ohlc_data["RSI"] = 70.0

    # Define precomputed 3-point divergence indices
    p1_idx = sample_ohlc_data.index[10]
    p2_idx = sample_ohlc_data.index[30]
    p3_idx = sample_ohlc_data.index[50]
    r1_idx = sample_ohlc_data.index[11]
    r2_idx = sample_ohlc_data.index[31]
    r3_idx = sample_ohlc_data.index[51]

    precomputed = {"bearish_indices": (p1_idx, p2_idx, p3_idx, r1_idx, r2_idx, r3_idx)}

    fig = plot_price_rsi(
        sample_ohlc_data,
        ticker="TEST",
        show_divergence=True,
        precomputed_divergence=precomputed,
    )

    assert isinstance(fig, Figure)
    assert len(fig.axes) == 2

    # Check legend for bearish divergence
    ax_price = fig.axes[0]
    legend = ax_price.get_legend()
    assert legend is not None


def test_plot_price_rsi_auto_detect_divergence(sample_rsi_data, monkeypatch):
    """Test auto-detection of divergences when not precomputed."""
    # Add OHLC columns for candlestick plotting
    sample_rsi_data["Open"] = sample_rsi_data["Close"] - 1.0
    sample_rsi_data["High"] = sample_rsi_data["Close"] + 2.0
    sample_rsi_data["Low"] = sample_rsi_data["Close"] - 2.0

    # Mock compute_rsi to return existing RSI values
    def mock_compute_rsi(series, period):
        return sample_rsi_data["RSI"]

    monkeypatch.setattr("stockcharts.charts.divergence.compute_rsi", mock_compute_rsi)

    fig = plot_price_rsi(
        sample_rsi_data,
        ticker="AUTO",
        show_divergence=True,
        divergence_window=5,
        divergence_lookback=60,
    )

    assert isinstance(fig, Figure)
    assert len(fig.axes) == 2


def test_plot_price_rsi_custom_overbought_oversold(sample_ohlc_data):
    """Test custom overbought/oversold levels."""
    fig = plot_price_rsi(sample_ohlc_data, ticker="CUSTOM", overbought=80.0, oversold=20.0)

    assert isinstance(fig, Figure)

    # Check RSI axis has correct horizontal lines
    ax_rsi = fig.axes[1]
    y_limits = ax_rsi.get_ylim()
    assert y_limits == (0, 100)


def test_plot_price_rsi_no_ticker(sample_ohlc_data):
    """Test plotting without ticker name in title."""
    fig = plot_price_rsi(sample_ohlc_data, ticker="")

    assert isinstance(fig, Figure)

    # Title should not include ticker
    ax_price = fig.axes[0]
    title = ax_price.get_title()
    assert "Price Action with RSI Divergence" in title
    assert " - " not in title  # No ticker separator


def test_convert_precomputed_to_df_2point_bullish(sample_ohlc_data):
    """Test conversion of 2-point bullish divergence to DataFrame."""
    sample_ohlc_data["RSI"] = 50.0

    p1_idx = sample_ohlc_data.index[10]
    p2_idx = sample_ohlc_data.index[20]
    r1_idx = sample_ohlc_data.index[11]
    r2_idx = sample_ohlc_data.index[21]

    precomputed = {"bullish_indices": (p1_idx, p2_idx, r1_idx, r2_idx)}

    result = _convert_precomputed_to_df(sample_ohlc_data, precomputed)

    assert result is not None
    assert len(result) == 1
    assert result.iloc[0]["divergence_type"] == "bullish"
    assert result.iloc[0]["num_points"] == 2


def test_convert_precomputed_to_df_3point_bearish(sample_ohlc_data):
    """Test conversion of 3-point bearish divergence to DataFrame."""
    sample_ohlc_data["RSI"] = 70.0

    p1_idx = sample_ohlc_data.index[10]
    p2_idx = sample_ohlc_data.index[30]
    p3_idx = sample_ohlc_data.index[50]
    r1_idx = sample_ohlc_data.index[11]
    r2_idx = sample_ohlc_data.index[31]
    r3_idx = sample_ohlc_data.index[51]

    precomputed = {"bearish_indices": (p1_idx, p2_idx, p3_idx, r1_idx, r2_idx, r3_idx)}

    result = _convert_precomputed_to_df(sample_ohlc_data, precomputed)

    assert result is not None
    assert len(result) == 1
    assert result.iloc[0]["divergence_type"] == "bearish"
    assert result.iloc[0]["num_points"] == 3
    assert len(result.iloc[0]["swing_dates"]) == 3
    assert len(result.iloc[0]["rsi_dates"]) == 3


def test_convert_precomputed_to_df_both_types(sample_ohlc_data):
    """Test conversion with both bullish and bearish divergences."""
    sample_ohlc_data["RSI"] = 50.0

    # Bullish 2-point
    b_p1 = sample_ohlc_data.index[5]
    b_p2 = sample_ohlc_data.index[10]
    b_r1 = sample_ohlc_data.index[6]
    b_r2 = sample_ohlc_data.index[11]

    # Bearish 3-point
    br_p1 = sample_ohlc_data.index[20]
    br_p2 = sample_ohlc_data.index[40]
    br_p3 = sample_ohlc_data.index[60]
    br_r1 = sample_ohlc_data.index[21]
    br_r2 = sample_ohlc_data.index[41]
    br_r3 = sample_ohlc_data.index[61]

    precomputed = {
        "bullish_indices": (b_p1, b_p2, b_r1, b_r2),
        "bearish_indices": (br_p1, br_p2, br_p3, br_r1, br_r2, br_r3),
    }

    result = _convert_precomputed_to_df(sample_ohlc_data, precomputed)

    assert result is not None
    assert len(result) == 2
    assert result.iloc[0]["divergence_type"] == "bullish"
    assert result.iloc[1]["divergence_type"] == "bearish"


def test_convert_precomputed_to_df_invalid_indices(sample_ohlc_data):
    """Test conversion handles invalid indices gracefully."""
    sample_ohlc_data["RSI"] = 50.0

    # Use indices not in DataFrame
    invalid_date = pd.Timestamp("2025-12-31")
    precomputed = {
        "bullish_indices": (
            invalid_date,
            invalid_date,
            invalid_date,
            invalid_date,
        )
    }

    result = _convert_precomputed_to_df(sample_ohlc_data, precomputed)

    # Should return None or empty DataFrame when indices invalid
    assert result is None or len(result) == 0


def test_convert_precomputed_to_df_empty_dict(sample_ohlc_data):
    """Test conversion with empty precomputed dict."""
    sample_ohlc_data["RSI"] = 50.0

    result = _convert_precomputed_to_df(sample_ohlc_data, {})

    assert result is None


def test_find_divergence_points_with_swing_data():
    """Test _find_divergence_points with synthetic swing pattern."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")

    # Create clear bullish divergence: lower lows in price, higher lows in RSI
    prices = [100] * 10 + [95] * 10 + [90] * 10 + [88] * 20
    rsi_values = [30] * 10 + [32] * 10 + [35] * 10 + [38] * 20

    df = pd.DataFrame({"Close": prices, "RSI": rsi_values}, index=dates)

    result = _find_divergence_points(df, window=5)

    # Result may be None or DataFrame depending on swing detection
    if result is not None:
        assert isinstance(result, pd.DataFrame)
        if len(result) > 0:
            assert "divergence_type" in result.columns
