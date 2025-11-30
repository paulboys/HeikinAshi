"""Unit tests for CLI main_plot function."""

import os
from io import StringIO
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stockcharts.cli import main_plot


@pytest.fixture
def sample_input_csv(tmp_path):
    """Create sample screener CSV with Ticker column."""
    csv_path = tmp_path / "screen_results.csv"
    csv_path.write_text("Ticker,color,ha_close\nAAPL,green,155.0\nMSFT,green,375.0\n")
    return csv_path


@pytest.fixture
def sample_input_csv_lowercase(tmp_path):
    """Create sample screener CSV with lowercase ticker column."""
    csv_path = tmp_path / "screen_results_lower.csv"
    csv_path.write_text("ticker,color,ha_close\nAAPL,green,155.0\nMSFT,green,375.0\n")
    return csv_path


@pytest.fixture
def mock_ohlc_data():
    """Mock OHLC DataFrame."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    return pd.DataFrame(
        {
            "Open": [100 + i for i in range(30)],
            "High": [105 + i for i in range(30)],
            "Low": [95 + i for i in range(30)],
            "Close": [102 + i for i in range(30)],
            "Volume": [1000000] * 30,
        },
        index=dates,
    )


@pytest.fixture
def mock_ha_data():
    """Mock Heiken Ashi DataFrame."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    return pd.DataFrame(
        {
            "HA_Open": [100 + i for i in range(30)],
            "HA_High": [105 + i for i in range(30)],
            "HA_Low": [95 + i for i in range(30)],
            "HA_Close": [102 + i for i in range(30)],
        },
        index=dates,
    )


def test_main_plot_version_flag():
    """Test --version flag prints version and exits."""
    with patch("sys.argv", ["stockcharts-plot", "--version"]):
        with patch("stockcharts.__version__", "1.2.3"):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_plot()

    assert result == 0
    assert "stockcharts 1.2.3" in mock_stdout.getvalue()


def test_main_plot_missing_input_file():
    """Test error handling when input CSV doesn't exist."""
    with patch("sys.argv", ["stockcharts-plot", "--input", "nonexistent.csv"]):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main_plot()

    assert result == 1
    output_text = mock_stdout.getvalue()
    assert "Error: Input file not found" in output_text


def test_main_plot_missing_ticker_column(tmp_path):
    """Test error handling when CSV lacks Ticker/ticker column."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("Symbol,color\nAAPL,green\n")

    with patch("sys.argv", ["stockcharts-plot", "--input", str(bad_csv)]):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main_plot()

    assert result == 1
    output_text = mock_stdout.getvalue()
    assert "must have a 'Ticker' or 'ticker' column" in output_text
    assert "Available columns:" in output_text


def test_main_plot_successful_with_uppercase_ticker(
    sample_input_csv, mock_ohlc_data, mock_ha_data, tmp_path
):
    """Test successful plotting with uppercase Ticker column."""
    output_dir = tmp_path / "charts"

    with patch("sys.argv", ["stockcharts-plot", "--input", str(sample_input_csv), "--output-dir", str(output_dir)]):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data) as mock_fetch:
            with patch("stockcharts.cli.heiken_ashi", return_value=mock_ha_data):
                with patch("matplotlib.pyplot.savefig") as mock_savefig:
                    with patch("matplotlib.pyplot.close"):
                        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                            result = main_plot()

    assert result == 0
    assert output_dir.exists()

    # Verify fetch_ohlc was called for both tickers
    assert mock_fetch.call_count == 2

    # Verify savefig was called for both tickers
    assert mock_savefig.call_count == 2

    output_text = mock_stdout.getvalue()
    assert "Generating Heiken Ashi charts for 2 stocks" in output_text
    assert "AAPL" in output_text
    assert "MSFT" in output_text


def test_main_plot_successful_with_lowercase_ticker(
    sample_input_csv_lowercase, mock_ohlc_data, mock_ha_data, tmp_path
):
    """Test successful plotting with lowercase ticker column."""
    output_dir = tmp_path / "charts"

    with patch(
        "sys.argv",
        ["stockcharts-plot", "--input", str(sample_input_csv_lowercase), "--output-dir", str(output_dir)],
    ):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data):
            with patch("stockcharts.cli.heiken_ashi", return_value=mock_ha_data):
                with patch("matplotlib.pyplot.savefig") as mock_savefig:
                    with patch("matplotlib.pyplot.close"):
                        result = main_plot()

    assert result == 0
    assert mock_savefig.call_count == 2


def test_main_plot_empty_data_skipped(sample_input_csv, tmp_path):
    """Test that tickers with no data are skipped gracefully."""
    output_dir = tmp_path / "charts"

    with patch("sys.argv", ["stockcharts-plot", "--input", str(sample_input_csv), "--output-dir", str(output_dir)]):
        with patch("stockcharts.cli.fetch_ohlc", return_value=None):  # Simulate no data
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_plot()

    assert result == 0
    output_text = mock_stdout.getvalue()
    assert "❌ No data" in output_text


def test_main_plot_fetch_exception_handled(sample_input_csv, tmp_path):
    """Test that fetch exceptions are caught and displayed."""
    output_dir = tmp_path / "charts"

    with patch("sys.argv", ["stockcharts-plot", "--input", str(sample_input_csv), "--output-dir", str(output_dir)]):
        with patch("stockcharts.cli.fetch_ohlc", side_effect=Exception("Network error")):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_plot()

    assert result == 0  # Still returns success, but errors are reported per ticker
    output_text = mock_stdout.getvalue()
    assert "❌ Error" in output_text


def test_main_plot_custom_period_and_lookback(sample_input_csv, mock_ohlc_data, mock_ha_data, tmp_path):
    """Test plotting with custom period and lookback."""
    output_dir = tmp_path / "charts"

    with patch(
        "sys.argv",
        [
            "stockcharts-plot",
            "--input",
            str(sample_input_csv),
            "--output-dir",
            str(output_dir),
            "--period",
            "1h",
            "--lookback",
            "5d",
        ],
    ):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data) as mock_fetch:
            with patch("stockcharts.cli.heiken_ashi", return_value=mock_ha_data):
                with patch("matplotlib.pyplot.savefig"):
                    with patch("matplotlib.pyplot.close"):
                        result = main_plot()

    assert result == 0

    # Verify fetch_ohlc was called with correct parameters
    call_kwargs = mock_fetch.call_args[1]
    assert call_kwargs["interval"] == "1h"
    assert call_kwargs["lookback"] == "5d"


def test_main_plot_no_disclaimer_flag(sample_input_csv, mock_ohlc_data, mock_ha_data, tmp_path):
    """Test --no-disclaimer flag suppresses disclaimer."""
    output_dir = tmp_path / "charts"

    with patch(
        "sys.argv",
        ["stockcharts-plot", "--input", str(sample_input_csv), "--output-dir", str(output_dir), "--no-disclaimer"],
    ):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data):
            with patch("stockcharts.cli.heiken_ashi", return_value=mock_ha_data):
                with patch("matplotlib.pyplot.savefig"):
                    with patch("matplotlib.pyplot.close"):
                        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                            result = main_plot()

    output_text = mock_stdout.getvalue()
    assert "[Disclaimer]" not in output_text


def test_main_plot_creates_output_directory(sample_input_csv, mock_ohlc_data, mock_ha_data, tmp_path):
    """Test that output directory is created if it doesn't exist."""
    output_dir = tmp_path / "new_charts_dir"
    assert not output_dir.exists()

    with patch("sys.argv", ["stockcharts-plot", "--input", str(sample_input_csv), "--output-dir", str(output_dir)]):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data):
            with patch("stockcharts.cli.heiken_ashi", return_value=mock_ha_data):
                with patch("matplotlib.pyplot.savefig"):
                    with patch("matplotlib.pyplot.close"):
                        result = main_plot()

    assert result == 0
    assert output_dir.exists()
