"""Unit tests for CLI main_plot_divergence function."""

import os
from io import StringIO
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stockcharts.cli import main_plot_divergence


@pytest.fixture
def sample_rsi_csv(tmp_path):
    """Create sample RSI divergence CSV."""
    csv_path = tmp_path / "rsi_results.csv"
    csv_path.write_text(
        'Ticker,Company,Divergence Type,Bullish_Indices,Bearish_Indices\n'
        'AAPL,Apple Inc.,bullish,"[\\"2024-01-10\\",\\"2024-01-20\\",\\"2024-01-11\\",\\"2024-01-21\\"]",\n'
        'MSFT,Microsoft Corp.,bearish,,"[\\"2024-01-15\\",\\"2024-01-25\\",\\"2024-01-16\\",\\"2024-01-26\\"]"\n'
    )
    return csv_path


@pytest.fixture
def sample_rsi_csv_lowercase(tmp_path):
    """Create sample RSI CSV with lowercase ticker column."""
    csv_path = tmp_path / "rsi_results_lower.csv"
    csv_path.write_text('ticker,company,divergence_type\nAAPL,Apple,bullish\nMSFT,Microsoft,bearish\n')
    return csv_path


@pytest.fixture
def mock_ohlc_data():
    """Mock OHLC DataFrame."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    return pd.DataFrame(
        {
            "Open": [100 + i for i in range(50)],
            "High": [105 + i for i in range(50)],
            "Low": [95 + i for i in range(50)],
            "Close": [102 + i for i in range(50)],
        },
        index=dates,
    )


def test_main_plot_divergence_version_flag():
    """Test --version flag prints version and exits."""
    with patch("sys.argv", ["stockcharts-plot-divergence", "--version"]):
        with patch("stockcharts.__version__", "1.2.3"):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_plot_divergence()

    assert result == 0
    assert "stockcharts 1.2.3" in mock_stdout.getvalue()


def test_main_plot_divergence_missing_input_file():
    """Test error handling when input CSV doesn't exist."""
    with patch("sys.argv", ["stockcharts-plot-divergence", "--input", "nonexistent.csv"]):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main_plot_divergence()

    assert result == 1
    output_text = mock_stdout.getvalue()
    assert "Error: Input file not found" in output_text


def test_main_plot_divergence_missing_ticker_column(tmp_path):
    """Test error handling when CSV lacks Ticker/ticker column."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("Symbol,Company\nAAPL,Apple\n")

    with patch("sys.argv", ["stockcharts-plot-divergence", "--input", str(bad_csv)]):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main_plot_divergence()

    assert result == 1
    output_text = mock_stdout.getvalue()
    assert "must have a 'Ticker' or 'ticker' column" in output_text


def test_main_plot_divergence_successful_with_uppercase_ticker(sample_rsi_csv, mock_ohlc_data, tmp_path):
    """Test successful plotting with uppercase Ticker column."""
    output_dir = tmp_path / "div_charts"

    with patch("sys.argv", ["stockcharts-plot-divergence", "--input", str(sample_rsi_csv), "--output-dir", str(output_dir)]):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data):
            with patch("stockcharts.charts.divergence.plot_price_rsi") as mock_plot:
                mock_fig = MagicMock()
                mock_plot.return_value = mock_fig

                with patch("stockcharts.cli.plt.close"):
                    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                        result = main_plot_divergence()

    assert result == 0
    assert output_dir.exists()

    # Verify plot_price_rsi was called for both tickers
    assert mock_plot.call_count == 2

    # Verify savefig was called
    assert mock_fig.savefig.call_count == 2

    output_text = mock_stdout.getvalue()
    assert "Generating Price/RSI divergence charts for 2 stocks" in output_text


def test_main_plot_divergence_successful_with_lowercase_ticker(
    sample_rsi_csv_lowercase, mock_ohlc_data, tmp_path
):
    """Test successful plotting with lowercase ticker column."""
    output_dir = tmp_path / "div_charts"

    with patch(
        "sys.argv",
        ["stockcharts-plot-divergence", "--input", str(sample_rsi_csv_lowercase), "--output-dir", str(output_dir)],
    ):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data):
            with patch("stockcharts.charts.divergence.plot_price_rsi") as mock_plot:
                mock_fig = MagicMock()
                mock_plot.return_value = mock_fig

                with patch("stockcharts.cli.plt.close"):
                    result = main_plot_divergence()

    assert result == 0
    assert mock_plot.call_count == 2


def test_main_plot_divergence_with_precomputed_indices(sample_rsi_csv, mock_ohlc_data, tmp_path):
    """Test that precomputed divergence indices are parsed and passed."""
    output_dir = tmp_path / "div_charts"

    with patch("sys.argv", ["stockcharts-plot-divergence", "--input", str(sample_rsi_csv), "--output-dir", str(output_dir)]):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data):
            with patch("stockcharts.charts.divergence.plot_price_rsi") as mock_plot:
                mock_fig = MagicMock()
                mock_plot.return_value = mock_fig

                with patch("stockcharts.cli.plt.close"):
                    result = main_plot_divergence()

    assert result == 0

    # Check that precomputed_divergence was passed (at least for first call)
    first_call_kwargs = mock_plot.call_args_list[0][1]
    assert "precomputed_divergence" in first_call_kwargs


def test_main_plot_divergence_custom_parameters(sample_rsi_csv, mock_ohlc_data, tmp_path):
    """Test plotting with custom RSI period, interval, and lookback."""
    output_dir = tmp_path / "custom_charts"

    with patch(
        "sys.argv",
        [
            "stockcharts-plot-divergence",
            "--input",
            str(sample_rsi_csv),
            "--output-dir",
            str(output_dir),
            "--interval",
            "1h",
            "--lookback",
            "1mo",
            "--rsi-period",
            "21",
            "--swing-window",
            "7",
        ],
    ):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data) as mock_fetch:
            with patch("stockcharts.charts.divergence.plot_price_rsi") as mock_plot:
                mock_fig = MagicMock()
                mock_plot.return_value = mock_fig

                with patch("stockcharts.cli.plt.close"):
                    result = main_plot_divergence()

    assert result == 0

    # Verify fetch parameters
    call_kwargs = mock_fetch.call_args[1]
    assert call_kwargs["interval"] == "1h"
    assert call_kwargs["lookback"] == "1mo"

    # Verify plot parameters
    plot_kwargs = mock_plot.call_args[1]
    assert plot_kwargs["rsi_period"] == 21
    assert plot_kwargs["divergence_window"] == 7


def test_main_plot_divergence_max_plots_limit(sample_rsi_csv, mock_ohlc_data, tmp_path):
    """Test --max-plots limits the number of charts generated."""
    output_dir = tmp_path / "limited_charts"

    with patch(
        "sys.argv",
        [
            "stockcharts-plot-divergence",
            "--input",
            str(sample_rsi_csv),
            "--output-dir",
            str(output_dir),
            "--max-plots",
            "1",
        ],
    ):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data):
            with patch("stockcharts.charts.divergence.plot_price_rsi") as mock_plot:
                mock_fig = MagicMock()
                mock_plot.return_value = mock_fig

                with patch("stockcharts.cli.plt.close"):
                    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                        result = main_plot_divergence()

    assert result == 0

    # Only 1 plot should be generated (limited by --max-plots)
    assert mock_plot.call_count == 1

    output_text = mock_stdout.getvalue()
    assert "Generating Price/RSI divergence charts for 1 stocks" in output_text


def test_main_plot_divergence_handles_exceptions(sample_rsi_csv, tmp_path):
    """Test that plotting exceptions are caught and reported per ticker."""
    output_dir = tmp_path / "error_charts"

    with patch("sys.argv", ["stockcharts-plot-divergence", "--input", str(sample_rsi_csv), "--output-dir", str(output_dir)]):
        with patch("stockcharts.cli.fetch_ohlc", side_effect=Exception("Network error")):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_plot_divergence()

    assert result == 0  # Returns success but errors are reported

    output_text = mock_stdout.getvalue()
    assert "❌ Error" in output_text


def test_main_plot_divergence_creates_output_directory(sample_rsi_csv, mock_ohlc_data, tmp_path):
    """Test that output directory is created if it doesn't exist."""
    output_dir = tmp_path / "new_divergence_dir"
    assert not output_dir.exists()

    with patch("sys.argv", ["stockcharts-plot-divergence", "--input", str(sample_rsi_csv), "--output-dir", str(output_dir)]):
        with patch("stockcharts.cli.fetch_ohlc", return_value=mock_ohlc_data):
            with patch("stockcharts.charts.divergence.plot_price_rsi") as mock_plot:
                mock_fig = MagicMock()
                mock_plot.return_value = mock_fig

                with patch("stockcharts.cli.plt.close"):
                    result = main_plot_divergence()

    assert result == 0
    assert output_dir.exists()
