"""Unit tests for CLI main_screen function."""

import os
from io import StringIO
from unittest.mock import patch

import pandas as pd
import pytest

from stockcharts.cli import main_screen
from stockcharts.screener.screener import ScreenResult


@pytest.fixture
def mock_screen_results():
    """Sample screening results."""
    return [
        ScreenResult(
            ticker="AAPL",
            color="green",
            previous_color="red",
            color_changed=True,
            ha_open=150.0,
            ha_close=155.0,
            last_date="2024-01-15",
            interval="1d",
            avg_volume=50000000,
            run_length=5,
            run_percentile=85.0,
        ),
        ScreenResult(
            ticker="MSFT",
            color="green",
            previous_color="green",
            color_changed=False,
            ha_open=370.0,
            ha_close=375.0,
            last_date="2024-01-15",
            interval="1d",
            avg_volume=25000000,
            run_length=12,
            run_percentile=95.0,
        ),
    ]


@pytest.fixture
def mock_empty_results():
    """Empty screening results."""
    return []


def test_main_screen_version_flag():
    """Test --version flag prints version and exits."""
    with patch("sys.argv", ["stockcharts-screen", "--version"]):
        with patch("stockcharts.__version__", "1.2.3"):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_screen()

    assert result == 0
    assert "stockcharts 1.2.3" in mock_stdout.getvalue()


def test_main_screen_successful_run(mock_screen_results, tmp_path):
    """Test successful screening with results saved to CSV."""
    output_file = tmp_path / "test_output.csv"

    with patch(
        "sys.argv",
        ["stockcharts-screen", "--color", "green", "--output", str(output_file)],
    ):
        with patch("stockcharts.cli.screen_nasdaq", return_value=mock_screen_results):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_screen()

    assert result == 0
    assert output_file.exists()

    # Verify CSV structure
    df = pd.read_csv(output_file)
    assert len(df) == 2
    assert "ticker" in df.columns
    assert "color" in df.columns
    assert "color_changed" in df.columns
    assert df["ticker"].tolist() == ["AAPL", "MSFT"]

    output_text = mock_stdout.getvalue()
    assert "Found 2 stocks matching criteria" in output_text


def test_main_screen_no_results(mock_empty_results, tmp_path):
    """Test screening with no matching results."""
    output_file = tmp_path / "empty_output.csv"

    with patch(
        "sys.argv",
        ["stockcharts-screen", "--color", "red", "--output", str(output_file)],
    ):
        with patch("stockcharts.cli.screen_nasdaq", return_value=mock_empty_results):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_screen()

    assert result == 0
    assert not output_file.exists()  # No CSV created for empty results

    output_text = mock_stdout.getvalue()
    assert "No stocks found matching criteria" in output_text


def test_main_screen_input_filter_missing():
    """Test error handling when input filter file doesn't exist."""
    with patch("sys.argv", ["stockcharts-screen", "--input-filter", "nonexistent.csv"]):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main_screen()

    assert result == 1
    output_text = mock_stdout.getvalue()
    assert "Error: Input filter file not found" in output_text


def test_main_screen_input_filter_malformed(tmp_path):
    """Test error handling when input filter lacks 'Ticker' column."""
    filter_file = tmp_path / "bad_filter.csv"
    filter_file.write_text("Symbol,Name\nAAPL,Apple\nMSFT,Microsoft\n")

    with patch("sys.argv", ["stockcharts-screen", "--input-filter", str(filter_file)]):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main_screen()

    assert result == 1
    output_text = mock_stdout.getvalue()
    assert "must have a 'Ticker' column" in output_text


def test_main_screen_input_filter_success(mock_screen_results, tmp_path):
    """Test successful screening with input filter CSV."""
    filter_file = tmp_path / "filter.csv"
    filter_file.write_text("Ticker,Company\nAAPL,Apple Inc.\nMSFT,Microsoft Corp.\n")

    output_file = tmp_path / "filtered_output.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-screen",
            "--input-filter",
            str(filter_file),
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_nasdaq", return_value=mock_screen_results
        ) as mock_screen:
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_screen()

    assert result == 0
    output_text = mock_stdout.getvalue()
    assert "Loaded 2 tickers from" in output_text

    # Verify ticker_filter was passed
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["ticker_filter"] == ["AAPL", "MSFT"]


def test_main_screen_with_filters(mock_screen_results, tmp_path):
    """Test screening with volume and price filters."""
    output_file = tmp_path / "filtered.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-screen",
            "--color",
            "green",
            "--min-volume",
            "1000000",
            "--min-price",
            "10.0",
            "--changed-only",
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_nasdaq", return_value=mock_screen_results
        ) as mock_screen:
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_screen()

    assert result == 0

    # Verify filter parameters were passed correctly
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["color_filter"] == "green"
    assert call_kwargs["min_volume"] == 1000000
    assert call_kwargs["min_price"] == 10.0
    assert call_kwargs["changed_only"] is True

    output_text = mock_stdout.getvalue()
    assert "Minimum volume: 1,000,000 shares/day" in output_text
    assert "Minimum price: $10.00" in output_text
    assert "Filtering for color changes only" in output_text


def test_main_screen_no_disclaimer_flag():
    """Test --no-disclaimer flag suppresses disclaimer."""
    with patch("sys.argv", ["stockcharts-screen", "--no-disclaimer", "--version"]):
        with patch("stockcharts.__version__", "1.0.0"):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_screen()

    output_text = mock_stdout.getvalue()
    assert "[Disclaimer]" not in output_text


def test_main_screen_disclaimer_env_var():
    """Test STOCKCHARTS_NO_DISCLAIMER env var suppresses disclaimer."""
    with patch("sys.argv", ["stockcharts-screen", "--version"]):
        with patch("stockcharts.__version__", "1.0.0"):
            with patch.dict(os.environ, {"STOCKCHARTS_NO_DISCLAIMER": "1"}):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    result = main_screen()

    output_text = mock_stdout.getvalue()
    assert "[Disclaimer]" not in output_text


def test_main_screen_with_limit(mock_screen_results, tmp_path):
    """Test screening with ticker limit."""
    output_file = tmp_path / "limited.csv"

    with patch(
        "sys.argv",
        ["stockcharts-screen", "--limit", "100", "--output", str(output_file)],
    ):
        with patch(
            "stockcharts.cli.screen_nasdaq", return_value=mock_screen_results
        ) as mock_screen:
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_screen()

    assert result == 0

    # Verify limit was passed
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["limit"] == 100

    output_text = mock_stdout.getvalue()
    assert "Limiting to first 100 tickers" in output_text


def test_main_screen_custom_period_and_lookback(mock_screen_results, tmp_path):
    """Test screening with custom period and lookback parameters."""
    output_file = tmp_path / "custom.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-screen",
            "--period",
            "1h",
            "--lookback",
            "1mo",
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_nasdaq", return_value=mock_screen_results
        ) as mock_screen:
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_screen()

    assert result == 0

    # Verify parameters were passed
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["period"] == "1h"
    assert call_kwargs["lookback"] == "1mo"

    output_text = mock_stdout.getvalue()
    assert "Period: 1h, Lookback: 1mo" in output_text


def test_main_screen_custom_date_range(mock_screen_results, tmp_path):
    """Test screening with custom start/end dates."""
    output_file = tmp_path / "custom_dates.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-screen",
            "--start",
            "2024-01-01",
            "--end",
            "2024-12-31",
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_nasdaq", return_value=mock_screen_results
        ) as mock_screen:
            result = main_screen()

    assert result == 0

    # Verify date parameters were passed
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["start"] == "2024-01-01"
    assert call_kwargs["end"] == "2024-12-31"


def test_main_screen_debug_flag(mock_screen_results, tmp_path):
    """Test --debug flag enables detailed error messages."""
    output_file = tmp_path / "debug.csv"

    with patch("sys.argv", ["stockcharts-screen", "--debug", "--output", str(output_file)]):
        with patch(
            "stockcharts.cli.screen_nasdaq", return_value=mock_screen_results
        ) as mock_screen:
            result = main_screen()

    assert result == 0

    # Verify debug flag was passed
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["debug"] is True
