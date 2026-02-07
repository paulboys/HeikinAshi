"""Unit tests for beta indicators module."""

import numpy as np
import pandas as pd

from stockcharts.indicators.beta import (
    analyze_beta_regime,
    compute_regime_signal,
    compute_relative_strength,
    compute_rolling_beta,
)

# ============================================================================
# compute_rolling_beta tests
# ============================================================================


def test_compute_rolling_beta_basic():
    """Test basic beta calculation with known values."""
    # Create perfectly correlated series (beta should be close to 1)
    np.random.seed(42)
    benchmark = pd.Series(np.random.randn(100).cumsum() + 100)
    asset = benchmark * 1.0  # Same as benchmark

    beta = compute_rolling_beta(asset, benchmark, window=20)

    assert len(beta) == len(asset)
    # Last beta should be very close to 1.0 for identical series
    assert abs(beta.iloc[-1] - 1.0) < 0.1


def test_compute_rolling_beta_high_beta():
    """Test that amplified series has beta > 1."""
    np.random.seed(42)
    benchmark = pd.Series(np.random.randn(100).cumsum() + 100)
    # Asset moves twice as much as benchmark
    asset = 100 + (benchmark - 100) * 2

    beta = compute_rolling_beta(asset, benchmark, window=20)

    # Should have beta around 2.0
    assert beta.iloc[-1] > 1.5


def test_compute_rolling_beta_low_beta():
    """Test that dampened series has beta < 1."""
    np.random.seed(42)
    benchmark = pd.Series(np.random.randn(100).cumsum() + 100)
    # Asset moves half as much as benchmark
    asset = 100 + (benchmark - 100) * 0.5

    beta = compute_rolling_beta(asset, benchmark, window=20)

    # Should have beta around 0.5
    assert beta.iloc[-1] < 0.8


def test_compute_rolling_beta_nan_for_insufficient_data():
    """Test that early values are NaN due to insufficient window."""
    np.random.seed(42)
    benchmark = pd.Series(np.random.randn(30).cumsum() + 100)
    asset = benchmark * 1.1

    beta = compute_rolling_beta(asset, benchmark, window=20)

    # First 19 values should be NaN (window=20 needs 20 data points)
    assert beta.iloc[:19].isna().all()
    assert not beta.iloc[-1:].isna().any()


def test_compute_rolling_beta_empty_series():
    """Test handling of empty series."""
    asset = pd.Series([], dtype=float)
    benchmark = pd.Series([], dtype=float)

    beta = compute_rolling_beta(asset, benchmark, window=20)

    assert len(beta) == 0


def test_compute_rolling_beta_short_series():
    """Test series shorter than window."""
    asset = pd.Series([100, 101, 102])
    benchmark = pd.Series([100, 100.5, 101])

    beta = compute_rolling_beta(asset, benchmark, window=20)

    # All values should be NaN
    assert beta.isna().all()


# ============================================================================
# compute_relative_strength tests
# ============================================================================


def test_compute_relative_strength_basic():
    """Test basic relative strength calculation."""
    asset = pd.Series([100, 105, 110])
    benchmark = pd.Series([100, 100, 100])

    rs = compute_relative_strength(asset, benchmark)

    assert len(rs) == 3
    assert rs.iloc[0] == 1.0
    assert rs.iloc[1] == 1.05
    assert rs.iloc[2] == 1.1


def test_compute_relative_strength_outperformance():
    """Test relative strength when asset outperforms."""
    asset = pd.Series([100, 120, 150])
    benchmark = pd.Series([100, 110, 120])

    rs = compute_relative_strength(asset, benchmark)

    # Asset growing faster than benchmark
    assert rs.iloc[-1] > rs.iloc[0]


def test_compute_relative_strength_underperformance():
    """Test relative strength when asset underperforms."""
    asset = pd.Series([100, 105, 108])
    benchmark = pd.Series([100, 120, 150])

    rs = compute_relative_strength(asset, benchmark)

    # Asset growing slower than benchmark
    assert rs.iloc[-1] < rs.iloc[0]


def test_compute_relative_strength_handles_zeros():
    """Test that zeros in benchmark produce inf/nan appropriately."""
    asset = pd.Series([100, 105, 110])
    benchmark = pd.Series([100, 0, 100])

    rs = compute_relative_strength(asset, benchmark)

    assert np.isinf(rs.iloc[1]) or pd.isna(rs.iloc[1])


# ============================================================================
# compute_regime_signal tests
# ============================================================================


def test_compute_regime_signal_risk_on():
    """Test risk-on signal when RS above MA."""
    # RS steadily increasing, should be above its MA
    rs = pd.Series([1.0, 1.02, 1.04, 1.06, 1.08, 1.10])

    result = compute_regime_signal(rs, ma_period=3)

    # Current RS is above MA, so risk-on
    assert result["regime"] == "risk-on"
    assert result["pct_from_ma"] > 0


def test_compute_regime_signal_risk_off():
    """Test risk-off signal when RS below MA."""
    # RS steadily decreasing, should be below its MA
    rs = pd.Series([1.10, 1.08, 1.06, 1.04, 1.02, 1.00])

    result = compute_regime_signal(rs, ma_period=3)

    # Current RS is below MA, so risk-off
    assert result["regime"] == "risk-off"
    assert result["pct_from_ma"] < 0


def test_compute_regime_signal_insufficient_data():
    """Test that regime is 'insufficient-data' when not enough data for MA."""
    rs = pd.Series([1.0, 1.02])

    result = compute_regime_signal(rs, ma_period=10)

    # Not enough data for MA, regime should be insufficient-data
    assert result["regime"] == "insufficient-data"


def test_compute_regime_signal_exact_at_ma():
    """Test regime when RS exactly equals MA."""
    # Flat RS equals its MA
    rs = pd.Series([1.0] * 10)

    result = compute_regime_signal(rs, ma_period=5)

    # When RS == MA, classified as risk-off (<= comparison)
    # Check that pct_from_ma is approximately 0
    assert abs(result["pct_from_ma"]) < 0.01


# ============================================================================
# analyze_beta_regime tests
# ============================================================================


def test_analyze_beta_regime_basic():
    """Test basic regime analysis returns expected keys."""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=250, freq="D")
    asset_df = pd.DataFrame(
        {
            "Open": np.random.randn(250).cumsum() + 100,
            "High": np.random.randn(250).cumsum() + 102,
            "Low": np.random.randn(250).cumsum() + 98,
            "Close": np.random.randn(250).cumsum() + 100,
            "Volume": np.random.randint(1000000, 5000000, 250),
        },
        index=dates,
    )
    benchmark_df = pd.DataFrame(
        {
            "Open": np.random.randn(250).cumsum() + 400,
            "High": np.random.randn(250).cumsum() + 402,
            "Low": np.random.randn(250).cumsum() + 398,
            "Close": np.random.randn(250).cumsum() + 400,
            "Volume": np.random.randint(10000000, 50000000, 250),
        },
        index=dates,
    )

    result = analyze_beta_regime(asset_df, benchmark_df, ma_period=50, beta_window=20)

    # Check required keys exist
    assert "regime" in result
    assert "relative_strength" in result
    assert "rs_ma" in result
    assert "pct_from_ma" in result
    assert "rolling_beta" in result
    assert "rs_series" in result
    assert "rs_ma_series" in result
    assert "beta_series" in result

    # Regime should be valid
    assert result["regime"] in ["risk-on", "risk-off", "insufficient-data"]


def test_analyze_beta_regime_empty_data():
    """Test handling of empty DataFrames."""
    asset_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    benchmark_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    result = analyze_beta_regime(asset_df, benchmark_df)

    assert result["regime"] == "insufficient-data"


def test_analyze_beta_regime_mismatched_dates():
    """Test handling of mismatched date ranges."""
    dates1 = pd.date_range("2023-01-01", periods=100, freq="D")
    dates2 = pd.date_range("2023-06-01", periods=100, freq="D")  # Different dates

    asset_df = pd.DataFrame(
        {
            "Open": [100] * 100,
            "High": [102] * 100,
            "Low": [98] * 100,
            "Close": [100] * 100,
            "Volume": [1000000] * 100,
        },
        index=dates1,
    )
    benchmark_df = pd.DataFrame(
        {
            "Open": [400] * 100,
            "High": [402] * 100,
            "Low": [398] * 100,
            "Close": [400] * 100,
            "Volume": [10000000] * 100,
        },
        index=dates2,
    )

    # Should handle gracefully (may align on common dates or return unknown)
    result = analyze_beta_regime(asset_df, benchmark_df, ma_period=50)

    # Just verify it returns a valid result without crashing
    assert "regime" in result


def test_analyze_beta_regime_custom_parameters():
    """Test with custom MA and beta window parameters."""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    asset_df = pd.DataFrame(
        {
            "Open": np.random.randn(100).cumsum() + 100,
            "High": np.random.randn(100).cumsum() + 102,
            "Low": np.random.randn(100).cumsum() + 98,
            "Close": np.random.randn(100).cumsum() + 100,
            "Volume": np.random.randint(1000000, 5000000, 100),
        },
        index=dates,
    )
    benchmark_df = pd.DataFrame(
        {
            "Open": np.random.randn(100).cumsum() + 400,
            "High": np.random.randn(100).cumsum() + 402,
            "Low": np.random.randn(100).cumsum() + 398,
            "Close": np.random.randn(100).cumsum() + 400,
            "Volume": np.random.randint(10000000, 50000000, 100),
        },
        index=dates,
    )

    # Use shorter periods for this smaller dataset
    result = analyze_beta_regime(asset_df, benchmark_df, ma_period=20, beta_window=10)

    # Should produce valid result
    assert result["regime"] in ["risk-on", "risk-off", "insufficient-data"]
