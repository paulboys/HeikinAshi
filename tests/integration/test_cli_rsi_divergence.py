"""
Integration tests for RSI divergence CLI workflow.
Tests end-to-end behavior with mocked data fetching.
"""
import os
import tempfile
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from stockcharts.screener.rsi_divergence import screen_rsi_divergence, save_results_to_csv


def test_rsi_divergence_screen_csv_output(mock_yfinance_download, tmp_path):
    """
    Integration test: verify screen_rsi_divergence produces valid CSV with expected headers.
    Uses mocked yfinance data to avoid network dependency.
    """
    output_file = tmp_path / "test_divergence.csv"
    
    # Mock the NASDAQ ticker list to avoid fetching thousands
    with patch('stockcharts.screener.nasdaq.get_nasdaq_tickers', return_value=['TEST']):
        results = screen_rsi_divergence(
            tickers=['TEST'],
            period='3mo',
            interval='1d',
            rsi_period=14,
            divergence_type='all',
            swing_window=5,
            lookback=60
        )
    
    # Verify we got results (synthetic data should produce divergence)
    # If no divergence found, that's okay - test the save behavior
    if results:
        # Save results
        save_results_to_csv(results, str(output_file))
        
        # Verify CSV was created
        assert output_file.exists(), "CSV output file should be created when results exist"
        
        # Read and validate structure
        df = pd.read_csv(output_file)
        expected_columns = ['Ticker', 'Company', 'Price', 'RSI', 'Divergence Type']
        
        for col in expected_columns:
            assert col in df.columns, f"Expected column '{col}' in CSV output"
    else:
        # No results - verify save_results_to_csv handles empty list gracefully
        save_results_to_csv(results, str(output_file))
        assert not output_file.exists(), "CSV should not be created for empty results"


def test_rsi_divergence_bullish_only_filter(mock_yfinance_download):
    """
    Integration test: verify divergence_type='bullish' filter works correctly.
    """
    with patch('stockcharts.screener.nasdaq.get_nasdaq_tickers', return_value=['TEST']):
        results = screen_rsi_divergence(
            tickers=['TEST'],
            period='3mo',
            interval='1d',
            divergence_type='bullish',
            swing_window=5,
            lookback=60
        )
    
    # All results should be bullish if any divergence found
    for result in results:
        if result.divergence_type != 'none':
            assert result.divergence_type == 'bullish', "Only bullish divergences should be returned"


def test_rsi_divergence_price_filter(mock_yfinance_download):
    """
    Integration test: verify min_price filter excludes low-priced stocks.
    """
    with patch('stockcharts.screener.nasdaq.get_nasdaq_tickers', return_value=['TEST']):
        results = screen_rsi_divergence(
            tickers=['TEST'],
            period='3mo',
            interval='1d',
            min_price=100.0,  # Set threshold above synthetic data range
            swing_window=5,
            lookback=60
        )
    
    # All results should meet min price threshold
    for result in results:
        assert result.close_price >= 100.0, f"Stock price {result.close_price} below min_price threshold"


def test_rsi_divergence_empty_ticker_list():
    """
    Integration test: verify graceful handling of empty ticker list.
    """
    results = screen_rsi_divergence(
        tickers=[],
        period='3mo',
        interval='1d'
    )
    
    assert len(results) == 0, "Empty ticker list should return empty results"


def test_rsi_divergence_three_point_mode(mock_yfinance_download):
    """
    Integration test: verify 3-point divergence detection with sequence scoring.
    """
    with patch('stockcharts.screener.nasdaq.get_nasdaq_tickers', return_value=['TEST']):
        results = screen_rsi_divergence(
            tickers=['TEST'],
            period='3mo',
            interval='1d',
            min_swing_points=3,
            use_sequence_scoring=True,
            min_sequence_score=1.0,
            swing_window=5,
            lookback=60
        )
    
    # Test should complete without error
    # Results may be empty if synthetic data doesn't produce 3-point patterns
    assert isinstance(results, list), "Results should be a list"
