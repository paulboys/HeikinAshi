from unittest.mock import patch

import pandas as pd
import pytest

from stockcharts.data.fetch import fetch_ohlc


def test_fetch_ohlc_handles_network_error():
    with patch("yfinance.download", side_effect=Exception("Network error")):
        with pytest.raises(Exception):
            fetch_ohlc("AAPL", lookback="1mo", interval="1d")
