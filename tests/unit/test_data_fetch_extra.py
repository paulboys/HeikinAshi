"""Extended tests for data/fetch.py to reach 80%+ coverage."""

import pandas as pd
import pytest

from stockcharts.data.fetch import fetch_ohlc


def _mock_yf_download(ticker, **kwargs):
    """Mock yfinance download that returns a simple DataFrame."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100 + i for i in range(10)],
            "High": [105 + i for i in range(10)],
            "Low": [95 + i for i in range(10)],
            "Close": [102 + i for i in range(10)],
            "Volume": [1000000] * 10,
        },
        index=dates,
    )
    df.index.name = "Date"
    return df


def test_fetch_ohlc_invalid_interval():
    """Test that invalid interval raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported interval"):
        fetch_ohlc("AAPL", interval="5m")


def test_fetch_ohlc_invalid_lookback():
    """Test that invalid lookback raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported lookback"):
        fetch_ohlc("AAPL", lookback="99y")


def test_fetch_ohlc_empty_response(monkeypatch):
    """Test that empty DataFrame raises ValueError."""

    def mock_empty_download(*args: object, **kwargs: object) -> pd.DataFrame:
        return pd.DataFrame()

    monkeypatch.setattr("yfinance.download", mock_empty_download)

    with pytest.raises(ValueError, match="No data returned"):
        fetch_ohlc("INVALID")


def test_fetch_ohlc_missing_columns(monkeypatch):
    """Test that missing required columns raises ValueError."""

    def mock_missing_cols(*args: object, **kwargs: object) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        df = pd.DataFrame({"Open": [100] * 5, "High": [105] * 5}, index=dates)
        df.index.name = "Date"
        return df

    monkeypatch.setattr("yfinance.download", mock_missing_cols)

    with pytest.raises(ValueError, match="Missing expected columns"):
        fetch_ohlc("TEST")


def test_fetch_ohlc_with_start_and_end(monkeypatch):
    """Test fetch with explicit start and end dates."""
    monkeypatch.setattr("yfinance.download", _mock_yf_download)

    df = fetch_ohlc("AAPL", start="2024-01-01", end="2024-01-10")
    assert not df.empty
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_fetch_ohlc_with_invalid_start_falls_back(monkeypatch):
    """Test that invalid start (like '3mo') is ignored and uses lookback."""
    monkeypatch.setattr("yfinance.download", _mock_yf_download)

    # Pass invalid date format in start - should fall back to default lookback
    df = fetch_ohlc("AAPL", start="3mo")
    assert not df.empty


def test_fetch_ohlc_default_lookback(monkeypatch):
    """Test that default lookback='1y' is used when nothing specified."""
    download_calls = []

    def capture_download(*args: object, **kwargs: object) -> pd.DataFrame:
        download_calls.append(kwargs)
        return _mock_yf_download(*args, **kwargs)

    monkeypatch.setattr("yfinance.download", capture_download)

    fetch_ohlc("AAPL")
    assert len(download_calls) == 1
    assert download_calls[0]["period"] == "1y"


def test_fetch_ohlc_multiindex_columns(monkeypatch):
    """Test handling of MultiIndex columns from yfinance."""

    def mock_multiindex_download(*args: object, **kwargs: object) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        df = pd.DataFrame(
            {
                ("Open", "AAPL"): [100] * 5,
                ("High", "AAPL"): [105] * 5,
                ("Low", "AAPL"): [95] * 5,
                ("Close", "AAPL"): [102] * 5,
                ("Volume", "AAPL"): [1000000] * 5,
            },
            index=dates,
        )
        df.index.name = "Date"
        return df

    monkeypatch.setattr("yfinance.download", mock_multiindex_download)

    df = fetch_ohlc("AAPL")
    assert not df.empty
    # Should flatten MultiIndex and keep only needed columns
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_fetch_ohlc_start_and_end_override_lookback(monkeypatch):
    """Test that start/end take precedence over lookback."""
    download_calls = []

    def capture_download(*args: object, **kwargs: object) -> pd.DataFrame:
        download_calls.append(kwargs)
        return _mock_yf_download(*args, **kwargs)

    monkeypatch.setattr("yfinance.download", capture_download)

    fetch_ohlc("AAPL", start="2024-01-01", end="2024-01-31", lookback="1y")
    assert len(download_calls) == 1
    assert "start" in download_calls[0]
    assert "end" in download_calls[0]
    assert "period" not in download_calls[0]
