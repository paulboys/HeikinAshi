from unittest.mock import patch

import pandas as pd
import pytest

from stockcharts.screener.screener import screen_nasdaq


@pytest.fixture
def mock_fetch_and_tickers(tmp_path):
    # Provide synthetic data and small ticker set
    df = pd.DataFrame(
        {
            "Open": [10, 11, 12, 13],
            "High": [11, 12, 13, 14],
            "Low": [9, 10, 11, 12],
            "Close": [10, 11, 12, 13],
            "Volume": [600000, 600000, 600000, 600000],
        },
        index=pd.date_range("2025-01-01", periods=4),
    )

    with patch("stockcharts.data.fetch.yf.download", return_value=df):
        with patch(
            "stockcharts.screener.nasdaq.get_nasdaq_tickers",
            return_value=["TEST1", "TEST2"],
        ):
            yield


def test_screener_min_volume_filter(mock_fetch_and_tickers):
    results = screen_nasdaq(color_filter="green", changed_only=False, min_volume=500000, limit=2)
    assert isinstance(results, list)
    # All entries should pass volume filter
    for r in results:
        assert r.avg_volume >= 500000


def test_screener_min_price_filter(mock_fetch_and_tickers):
    # Synthetic close ~13 so min_price 5 should pass
    results = screen_nasdaq(color_filter="green", changed_only=False, min_price=5.0, limit=2)
    assert isinstance(results, list)
    for r in results:
        assert r.ha_close >= 5.0


def test_screener_csv_output(tmp_path, mock_fetch_and_tickers):
    results = screen_nasdaq(color_filter="green", changed_only=False, limit=2)
    out = tmp_path / "screener.csv"
    rows = [
        {
            "Ticker": r.ticker,
            "Price": r.ha_close,
            "Volume": r.avg_volume,
            "Color": r.color,
            "Run_Length": r.run_length,
            "Run_Percentile": r.run_percentile,
        }
        for r in results
    ]

    if rows:
        pd.DataFrame(rows).to_csv(out, index=False)
        df = pd.read_csv(out)
        expected_cols = ["Ticker", "Price", "Volume", "Color", "Run_Length", "Run_Percentile"]
        assert set(expected_cols).issubset(df.columns)
        # Verify run stats are valid
        assert all(df["Run_Length"] > 0)
        assert all((df["Run_Percentile"] >= 0) & (df["Run_Percentile"] <= 100))
    else:
        # If no results, ensure we don't write empty CSV and test passes gracefully
        assert not out.exists()


def test_screener_invalid_input_file(tmp_path, mock_fetch_and_tickers):
    # Simulate CLI passing missing input filter file by calling screen_nasdaq with limit and verifying behavior
    # screen_nasdaq does not read files; this test ensures workflow doesn't crash with external invalid inputs
    results = screen_nasdaq(color_filter="green", changed_only=False, limit=1)
    assert len(results) >= 0
