"""Unit tests for CLI main_rsi_divergence function."""

from io import StringIO
from unittest.mock import patch

import pandas as pd
import pytest

from stockcharts.cli import main_rsi_divergence
from stockcharts.screener.rsi_divergence import RSIDivergenceResult


@pytest.fixture
def mock_rsi_results():
    """Sample RSI divergence results."""
    return [
        RSIDivergenceResult(
            ticker="AAPL",
            company_name="Apple Inc.",
            close_price=150.0,
            rsi=45.0,
            divergence_type="bullish",
            bullish_divergence=True,
            bearish_divergence=False,
            details="2-point bullish divergence detected",
            bullish_indices=(
                pd.Timestamp("2024-01-10"),
                pd.Timestamp("2024-01-20"),
                pd.Timestamp("2024-01-11"),
                pd.Timestamp("2024-01-21"),
            ),
            bearish_indices=None,
        )
    ]


def test_main_rsi_divergence_version_flag():
    """Test --version flag prints version and exits."""
    with patch("sys.argv", ["stockcharts-rsi-divergence", "--version"]):
        with patch("stockcharts.__version__", "1.2.3"):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_rsi_divergence()

    assert result == 0
    assert "stockcharts 1.2.3" in mock_stdout.getvalue()


def test_main_rsi_divergence_successful_run(mock_rsi_results, tmp_path):
    """Test successful screening with results saved."""
    output_file = tmp_path / "rsi_output.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-rsi-divergence",
            "--type",
            "bullish",
            "--output",
            str(output_file),
        ],
    ):
        with patch("stockcharts.cli.screen_rsi_divergence", return_value=mock_rsi_results):
            with patch("stockcharts.cli.save_results_to_csv") as mock_save:
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    result = main_rsi_divergence()

    assert result == 0
    mock_save.assert_called_once()

    output_text = mock_stdout.getvalue()
    assert "Found 1 stocks with divergences" in output_text
    assert "AAPL" in output_text


def test_main_rsi_divergence_no_results(tmp_path):
    """Test screening with no divergences found."""
    output_file = tmp_path / "empty_rsi.csv"

    with patch("sys.argv", ["stockcharts-rsi-divergence", "--output", str(output_file)]):
        with patch("stockcharts.cli.screen_rsi_divergence", return_value=[]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = main_rsi_divergence()

    assert result == 0

    output_text = mock_stdout.getvalue()
    assert "No divergences found" in output_text


def test_main_rsi_divergence_custom_parameters(mock_rsi_results, tmp_path):
    """Test screening with custom RSI period, swing window, and lookback."""
    output_file = tmp_path / "custom_rsi.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-rsi-divergence",
            "--rsi-period",
            "21",
            "--swing-window",
            "7",
            "--lookback",
            "90",
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_rsi_divergence", return_value=mock_rsi_results
        ) as mock_screen:
            with patch("stockcharts.cli.save_results_to_csv"):
                result = main_rsi_divergence()

    assert result == 0

    # Verify parameters were passed correctly
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["rsi_period"] == 21
    assert call_kwargs["swing_window"] == 7
    assert call_kwargs["lookback"] == 90


def test_main_rsi_divergence_with_filters(mock_rsi_results, tmp_path):
    """Test screening with price and volume filters."""
    output_file = tmp_path / "filtered_rsi.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-rsi-divergence",
            "--min-price",
            "10.0",
            "--max-price",
            "200.0",
            "--min-volume",
            "1000000",
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_rsi_divergence", return_value=mock_rsi_results
        ) as mock_screen:
            with patch("stockcharts.cli.save_results_to_csv"):
                result = main_rsi_divergence()

    assert result == 0

    # Verify filters were passed
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["min_price"] == 10.0
    assert call_kwargs["max_price"] == 200.0
    assert call_kwargs["min_volume"] == 1000000


def test_main_rsi_divergence_3point_with_scoring(mock_rsi_results, tmp_path):
    """Test 3-point divergence with sequence scoring."""
    output_file = tmp_path / "3point_rsi.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-rsi-divergence",
            "--min-swing-points",
            "3",
            "--use-sequence-scoring",
            "--min-sequence-score",
            "2.0",
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_rsi_divergence", return_value=mock_rsi_results
        ) as mock_screen:
            with patch("stockcharts.cli.save_results_to_csv"):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    result = main_rsi_divergence()

    assert result == 0

    # Verify 3-point parameters
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["min_swing_points"] == 3
    assert call_kwargs["use_sequence_scoring"] is True
    assert call_kwargs["min_sequence_score"] == 2.0

    output_text = mock_stdout.getvalue()
    assert "3-point divergence required" in output_text
    assert "Sequence scoring: ENABLED" in output_text


def test_main_rsi_divergence_ema_deriv_pivot_method(mock_rsi_results, tmp_path):
    """Test screening with ema-deriv pivot method."""
    output_file = tmp_path / "ema_rsi.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-rsi-divergence",
            "--pivot-method",
            "ema-deriv",
            "--ema-price-span",
            "7",
            "--ema-rsi-span",
            "7",
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_rsi_divergence", return_value=mock_rsi_results
        ) as mock_screen:
            with patch("stockcharts.cli.save_results_to_csv"):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    result = main_rsi_divergence()

    assert result == 0

    # Verify pivot method parameters
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["pivot_method"] == "ema-deriv"
    assert call_kwargs["ema_price_span"] == 7
    assert call_kwargs["ema_rsi_span"] == 7

    output_text = mock_stdout.getvalue()
    assert "ema-deriv" in output_text


def test_main_rsi_divergence_exclude_breakouts(mock_rsi_results, tmp_path):
    """Test screening with breakout exclusion flags."""
    output_file = tmp_path / "no_breakouts.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-rsi-divergence",
            "--exclude-breakouts",
            "--breakout-threshold",
            "0.07",
            "--exclude-failed-breakouts",
            "--failed-lookback",
            "15",
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_rsi_divergence", return_value=mock_rsi_results
        ) as mock_screen:
            with patch("stockcharts.cli.save_results_to_csv"):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    result = main_rsi_divergence()

    assert result == 0

    # Verify breakout parameters
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["exclude_breakouts"] is True
    assert call_kwargs["breakout_threshold"] == 0.07
    assert call_kwargs["exclude_failed_breakouts"] is True
    assert call_kwargs["failed_lookback_window"] == 15

    output_text = mock_stdout.getvalue()
    assert "Excluding completed breakouts" in output_text
    assert "Excluding failed breakouts" in output_text


def test_main_rsi_divergence_custom_date_range(mock_rsi_results, tmp_path):
    """Test screening with custom start and end dates."""
    output_file = tmp_path / "custom_dates_rsi.csv"

    with patch(
        "sys.argv",
        [
            "stockcharts-rsi-divergence",
            "--start",
            "2024-01-01",
            "--end",
            "2024-12-31",
            "--output",
            str(output_file),
        ],
    ):
        with patch(
            "stockcharts.cli.screen_rsi_divergence", return_value=mock_rsi_results
        ) as mock_screen:
            with patch("stockcharts.cli.save_results_to_csv"):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    result = main_rsi_divergence()

    assert result == 0

    # Verify date parameters
    call_kwargs = mock_screen.call_args[1]
    assert call_kwargs["start"] == "2024-01-01"
    assert call_kwargs["end"] == "2024-12-31"

    output_text = mock_stdout.getvalue()
    assert "Date range override" in output_text
