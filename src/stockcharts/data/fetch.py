"""Data fetching utilities using yfinance.

Function:
    fetch_ohlc(
        ticker,
        interval="1d",
        lookback: str | None = None,
        start: str | None = None,
        end: str | None = None,
        auto_adjust: bool = False,
    )
    
Parameter semantics:
    - interval: Aggregation interval for candles ('1d', '1wk', '1mo').
    - lookback: Relative period for history breadth ('5d','1mo','3mo','6mo','1y','2y','5y','10y','ytd','max').
    - start/end: Explicit date range (YYYY-MM-DD). If both provided they override lookback.
      Passing values like '3mo' to start/end is invalid and will be ignored.

We guard against accidentally sending a lookback string where a date is required by validating format.

Returns a pandas DataFrame with columns: Open, High, Low, Close, Volume
"""
from __future__ import annotations

from typing import Optional
import re
from datetime import datetime
import pandas as pd

try:
    import yfinance as yf
except ImportError as e:  # pragma: no cover - guidance only
    raise ImportError("yfinance must be installed to use fetch_ohlc. Install with `pip install yfinance`." ) from e


VALID_INTERVALS = {"1d", "1wk", "1mo"}  # Aggregation intervals: daily, weekly, monthly
VALID_LOOKBACK = {"5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _is_date(s: Optional[str]) -> bool:
    return bool(s and DATE_RE.match(s))

def _normalize_date(s: Optional[str]) -> Optional[str]:
    """Return date string if valid YYYY-MM-DD else None."""
    if not _is_date(s):
        return None
    return s


def fetch_ohlc(
    ticker: str,
    interval: str = "1d",
    lookback: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    auto_adjust: bool = False,
) -> pd.DataFrame:
    """Fetch OHLC data for a single ticker.

    Guard rails:
        - If both start and end are valid dates they override lookback.
        - If either start/end is invalid (e.g. '3mo'), it is ignored.
        - If nothing specified, default lookback = '1y'.
    """
    if interval not in VALID_INTERVALS:
        raise ValueError(f"Unsupported interval '{interval}'. Allowed: {sorted(VALID_INTERVALS)}")

    start = _normalize_date(start)
    end = _normalize_date(end)

    if lookback and (start or end):
        # Explicit date range takes precedence; ignore lookback
        lookback = None

    if not lookback and not start and not end:
        lookback = "1y"

    if lookback and lookback not in VALID_LOOKBACK:
        raise ValueError(f"Unsupported lookback '{lookback}'. Allowed: {sorted(VALID_LOOKBACK)}")

    download_kwargs = {
        "interval": interval,
        "progress": False,
        "auto_adjust": auto_adjust,
    }
    if start and end:
        download_kwargs["start"] = start
        download_kwargs["end"] = end
    else:
        download_kwargs["period"] = lookback

    df = yf.download(ticker, **download_kwargs)
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
