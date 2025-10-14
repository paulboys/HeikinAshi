"""NASDAQ ticker list fetching utilities.

Functions for obtaining lists of NASDAQ-listed stock symbols.
"""
from __future__ import annotations

import pandas as pd
from typing import List
import io
import urllib.request


def get_nasdaq_tickers(limit: int | None = None) -> List[str]:
    """Fetch list of NASDAQ ticker symbols.
    
    Parameters
    ----------
    limit : int | None
        Maximum number of tickers to return. None returns all available.
        Useful for testing with smaller subsets.
    
    Returns
    -------
    List[str]
        List of ticker symbols (e.g., ['AAPL', 'MSFT', 'GOOGL', ...])
    
    Notes
    -----
    This function fetches data from NASDAQ's official FTP server.
    Falls back to a static list if the download fails.
    """
    # NASDAQ official FTP server with listed securities
    # This file is updated daily and contains all NASDAQ-listed stocks
    nasdaq_url = "ftp://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt"
    
    # Fallback: static list of major NASDAQ-100 tickers
    major_tickers = [
        # Tech giants
        'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'TSLA', 'NVDA',
        # Other major NASDAQ stocks
        'AVGO', 'COST', 'CSCO', 'ADBE', 'NFLX', 'PEP', 'INTC', 'CMCSA',
        'AMD', 'QCOM', 'TXN', 'INTU', 'AMGN', 'AMAT', 'HON', 'SBUX',
        'BKNG', 'GILD', 'ADP', 'MDLZ', 'ISRG', 'ADI', 'VRTX', 'REGN',
        'LRCX', 'PANW', 'MU', 'KLAC', 'SNPS', 'CDNS', 'MELI', 'ASML',
        'ABNB', 'MAR', 'ORLY', 'CTAS', 'MRVL', 'AEP', 'FTNT', 'DXCM',
        'ADSK', 'MNST', 'PCAR', 'NXPI', 'WDAY', 'PAYX', 'ROST', 'CPRT',
        # Additional tickers for broader coverage
        'KDP', 'ODFL', 'CHTR', 'FAST', 'BKR', 'EA', 'CTSH', 'CSGP',
        'XEL', 'VRSK', 'DDOG', 'IDXX', 'ANSS', 'GEHC', 'ON', 'ZS',
        'TEAM', 'FANG', 'TTWO', 'BIIB', 'CRWD', 'ILMN'
    ]
    
    try:
        # Attempt to fetch from NASDAQ FTP server
        with urllib.request.urlopen(nasdaq_url, timeout=10) as response:
            content = response.read().decode('utf-8')
        
        # Parse the pipe-delimited file
        df = pd.read_csv(io.StringIO(content), sep='|')
        
        # Filter out test symbols and get ticker column
        # Handle potential NaN values in 'Test Issue' column
        tickers = df[df['Test Issue'].fillna('Y') == 'N']['Symbol'].tolist()
        
        # Remove any tickers with special characters (like $ for warrants)
        # Also filter out NaN values and ensure all are strings
        tickers = [str(t) for t in tickers if pd.notna(t) and '$' not in str(t) and '.' not in str(t)]
        
    except Exception as e:
        print(f"Warning: Could not fetch NASDAQ tickers from FTP: {e}")
        print("Using fallback list of major NASDAQ tickers")
        tickers = major_tickers
    
    # Apply limit if specified
    if limit is not None:
        tickers = tickers[:limit]
    
    return tickers