"""Data fetching utilities using yfinance.

Function:
    fetch_ohlc(ticker, start=None, end=None, period="1d", lookback=None)
    
Parameters:
    - period: Aggregation period ('1d', '1wk', '1mo') - how data is grouped
    - lookback: Time window ('3mo', '1y', etc.) - how far back to fetch
    - start/end: Explicit date range (alternative to lookback)
    
Returns a pandas DataFrame with columns: Open, High, Low, Close, Volume
"""
from __future__ import annotations

from typing import Optional
import pandas as pd

try:
    import yfinance as yf
except ImportError as e:  # pragma: no cover - guidance only
    raise ImportError("yfinance must be installed to use fetch_ohlc. Install with `pip install yfinance`." ) from e


VALID_PERIODS = {"1d", "1wk", "1mo"}  # Aggregation periods: daily, weekly, monthly


def fetch_ohlc(
    ticker: str, 
    start: Optional[str] = None, 
    end: Optional[str] = None, 
    period: str = "1d",
    lookback: Optional[str] = None
) -> pd.DataFrame:
    """Fetch OHLC data for a single ticker.

    Parameters
    ----------
    ticker : str
        Symbol, e.g. 'AAPL'.
    start : str | None
        Start date YYYY-MM-DD. Optional. Cannot be used with lookback.
    end : str | None
        End date YYYY-MM-DD. Optional. Cannot be used with lookback.
    period : str
        Aggregation period (how data is grouped): '1d' (daily), '1wk' (weekly), '1mo' (monthly).
        Default '1d'.
    lookback : str | None
        How far back to fetch data: '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'.
        Cannot be used with start/end. If not specified and no start/end given, defaults to '1y'.

    Returns
    -------
    DataFrame with columns Open, High, Low, Close, Volume and DatetimeIndex.
    """
    if period not in VALID_PERIODS:
        raise ValueError(f"Unsupported period '{period}'. Allowed: {sorted(VALID_PERIODS)}")

    # Validate parameter combinations
    if lookback and (start or end):
        raise ValueError("Cannot specify both 'lookback' and 'start'/'end' parameters")
    
    # If neither lookback nor start/end specified, default to 1 year
    if not lookback and not start and not end:
        lookback = "1y"

    # yfinance uses 'interval' for aggregation period and 'period' for lookback
    df = yf.download(ticker, start=start, end=end, period=lookback, interval=period, progress=False, auto_adjust=False)
    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'.")

    # Flatten multi-level columns if present (yfinance returns (column, ticker) tuples for single ticker)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # Standardize columns (yfinance sometimes returns lowercase or multi-level)
    df = df.reset_index().set_index(df.index.names[0])  # ensure first index is datetime
    # Keep only needed columns
    needed = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns in data: {missing}")
    return df[needed].copy()

__all__ = ["fetch_ohlc"]
