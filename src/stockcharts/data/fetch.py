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

import re

import pandas as pd

try:
    import yfinance as yf
except ImportError as e:  # pragma: no cover - guidance only
    raise ImportError(
        "yfinance must be installed to use fetch_ohlc. Install with `pip install yfinance`."
    ) from e


VALID_INTERVALS = {"1d", "1wk", "1mo"}  # Aggregation intervals: daily, weekly, monthly
VALID_LOOKBACK = {"5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_date(s: str | None) -> bool:
    return bool(s and DATE_RE.match(s))


def _normalize_date(s: str | None) -> str | None:
    """Return date string if valid YYYY-MM-DD else None."""
    if not _is_date(s):
        return None
    return s


def _validate_and_build_download_kwargs(
    interval: str,
    lookback: str | None,
    start: str | None,
    end: str | None,
    auto_adjust: bool,
) -> dict:
    """Validate parameters and build kwargs for yf.download.

    Args:
        interval: Aggregation interval ('1d', '1wk', '1mo').
        lookback: Relative period for history.
        start: Start date YYYY-MM-DD.
        end: End date YYYY-MM-DD.
        auto_adjust: Whether to adjust OHLC for splits/dividends.

    Returns:
        Dictionary with validated download kwargs for yfinance.

    Raises:
        ValueError: If interval or lookback is not in valid set.
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

    return download_kwargs


def _normalize_single_ticker_df(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Normalize a single-ticker DataFrame from yfinance.

    Args:
        df: Raw DataFrame from yfinance download.
        ticker: Stock symbol (used for error messages).

    Returns:
        DataFrame with standardized columns [Open, High, Low, Close, Volume].

    Raises:
        ValueError: If data is empty or missing required columns.
    """
    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'.")

    # Flatten multi-level columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Standardize columns
    df = df.reset_index().set_index(df.index.names[0])

    needed = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns in data: {missing}")
    return df[needed].copy()


def fetch_ohlc(
    ticker: str,
    interval: str = "1d",
    lookback: str | None = None,
    start: str | None = None,
    end: str | None = None,
    auto_adjust: bool = False,
) -> pd.DataFrame:
    """Fetch OHLC data for a single ticker.

    Args:
        ticker: Stock symbol to download.
        interval: Aggregation interval ('1d', '1wk', '1mo').
        lookback: Relative period for history ('1y', '5y', 'max', etc.).
        start: Start date YYYY-MM-DD (overrides lookback if end also provided).
        end: End date YYYY-MM-DD.
        auto_adjust: Whether to adjust OHLC for splits/dividends.

    Returns:
        DataFrame with columns [Open, High, Low, Close, Volume].

    Raises:
        ValueError: If data is empty or missing required columns.

    Note:
        - If both start and end are valid dates they override lookback.
        - If either start/end is invalid (e.g. '3mo'), it is ignored.
        - If nothing specified, default lookback = '1y'.
    """
    download_kwargs = _validate_and_build_download_kwargs(
        interval, lookback, start, end, auto_adjust
    )

    df = yf.download(ticker, **download_kwargs)
    return _normalize_single_ticker_df(df, ticker)


def fetch_ohlc_batch(
    tickers: list[str],
    interval: str = "1d",
    lookback: str | None = None,
    start: str | None = None,
    end: str | None = None,
    auto_adjust: bool = False,
    threads: bool = True,
    progress: bool = False,
) -> dict[str, pd.DataFrame]:
    """Fetch OHLC data for multiple tickers in a single batch request.

    Uses yfinance's built-in threading for parallel downloads, which is
    significantly faster than sequential single-ticker downloads.

    Args:
        tickers: List of stock symbols to download.
        interval: Aggregation interval ('1d', '1wk', '1mo').
        lookback: Relative period for history ('1y', '5y', 'max', etc.).
        start: Start date YYYY-MM-DD (overrides lookback if end also provided).
        end: End date YYYY-MM-DD.
        auto_adjust: Whether to adjust OHLC for splits/dividends.
        threads: Use multi-threading for faster downloads (default: True).
        progress: Show download progress bar (default: False).

    Returns:
        Dictionary mapping ticker symbols to their OHLC DataFrames.
        Failed downloads are silently omitted from results.
    """
    if not tickers:
        return {}

    download_kwargs = _validate_and_build_download_kwargs(
        interval, lookback, start, end, auto_adjust
    )
    download_kwargs["progress"] = progress
    download_kwargs["threads"] = threads
    download_kwargs["group_by"] = "ticker"

    # yfinance accepts list or space-separated string
    batch_df = yf.download(tickers, **download_kwargs)

    results: dict[str, pd.DataFrame] = {}

    if batch_df.empty:
        return results

    # Handle single vs multiple ticker return format
    if len(tickers) == 1:
        # Single ticker: columns are just OHLCV
        ticker = tickers[0]
        try:
            df = _normalize_single_ticker_df(batch_df.copy(), ticker)
            results[ticker] = df
        except ValueError:
            pass  # Skip failed ticker
    else:
        # Multiple tickers: MultiIndex columns (ticker, OHLCV)
        for ticker in tickers:
            try:
                if ticker not in batch_df.columns.get_level_values(0):
                    continue

                ticker_df = batch_df[ticker].copy()

                # Drop rows where all values are NaN (no data for this date)
                ticker_df = ticker_df.dropna(how="all")

                if ticker_df.empty:
                    continue

                # Standardize columns
                ticker_df = ticker_df.reset_index().set_index(ticker_df.index.names[0])

                needed = ["Open", "High", "Low", "Close", "Volume"]
                missing = [c for c in needed if c not in ticker_df.columns]
                if missing:
                    continue

                results[ticker] = ticker_df[needed].copy()
            except Exception:
                # Skip any ticker that fails processing
                continue

    return results


__all__ = ["fetch_ohlc", "fetch_ohlc_batch"]
