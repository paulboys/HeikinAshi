"""Unit tests for RSI divergence screener filtering logic."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stockcharts.screener.rsi_divergence import (RSIDivergenceResult,
                                                 save_results_to_csv,
                                                 screen_rsi_divergence)


@pytest.fixture
def mock_ohlc_with_rsi():
    """Mock OHLC DataFrame with RSI column."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100 + i * 0.5 for i in range(100)],
            "High": [105 + i * 0.5 for i in range(100)],
            "Low": [95 + i * 0.5 for i in range(100)],
            "Close": [100 + i * 0.5 for i in range(100)],
            "Volume": [1000000 + i * 10000 for i in range(100)],
        },
        index=dates,
    )
    df["RSI"] = 50.0  # Neutral RSI
    return df


@pytest.fixture
def mock_bullish_divergence_result():
    """Mock divergence detection result with bullish divergence."""
    return {
        "bullish": True,
        "bearish": False,
        "bullish_details": "2-point bullish divergence detected",
        "bearish_details": "",
        "bullish_indices": (
            pd.Timestamp("2024-01-10"),
            pd.Timestamp("2024-01-20"),
            pd.Timestamp("2024-01-11"),
            pd.Timestamp("2024-01-21"),
        ),
        "bearish_indices": None,
    }


@pytest.fixture
def mock_bearish_divergence_result():
    """Mock divergence detection result with bearish divergence."""
    return {
        "bullish": False,
        "bearish": True,
        "bullish_details": "",
        "bearish_details": "2-point bearish divergence detected",
        "bullish_indices": None,
        "bearish_indices": (
            pd.Timestamp("2024-01-10"),
            pd.Timestamp("2024-01-20"),
            pd.Timestamp("2024-01-11"),
            pd.Timestamp("2024-01-21"),
        ),
    }


@pytest.fixture
def mock_no_divergence_result():
    """Mock divergence detection with no divergence found."""
    return {
        "bullish": False,
        "bearish": False,
        "bullish_details": "",
        "bearish_details": "",
        "bullish_indices": None,
        "bearish_indices": None,
    }


def test_screen_rsi_divergence_bullish_filter_includes_bullish(
    mock_ohlc_with_rsi, mock_bullish_divergence_result
):
    """Test divergence_type='bullish' includes bullish divergences."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_bullish_divergence_result,
            ):
                results = screen_rsi_divergence(
                    tickers=["TEST"], divergence_type="bullish", lookback=60
                )

    assert len(results) == 1
    assert results[0].divergence_type == "bullish"
    assert results[0].bullish_divergence is True


def test_screen_rsi_divergence_bearish_filter_includes_bearish(
    mock_ohlc_with_rsi, mock_bearish_divergence_result
):
    """Test divergence_type='bearish' includes bearish divergences."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_bearish_divergence_result,
            ):
                results = screen_rsi_divergence(
                    tickers=["TEST"], divergence_type="bearish", lookback=60
                )

    assert len(results) == 1
    assert results[0].divergence_type == "bearish"
    assert results[0].bearish_divergence is True


def test_screen_rsi_divergence_all_filter_includes_both(mock_ohlc_with_rsi):
    """Test divergence_type='all' includes both types."""
    both_result = {
        "bullish": True,
        "bearish": True,
        "bullish_details": "Bullish detected",
        "bearish_details": "Bearish detected",
        "bullish_indices": (
            pd.Timestamp("2024-01-10"),
            pd.Timestamp("2024-01-20"),
            pd.Timestamp("2024-01-11"),
            pd.Timestamp("2024-01-21"),
        ),
        "bearish_indices": (
            pd.Timestamp("2024-02-05"),
            pd.Timestamp("2024-02-15"),
            pd.Timestamp("2024-02-06"),
            pd.Timestamp("2024-02-16"),
        ),
    }

    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=both_result,
            ):
                results = screen_rsi_divergence(
                    tickers=["TEST"], divergence_type="all", lookback=60
                )

    assert len(results) == 1
    assert "bullish & bearish" in results[0].divergence_type.lower()


def test_screen_rsi_divergence_exclude_breakouts_filters_bullish(
    mock_ohlc_with_rsi, mock_bullish_divergence_result
):
    """Test exclude_breakouts=True filters out completed breakouts."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_bullish_divergence_result,
            ):
                with patch(
                    "stockcharts.screener.rsi_divergence.check_breakout_occurred",
                    return_value=True,
                ):  # Breakout happened
                    results = screen_rsi_divergence(
                        tickers=["TEST"],
                        divergence_type="bullish",
                        exclude_breakouts=True,
                        lookback=60,
                    )

    # Should be filtered out
    assert len(results) == 0


def test_screen_rsi_divergence_exclude_breakouts_includes_non_breakout(
    mock_ohlc_with_rsi, mock_bullish_divergence_result
):
    """Test exclude_breakouts=True includes divergences without breakout."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_bullish_divergence_result,
            ):
                with patch(
                    "stockcharts.screener.rsi_divergence.check_breakout_occurred",
                    return_value=False,
                ):  # No breakout
                    results = screen_rsi_divergence(
                        tickers=["TEST"],
                        divergence_type="bullish",
                        exclude_breakouts=True,
                        lookback=60,
                    )

    # Should be included
    assert len(results) == 1


def test_screen_rsi_divergence_exclude_failed_breakouts_filters_bearish(
    mock_ohlc_with_rsi, mock_bearish_divergence_result
):
    """Test exclude_failed_breakouts=True filters out failed attempts."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_bearish_divergence_result,
            ):
                with patch(
                    "stockcharts.screener.rsi_divergence.check_failed_breakout",
                    return_value=True,
                ):  # Failed attempt
                    results = screen_rsi_divergence(
                        tickers=["TEST"],
                        divergence_type="bearish",
                        exclude_failed_breakouts=True,
                        lookback=60,
                    )

    # Should be filtered out
    assert len(results) == 0


def test_screen_rsi_divergence_price_filter_min(
    mock_ohlc_with_rsi, mock_bullish_divergence_result
):
    """Test min_price filter excludes low-priced stocks."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_bullish_divergence_result,
            ):
                # Current price is ~149.5, set min above that
                results = screen_rsi_divergence(
                    tickers=["TEST"],
                    divergence_type="bullish",
                    min_price=200.0,
                    lookback=60,
                )

    # Should be filtered out
    assert len(results) == 0


def test_screen_rsi_divergence_price_filter_max(
    mock_ohlc_with_rsi, mock_bullish_divergence_result
):
    """Test max_price filter excludes high-priced stocks."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_bullish_divergence_result,
            ):
                # Current price is ~149.5, set max below that
                results = screen_rsi_divergence(
                    tickers=["TEST"],
                    divergence_type="bullish",
                    max_price=50.0,
                    lookback=60,
                )

    # Should be filtered out
    assert len(results) == 0


def test_screen_rsi_divergence_volume_filter(
    mock_ohlc_with_rsi, mock_bullish_divergence_result
):
    """Test min_volume filter excludes low-volume stocks."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_bullish_divergence_result,
            ):
                # Average volume is ~1,495,000, set min above that
                results = screen_rsi_divergence(
                    tickers=["TEST"],
                    divergence_type="bullish",
                    min_volume=10000000.0,
                    lookback=60,
                )

    # Should be filtered out
    assert len(results) == 0


def test_screen_rsi_divergence_no_divergence_excludes(
    mock_ohlc_with_rsi, mock_no_divergence_result
):
    """Test that stocks with no divergence are excluded."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_no_divergence_result,
            ):
                results = screen_rsi_divergence(
                    tickers=["TEST"], divergence_type="all", lookback=60
                )

    assert len(results) == 0


def test_screen_rsi_divergence_3point_with_scoring(mock_ohlc_with_rsi):
    """Test 3-point divergence with sequence scoring."""
    three_point_result = {
        "bullish": True,
        "bearish": False,
        "bullish_details": "3-point bullish divergence",
        "bearish_details": "",
        "bullish_indices": (
            pd.Timestamp("2024-01-10"),
            pd.Timestamp("2024-01-20"),
            pd.Timestamp("2024-01-30"),
            pd.Timestamp("2024-01-11"),
            pd.Timestamp("2024-01-21"),
            pd.Timestamp("2024-01-31"),
        ),
        "bearish_indices": None,
    }

    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=three_point_result,
            ):
                results = screen_rsi_divergence(
                    tickers=["TEST"],
                    divergence_type="bullish",
                    min_swing_points=3,
                    use_sequence_scoring=True,
                    min_sequence_score=1.0,
                    lookback=60,
                )

    assert len(results) == 1
    assert results[0].bullish_indices is not None
    assert len(results[0].bullish_indices) == 6  # 3-point has 6 indices


def test_screen_rsi_divergence_ema_deriv_pivot_method(
    mock_ohlc_with_rsi, mock_bullish_divergence_result
):
    """Test screener with ema-deriv pivot detection method."""
    with patch(
        "stockcharts.screener.rsi_divergence.fetch_ohlc",
        return_value=mock_ohlc_with_rsi,
    ):
        with patch(
            "stockcharts.screener.rsi_divergence.compute_rsi",
            return_value=mock_ohlc_with_rsi["RSI"],
        ):
            with patch(
                "stockcharts.screener.rsi_divergence.detect_divergence",
                return_value=mock_bullish_divergence_result,
            ) as mock_detect:
                results = screen_rsi_divergence(
                    tickers=["TEST"],
                    divergence_type="bullish",
                    pivot_method="ema-deriv",
                    ema_price_span=5,
                    ema_rsi_span=5,
                    lookback=60,
                )

    # Verify pivot_method was passed to detect_divergence
    call_kwargs = mock_detect.call_args[1]
    assert call_kwargs["pivot_method"] == "ema-deriv"
    assert call_kwargs["ema_price_span"] == 5
    assert call_kwargs["ema_rsi_span"] == 5


def test_save_results_to_csv_non_empty(tmp_path):
    """Test save_results_to_csv with non-empty results."""
    results = [
        RSIDivergenceResult(
            ticker="AAPL",
            company_name="Apple Inc.",
            close_price=150.0,
            rsi=45.0,
            divergence_type="bullish",
            bullish_divergence=True,
            bearish_divergence=False,
            details="Bullish divergence detected",
            bullish_indices=(
                pd.Timestamp("2024-01-10"),
                pd.Timestamp("2024-01-20"),
                pd.Timestamp("2024-01-11"),
                pd.Timestamp("2024-01-21"),
            ),
            bearish_indices=None,
        )
    ]

    output_file = tmp_path / "results.csv"

    save_results_to_csv(results, str(output_file))

    assert output_file.exists()

    # Verify CSV structure
    df = pd.read_csv(output_file)
    assert len(df) == 1
    assert df["Ticker"].iloc[0] == "AAPL"
    assert df["Divergence Type"].iloc[0] == "bullish"
    assert "Bullish_Indices" in df.columns


def test_save_results_to_csv_empty():
    """Test save_results_to_csv with empty results."""
    results = []

    # Should print message and return without error
    save_results_to_csv(results, "nonexistent.csv")

    # No file should be created (function returns early)
    import os

    assert not os.path.exists("nonexistent.csv")
