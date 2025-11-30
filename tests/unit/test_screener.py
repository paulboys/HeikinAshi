"""Unit tests for screener module."""

from unittest.mock import patch

import pandas as pd
import pytest

from stockcharts.screener.screener import (
    ScreenResult,
    get_candle_color,
    screen_nasdaq,
    screen_ticker,
)


def test_get_candle_color_green():
    """Test get_candle_color returns green for bullish candle."""
    df = pd.DataFrame(
        {
            "HA_Open": [100.0],
            "HA_Close": [105.0],
        }
    )
    assert get_candle_color(df) == "green"


def test_get_candle_color_red():
    """Test get_candle_color returns red for bearish candle."""
    df = pd.DataFrame(
        {
            "HA_Open": [105.0],
            "HA_Close": [100.0],
        }
    )
    assert get_candle_color(df) == "red"


def test_get_candle_color_previous():
    """Test get_candle_color can check previous candle."""
    df = pd.DataFrame(
        {
            "HA_Open": [100.0, 105.0],
            "HA_Close": [105.0, 103.0],
        }
    )
    assert get_candle_color(df, index=-2) == "green"
    assert get_candle_color(df, index=-1) == "red"


@patch("stockcharts.screener.screener.fetch_ohlc")
def test_screen_ticker_fetch_error(mock_fetch):
    """Test screen_ticker handles fetch errors gracefully."""
    mock_fetch.side_effect = Exception("Network error")

    result = screen_ticker("AAPL", debug=True)

    assert result is None


@patch("stockcharts.screener.screener.fetch_ohlc")
def test_screen_ticker_empty_df(mock_fetch):
    """Test screen_ticker handles empty DataFrame."""
    mock_fetch.return_value = pd.DataFrame()

    result = screen_ticker("AAPL")

    assert result is None


@patch("stockcharts.screener.screener.get_nasdaq_tickers")
@patch("stockcharts.screener.screener.screen_ticker")
def test_screen_nasdaq_ticker_filter(mock_screen_ticker, mock_get_tickers):
    """Test screen_nasdaq with ticker_filter."""
    # Create a proper ScreenResult
    result = ScreenResult(
        ticker="AAPL",
        color="green",
        previous_color="red",
        color_changed=True,
        ha_open=150.0,
        ha_close=155.0,
        last_date="2024-01-15",
        interval="1d",
        avg_volume=50000000.0,
    )
    mock_screen_ticker.return_value = result

    results = screen_nasdaq(ticker_filter=["AAPL"], delay=0, verbose=False)

    # Should not have called get_nasdaq_tickers
    mock_get_tickers.assert_not_called()
    assert len(results) > 0


@patch("stockcharts.screener.screener.get_nasdaq_tickers")
@patch("stockcharts.screener.screener.screen_ticker")
def test_screen_nasdaq_handles_errors(mock_screen_ticker, mock_get_tickers):
    """Test screen_nasdaq continues after individual ticker errors."""
    mock_get_tickers.return_value = ["AAPL", "INVALID", "MSFT"]

    result1 = ScreenResult(
        ticker="AAPL",
        color="green",
        previous_color="red",
        color_changed=True,
        ha_open=150.0,
        ha_close=155.0,
        last_date="2024-01-15",
        interval="1d",
        avg_volume=50000000.0,
    )

    result2 = ScreenResult(
        ticker="MSFT",
        color="red",
        previous_color="green",
        color_changed=True,
        ha_open=300.0,
        ha_close=295.0,
        last_date="2024-01-15",
        interval="1d",
        avg_volume=40000000.0,
    )

    mock_screen_ticker.side_effect = [result1, None, result2]

    results = screen_nasdaq(delay=0, limit=3, verbose=False)

    # Should have 2 successful results, skipping the None
    assert len(results) == 2
