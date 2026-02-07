"""Unit tests for beta regime screener module."""

import pandas as pd

from stockcharts.screener.beta_regime import (
    BetaRegimeResult,
    _process_ticker_beta,
    save_results_to_csv,
)

# ============================================================================
# BetaRegimeResult dataclass tests
# ============================================================================


def test_beta_regime_result_creation():
    """Test creating a BetaRegimeResult with all fields."""
    result = BetaRegimeResult(
        ticker="AAPL",
        company_name="Apple Inc.",
        benchmark="SPY",
        regime="risk-on",
        relative_strength=1.25,
        ma_value=1.20,
        pct_from_ma=0.0417,
        beta=1.15,
        close_price=175.50,
        benchmark_price=450.25,
        interval="1d",
        ma_period=200,
    )

    assert result.ticker == "AAPL"
    assert result.regime == "risk-on"
    assert result.beta == 1.15
    assert result.ma_period == 200


def test_beta_regime_result_risk_off():
    """Test creating a risk-off BetaRegimeResult."""
    result = BetaRegimeResult(
        ticker="XYZ",
        company_name="XYZ Corp",
        benchmark="SPY",
        regime="risk-off",
        relative_strength=0.85,
        ma_value=0.92,
        pct_from_ma=-0.0761,
        beta=0.75,
        close_price=25.50,
        benchmark_price=450.25,
        interval="1wk",
        ma_period=40,
    )

    assert result.regime == "risk-off"
    assert result.pct_from_ma < 0
    assert result.interval == "1wk"


# ============================================================================
# _process_ticker_beta tests
# ============================================================================


def test_process_ticker_beta_returns_none_for_empty_df():
    """Test that empty DataFrame returns None."""
    asset_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    benchmark_df = pd.DataFrame(
        {
            "Open": [100],
            "High": [102],
            "Low": [98],
            "Close": [100],
            "Volume": [1000000],
        },
        index=pd.date_range("2023-01-01", periods=1),
    )

    result = _process_ticker_beta(
        ticker="TEST",
        df=asset_df,
        benchmark="SPY",
        benchmark_df=benchmark_df,
        interval="1d",
        effective_ma_period=200,
        beta_window=60,
        regime_filter="all",
        min_price=None,
        max_price=None,
        min_volume=None,
        company_name="Test Corp",
    )

    assert result is None


def test_process_ticker_beta_filters_by_min_price():
    """Test that min_price filter works."""
    import numpy as np

    dates = pd.date_range("2023-01-01", periods=300, freq="D")
    np.random.seed(42)

    # Asset price constant around $5 (below min_price of 10)
    # Use small noise around base price to avoid all-zero returns
    base_price = 5.0
    noise = np.random.randn(300) * 0.1
    asset_df = pd.DataFrame(
        {
            "Open": base_price + noise - 0.1,
            "High": base_price + noise + 0.2,
            "Low": base_price + noise - 0.2,
            "Close": base_price + noise,
            "Volume": np.random.randint(1000000, 5000000, 300),
        },
        index=dates,
    )
    benchmark_df = pd.DataFrame(
        {
            "Open": np.random.randn(300).cumsum() + 400,
            "High": np.random.randn(300).cumsum() + 402,
            "Low": np.random.randn(300).cumsum() + 398,
            "Close": np.random.randn(300).cumsum() + 400,
            "Volume": np.random.randint(10000000, 50000000, 300),
        },
        index=dates,
    )

    result = _process_ticker_beta(
        ticker="CHEAP",
        df=asset_df,
        benchmark="SPY",
        benchmark_df=benchmark_df,
        interval="1d",
        effective_ma_period=50,
        beta_window=20,
        regime_filter="all",
        min_price=10.0,  # Filter out stocks below $10
        max_price=None,
        min_volume=None,
        company_name="Cheap Stock",
    )

    # Should be filtered out due to low price (price is ~$5)
    assert result is None


def test_process_ticker_beta_filters_by_max_price():
    """Test that max_price filter works."""
    import numpy as np

    dates = pd.date_range("2023-01-01", periods=300, freq="D")
    np.random.seed(42)

    # Asset price around $500 (above max_price of 100)
    asset_df = pd.DataFrame(
        {
            "Open": np.random.randn(300).cumsum() + 500,
            "High": np.random.randn(300).cumsum() + 502,
            "Low": np.random.randn(300).cumsum() + 498,
            "Close": np.random.randn(300).cumsum() + 500,
            "Volume": np.random.randint(1000000, 5000000, 300),
        },
        index=dates,
    )
    benchmark_df = pd.DataFrame(
        {
            "Open": np.random.randn(300).cumsum() + 400,
            "High": np.random.randn(300).cumsum() + 402,
            "Low": np.random.randn(300).cumsum() + 398,
            "Close": np.random.randn(300).cumsum() + 400,
            "Volume": np.random.randint(10000000, 50000000, 300),
        },
        index=dates,
    )

    result = _process_ticker_beta(
        ticker="EXPENSIVE",
        df=asset_df,
        benchmark="SPY",
        benchmark_df=benchmark_df,
        interval="1d",
        effective_ma_period=50,
        beta_window=20,
        regime_filter="all",
        min_price=None,
        max_price=100.0,  # Filter out stocks above $100
        min_volume=None,
        company_name="Expensive Stock",
    )

    # Should be filtered out due to high price
    assert result is None


def test_process_ticker_beta_filters_by_regime():
    """Test that regime_filter correctly filters results."""
    import numpy as np

    dates = pd.date_range("2023-01-01", periods=300, freq="D")
    np.random.seed(42)

    # Create steadily declining RS (risk-off condition)
    asset_prices = 100 + np.arange(300) * 0.1
    benchmark_prices = 400 + np.arange(300) * 0.5  # Benchmark rises faster

    asset_df = pd.DataFrame(
        {
            "Open": asset_prices - 1,
            "High": asset_prices + 1,
            "Low": asset_prices - 2,
            "Close": asset_prices,
            "Volume": np.random.randint(1000000, 5000000, 300),
        },
        index=dates,
    )
    benchmark_df = pd.DataFrame(
        {
            "Open": benchmark_prices - 1,
            "High": benchmark_prices + 1,
            "Low": benchmark_prices - 2,
            "Close": benchmark_prices,
            "Volume": np.random.randint(10000000, 50000000, 300),
        },
        index=dates,
    )

    # Test with regime_filter="risk-on" - should filter out this risk-off stock
    result = _process_ticker_beta(
        ticker="WEAK",
        df=asset_df,
        benchmark="SPY",
        benchmark_df=benchmark_df,
        interval="1d",
        effective_ma_period=50,
        beta_window=20,
        regime_filter="risk-on",  # Only want risk-on stocks
        min_price=None,
        max_price=None,
        min_volume=None,
        company_name="Weak Stock",
    )

    # If the stock is risk-off, it should be filtered when looking for risk-on
    # (result could be None if filtered, or have regime=risk-off if "all")
    # With this declining RS, it should be risk-off and thus filtered out
    assert result is None


# ============================================================================
# save_results_to_csv tests
# ============================================================================


def test_save_results_to_csv_empty_list(tmp_path, capsys):
    """Test saving empty results prints message."""
    save_results_to_csv([], str(tmp_path / "empty.csv"))

    captured = capsys.readouterr()
    assert "No results to save" in captured.out


def test_save_results_to_csv_writes_file(tmp_path):
    """Test that results are written to CSV correctly."""
    results = [
        BetaRegimeResult(
            ticker="AAPL",
            company_name="Apple Inc.",
            benchmark="SPY",
            regime="risk-on",
            relative_strength=1.25,
            ma_value=1.20,
            pct_from_ma=0.0417,
            beta=1.15,
            close_price=175.50,
            benchmark_price=450.25,
            interval="1d",
            ma_period=200,
        ),
        BetaRegimeResult(
            ticker="MSFT",
            company_name="Microsoft Corp.",
            benchmark="SPY",
            regime="risk-off",
            relative_strength=0.95,
            ma_value=1.00,
            pct_from_ma=-0.05,
            beta=0.90,
            close_price=350.00,
            benchmark_price=450.25,
            interval="1d",
            ma_period=200,
        ),
    ]

    output_file = tmp_path / "results.csv"
    save_results_to_csv(results, str(output_file))

    assert output_file.exists()

    # Read and verify contents
    df = pd.read_csv(output_file)
    assert len(df) == 2
    assert "Ticker" in df.columns
    assert "Regime" in df.columns
    assert "Beta" in df.columns
    assert df.iloc[0]["Ticker"] == "AAPL"
    assert df.iloc[1]["Ticker"] == "MSFT"


def test_save_results_to_csv_all_fields_present(tmp_path):
    """Test that all expected fields are in the CSV."""
    results = [
        BetaRegimeResult(
            ticker="TEST",
            company_name="Test Corp",
            benchmark="QQQ",
            regime="risk-on",
            relative_strength=1.10,
            ma_value=1.05,
            pct_from_ma=0.0476,
            beta=1.25,
            close_price=50.00,
            benchmark_price=400.00,
            interval="1wk",
            ma_period=40,
        ),
    ]

    output_file = tmp_path / "test.csv"
    save_results_to_csv(results, str(output_file))

    df = pd.read_csv(output_file)

    expected_columns = [
        "Ticker",
        "Company_Name",
        "Benchmark",
        "Regime",
        "Relative_Strength",
        "MA_Value",
        "Pct_From_MA",
        "Beta",
        "Close_Price",
        "Benchmark_Price",
        "Interval",
        "MA_Period",
    ]

    for col in expected_columns:
        assert col in df.columns, f"Missing column: {col}"
