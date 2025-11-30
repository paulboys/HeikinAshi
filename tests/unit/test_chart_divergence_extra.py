"""Extended tests for charts/divergence.py to reach 80%+ coverage."""

import pandas as pd

from stockcharts.charts.divergence import plot_price_rsi


def _sample_ohlc(n: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": [100 + i * 0.5 for i in range(n)],
            "High": [105 + i * 0.5 for i in range(n)],
            "Low": [95 + i * 0.5 for i in range(n)],
            "Close": [102 + i * 0.5 for i in range(n)],
        },
        index=dates,
    )


def test_plot_price_rsi_auto_detect_no_divergence():
    """Test auto-detection when no divergence exists."""
    df = _sample_ohlc(50)
    fig = plot_price_rsi(df, ticker="TEST", show_divergence=True, divergence_lookback=40)
    assert fig is not None
    assert len(fig.axes) == 2


def test_plot_price_rsi_with_custom_overbought_oversold():
    """Test plotting with custom overbought/oversold levels."""
    df = _sample_ohlc(60)
    fig = plot_price_rsi(df, overbought=80.0, oversold=20.0, show_divergence=False)
    assert fig is not None
    # Check RSI panel has custom levels
    ax_rsi = fig.axes[1]
    # Check for horizontal lines at 80 and 20
    hlines = [line for line in ax_rsi.get_lines() if line.get_linestyle() == "--"]
    assert len(hlines) >= 2


def test_plot_price_rsi_short_data_no_divergence():
    """Test that short data (< lookback) skips divergence detection."""
    df = _sample_ohlc(30)
    fig = plot_price_rsi(df, show_divergence=True, divergence_lookback=60)
    assert fig is not None
    # Should still plot but without divergence markers


def test_plot_price_rsi_empty_ticker():
    """Test plotting without ticker in title."""
    df = _sample_ohlc(50)
    fig = plot_price_rsi(df, ticker="", show_divergence=False)
    assert fig is not None
    title = fig.axes[0].get_title()
    assert "Price Action with RSI Divergence" in title
    assert "TEST" not in title


def test_plot_price_rsi_no_divergence_no_legend():
    """Test that legend is not added when no divergence present."""
    df = _sample_ohlc(50)
    fig = plot_price_rsi(df, show_divergence=False)
    ax_price = fig.axes[0]
    legend = ax_price.get_legend()
    # Should be None or have no divergence entries
    assert legend is None or len(legend.get_texts()) == 0


def test_plot_price_rsi_precomputed_empty_dict():
    """Test precomputed divergence with empty dict."""
    df = _sample_ohlc(50)
    fig = plot_price_rsi(df, precomputed_divergence={})
    assert fig is not None


def test_plot_price_rsi_precomputed_invalid_indices():
    """Test precomputed with indices not in dataframe."""
    df = _sample_ohlc(50)
    fake_idx = pd.Timestamp("2099-01-01")
    precomputed = {"bullish_indices": (fake_idx, fake_idx, fake_idx, fake_idx)}
    fig = plot_price_rsi(df, precomputed_divergence=precomputed)
    assert fig is not None
    # Should skip invalid indices gracefully


def test_plot_price_rsi_3point_precomputed():
    """Test precomputed 3-point divergence rendering."""
    df = _sample_ohlc(80)
    df["RSI"] = 50.0
    p1, p2, p3 = df.index[10], df.index[30], df.index[50]
    r1, r2, r3 = df.index[11], df.index[31], df.index[51]
    precomputed = {"bullish_indices": (p1, p2, p3, r1, r2, r3)}
    fig = plot_price_rsi(df, precomputed_divergence=precomputed, show_divergence=True)
    assert fig is not None
    ax_price = fig.axes[0]
    legend = ax_price.get_legend()
    assert legend is not None


def test_plot_price_rsi_mixed_precomputed():
    """Test both bullish and bearish precomputed indices."""
    df = _sample_ohlc(80)
    df["RSI"] = 50.0
    # 2-point bullish
    pb1, pb2 = df.index[10], df.index[20]
    rb1, rb2 = df.index[11], df.index[21]
    # 2-point bearish
    pb_bear1, pb_bear2 = df.index[40], df.index[50]
    rb_bear1, rb_bear2 = df.index[41], df.index[51]

    precomputed = {
        "bullish_indices": (pb1, pb2, rb1, rb2),
        "bearish_indices": (pb_bear1, pb_bear2, rb_bear1, rb_bear2),
    }
    fig = plot_price_rsi(df, precomputed_divergence=precomputed)
    assert fig is not None
    ax_price = fig.axes[0]
    legend = ax_price.get_legend()
    assert legend is not None
    # Should have both divergence types labeled
    labels = [t.get_text() for t in legend.get_texts()]
    assert any("Bullish" in lbl for lbl in labels)
    assert any("Bearish" in lbl for lbl in labels)


def test_plot_price_rsi_old_2point_format():
    """Test old 2-point divergence format (swing_start_date/swing_end_date)."""
    import matplotlib.pyplot as plt

    from stockcharts.charts.divergence import _plot_price_divergences, _plot_rsi_divergences

    df = _sample_ohlc(80)
    df["RSI"] = [30 + i * 0.3 for i in range(80)]

    # Create old-format divergence DataFrame
    old_div = pd.DataFrame(
        [
            {
                "divergence_type": "bullish",
                "swing_start_date": df.index[10],
                "swing_end_date": df.index[30],
                "price_start": df.loc[df.index[10], "Close"],
                "price_end": df.loc[df.index[30], "Close"],
                "rsi_start": df.loc[df.index[10], "RSI"],
                "rsi_end": df.loc[df.index[30], "RSI"],
            }
        ]
    )

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    ax1.plot(df.index, df["Close"])
    ax2.plot(df.index, df["RSI"])

    # Test plotting functions handle old format
    _plot_price_divergences(ax1, df, old_div)
    _plot_rsi_divergences(ax2, df, old_div)

    assert len(ax1.lines) > 1  # Price + divergence line
    assert len(ax2.lines) > 1  # RSI + divergence line
    plt.close(fig)


def test_plot_divergences_with_invalid_dates():
    """Test that plotting skips divergences with dates not in dataframe."""
    import matplotlib.pyplot as plt

    from stockcharts.charts.divergence import _plot_price_divergences, _plot_rsi_divergences

    df = _sample_ohlc(50)
    df["RSI"] = 50.0

    # Create divergence with invalid dates
    fake_date = pd.Timestamp("2099-12-31")
    bad_div = pd.DataFrame(
        [
            {
                "divergence_type": "bullish",
                "swing_dates": [fake_date, df.index[20]],
                "prices": [100.0, 110.0],
                "rsi_dates": [fake_date, df.index[21]],
                "rsi_values": [30.0, 40.0],
            }
        ]
    )

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    ax1.plot(df.index, df["Close"])
    ax2.plot(df.index, df["RSI"])

    # Should skip invalid divergence gracefully
    _plot_price_divergences(ax1, df, bad_div)
    _plot_rsi_divergences(ax2, df, bad_div)

    # Only original plot lines, no divergence lines added
    assert len(ax1.lines) == 1
    assert len(ax2.lines) == 1
    plt.close(fig)


def test_plot_price_rsi_with_actual_divergence_detection():
    """Test plot with show_divergence=True to trigger _find_divergence_points."""
    # Create data with clear price/RSI divergence pattern
    dates = pd.date_range("2024-01-01", periods=100, freq="D")

    # Price makes lower lows (bullish divergence setup)
    price = [100.0] * 20 + [90.0] * 20 + [80.0] * 20 + [85.0] * 40

    # RSI makes higher lows (bullish divergence)
    rsi = [30.0] * 20 + [35.0] * 20 + [40.0] * 20 + [45.0] * 40

    df = pd.DataFrame(
        {
            "Open": price,
            "High": [p + 2 for p in price],
            "Low": [p - 2 for p in price],
            "Close": price,
            "RSI": rsi,
        },
        index=dates,
    )

    # This should trigger _find_divergence_points function
    fig = plot_price_rsi(df, show_divergence=True, divergence_lookback=90, ticker="TEST")
    assert fig is not None
    assert len(fig.axes) == 2
