from unittest.mock import patch

import pytest

from stockcharts.data.fetch import (
    _validate_and_build_download_kwargs,
    fetch_ohlc,
)


def test_fetch_ohlc_handles_network_error():
    with patch("yfinance.download", side_effect=Exception("Network error")):
        with pytest.raises(Exception):
            fetch_ohlc("AAPL", lookback="1mo", interval="1d")


def test_extended_lookback_converts_to_max():
    """Test that extended lookback periods (20y, 30y, etc.) are converted to 'max'."""
    for extended_period in ["20y", "30y", "40y", "50y", "100y"]:
        kwargs = _validate_and_build_download_kwargs(
            interval="1d",
            lookback=extended_period,
            start=None,
            end=None,
            auto_adjust=False,
        )
        assert kwargs["period"] == "max", f"{extended_period} should be converted to 'max'"


def test_standard_lookback_unchanged():
    """Test that standard lookback periods are not modified."""
    for period in ["1y", "2y", "5y", "10y", "max"]:
        kwargs = _validate_and_build_download_kwargs(
            interval="1d",
            lookback=period,
            start=None,
            end=None,
            auto_adjust=False,
        )
        assert kwargs["period"] == period, f"{period} should remain unchanged"


def test_invalid_lookback_raises_error():
    """Test that invalid lookback periods raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported lookback"):
        _validate_and_build_download_kwargs(
            interval="1d",
            lookback="15y",  # Not in valid or extended set
            start=None,
            end=None,
            auto_adjust=False,
        )
