"""
Shared pytest fixtures and mocks for stockcharts tests.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_ohlc_rsi():
    """
    Generate synthetic OHLC data with clear bullish divergence pattern.
    Returns a DataFrame with OHLC, Volume, RSI suitable for testing.

    Pattern: Price makes lower lows, RSI makes higher lows (bullish divergence).
    """
    dates = pd.date_range(end=datetime.now(), periods=100, freq="D")

    # Create price with clear lower lows pattern
    close = np.ones(100) * 100
    # First low around index 30
    close[25:35] = np.linspace(100, 90, 10)
    close[35:45] = np.linspace(90, 95, 10)
    # Second lower low around index 60
    close[55:65] = np.linspace(95, 85, 10)
    close[65:] = 87

    # Add small noise
    close = close + np.random.normal(0, 0.5, 100)

    # Create OHLC
    high = close + np.abs(np.random.normal(0, 0.5, 100))
    low = close - np.abs(np.random.normal(0, 0.5, 100))
    open_price = close + np.random.normal(0, 0.3, 100)
    volume = np.random.randint(1000000, 5000000, 100)

    # Create RSI with higher lows (bullish divergence signal)
    rsi = np.ones(100) * 50
    # First RSI low around index 30 (lower RSI value)
    rsi[25:35] = np.linspace(50, 30, 10)
    rsi[35:45] = np.linspace(30, 40, 10)
    # Second RSI low around index 60 (higher RSI value - bullish divergence!)
    rsi[55:65] = np.linspace(40, 35, 10)
    rsi[65:] = 40

    rsi = np.clip(rsi, 0, 100)

    df = pd.DataFrame(
        {
            "Open": open_price,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
            "RSI": rsi,
        },
        index=dates,
    )

    return df


@pytest.fixture
def mock_yfinance_download(synthetic_ohlc_rsi):
    """
    Mock yfinance.download to return synthetic OHLC data without hitting network.
    Use this fixture in tests that call fetch_ohlc or similar data fetch functions.

    Usage:
        def test_something(mock_yfinance_download):
            # fetch_ohlc will return synthetic data
            df = fetch_ohlc('AAPL', period='3mo')
    """
    with patch("yfinance.download") as mock_download:
        # Return synthetic data for any ticker
        mock_download.return_value = synthetic_ohlc_rsi.drop("RSI", axis=1)
        yield mock_download


@pytest.fixture
def mock_nasdaq_tickers():
    """
    Mock get_nasdaq_tickers to return a small set of test tickers.
    Prevents fetching the full ~5k ticker list in tests.
    """
    with patch("stockcharts.screener.nasdaq.get_nasdaq_tickers") as mock_get:
        mock_get.return_value = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
        yield mock_get


@pytest.fixture
def sample_divergence_df():
    """
    Minimal DataFrame representing divergence detection results.
    Useful for testing save/export functions.
    """
    return pd.DataFrame(
        {
            "Ticker": ["AAPL", "MSFT"],
            "Company": ["Apple Inc.", "Microsoft Corporation"],
            "Close": [150.25, 380.50],
            "RSI": [45.2, 52.8],
            "Type": ["bullish", "bearish"],
            "Details": ["Price down, RSI up", "Price up, RSI down"],
        }
    )
