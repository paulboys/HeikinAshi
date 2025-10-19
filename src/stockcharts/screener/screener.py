"""NASDAQ Heiken Ashi screener module.

Screens NASDAQ stocks for bullish (green) or bearish (red) Heiken Ashi patterns.
"""
from __future__ import annotations

import time
from typing import List, Literal, Optional
from dataclasses import dataclass

import pandas as pd

from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.screener.nasdaq import get_nasdaq_tickers


@dataclass
class ScreenResult:
    """Result for a single ticker screening."""
    ticker: str
    color: Literal["green", "red"]
    previous_color: Literal["green", "red"]
    color_changed: bool
    ha_open: float
    ha_close: float
    last_date: str
    interval: str
    avg_volume: float


def get_candle_color(ha_df: pd.DataFrame, index: int = -1) -> Literal["green", "red"]:
    """Determine if a Heiken Ashi candle is green or red.
    
    Parameters
    ----------
    ha_df : pd.DataFrame
        Heiken Ashi DataFrame with columns HA_Open, HA_Close
    index : int
        Index of the candle to check (-1 for most recent, -2 for previous, etc.)
    
    Returns
    -------
    "green" if HA_Close >= HA_Open (bullish), "red" otherwise (bearish)
    """
    row = ha_df.iloc[index]
    return "green" if row["HA_Close"] >= row["HA_Open"] else "red"


def screen_ticker(
    ticker: str,
    period: str = "1d",
    lookback: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    debug: bool = False
) -> Optional[ScreenResult]:
    """Screen a single ticker for its latest Heiken Ashi candle color.
    
    Parameters
    ----------
    ticker : str
        Stock symbol
    period : str
        Aggregation period: "1d" (daily), "1wk" (weekly), "1mo" (monthly)
    lookback : str | None
        How far back to fetch: '1mo', '3mo', '6mo', '1y', '2y', '5y', etc.
    start : str | None
        Start date YYYY-MM-DD
    end : str | None
        End date YYYY-MM-DD
    
    Returns
    -------
    ScreenResult or None if data unavailable or error occurs
    """
    try:
        # Fetch recent data
        df = fetch_ohlc(ticker, interval=period, lookback=lookback, start=start, end=end)
        
        if df.empty or len(df) < 2:
            return None
        
        # Compute Heiken Ashi
        ha = heiken_ashi(df)
        
        # Need at least 2 candles to detect color change
        if ha.empty or len(ha) < 2:
            return None
        
        # Get color of most recent candle and previous candle
        current_color = get_candle_color(ha, index=-1)
        previous_color = get_candle_color(ha, index=-2)
        color_changed = current_color != previous_color
        
        last_row = ha.iloc[-1]
        
        # Calculate average volume (use last 20 periods or all available if less)
        volume_window = min(20, len(df))
        avg_volume = float(df['Volume'].tail(volume_window).mean())
        
        return ScreenResult(
            ticker=ticker,
            color=current_color,
            previous_color=previous_color,
            color_changed=color_changed,
            ha_open=float(last_row["HA_Open"]),
            ha_close=float(last_row["HA_Close"]),
            last_date=str(ha.index[-1].date()),
            interval=period,  # Store the aggregation period
            avg_volume=avg_volume
        )
    
    except Exception as e:
        # Silently skip tickers with errors (delisted, no data, etc.)
        if debug:
            print(f"  DEBUG: Error screening {ticker}: {type(e).__name__}: {e}")
        return None


def screen_nasdaq(
    color_filter: Literal["green", "red", "all"] = "all",
    period: str = "1d",
    limit: Optional[int] = None,
    delay: float = 0.5,
    verbose: bool = True,
    changed_only: bool = False,
    lookback: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    debug: bool = False,
    min_volume: Optional[float] = None,
    min_price: Optional[float] = None,
    ticker_filter: Optional[List[str]] = None
) -> List[ScreenResult]:
    """Screen NASDAQ stocks for Heiken Ashi candle colors.
    
    Parameters
    ----------
    color_filter : "green" | "red" | "all"
        Filter results by current candle color. "all" returns both.
    period : str
        Aggregation period: "1d" (daily), "1wk" (weekly), "1mo" (monthly)
    limit : int | None
        Maximum number of tickers to screen (for testing). None = all.
    delay : float
        Delay in seconds between API calls to avoid rate limits
    verbose : bool
        Print progress messages
    changed_only : bool
        If True, only return tickers where the candle color just changed.
        For example, if color_filter="green" and changed_only=True,
        only returns stocks that turned from red to green.
    lookback : str | None
        How far back to fetch: '1mo', '3mo', '6mo', '1y', '2y', '5y', etc.
        Day traders: '5d', '1mo'. Swing traders: '3mo', '6mo'. Position traders: '1y', '5y'.
    start : str | None
        Start date YYYY-MM-DD. Cannot be used with lookback.
    min_volume : float | None
        Minimum average daily volume (in shares). Filters out low-volume stocks.
        Recommended: 500000 (500K) for swing trading, 1000000 (1M) for day trading.
    min_price : float | None
        Minimum stock price (in dollars). Filters out stocks below this price.
        Useful for avoiding penny stocks (e.g., 5.0 or 10.0).
    end : str | None
        End date YYYY-MM-DD. Cannot be used with lookback.
    ticker_filter : List[str] | None
        Optional list of ticker symbols to screen. If provided, only these tickers
        will be screened instead of all NASDAQ stocks. Useful for filtering by
        a pre-screened list (e.g., from RSI divergence results).
    
    Returns
    -------
    List[ScreenResult]
        List of results matching the color filter, sorted by ticker
    """
    # Use provided ticker filter or fetch all NASDAQ tickers
    if ticker_filter is not None:
        tickers = ticker_filter
        if limit is not None:
            tickers = tickers[:limit]
    else:
        tickers = get_nasdaq_tickers(limit=limit)
    
    results = []
    
    change_msg = " that just changed color" if changed_only else ""
    filter_msg = " (filtered list)" if ticker_filter is not None else ""
    if verbose:
        print(f"Screening {len(tickers)} tickers{filter_msg} for {color_filter} "
              f"Heiken Ashi candles{change_msg} ({period} period)...")
        print("-" * 70)
    
    for i, ticker in enumerate(tickers, 1):
        if verbose and i % 10 == 0:
            print(f"Progress: {i}/{len(tickers)} tickers screened, "
                  f"{len(results)} matches found...")
        
        result = screen_ticker(ticker, period=period, lookback=lookback, start=start, end=end, debug=debug)
        
        if result is not None:
            # Apply color filter
            if color_filter == "all" or result.color == color_filter:
                # Apply color change filter if requested
                if not changed_only or result.color_changed:
                    # Apply volume filter if specified
                    if min_volume is None or result.avg_volume >= min_volume:
                        # Apply price filter if specified
                        if min_price is None or result.ha_close >= min_price:
                            results.append(result)
        
        # Rate limiting
        if delay > 0 and i < len(tickers):
            time.sleep(delay)
    
    if verbose:
        print("-" * 70)
        print(f"Screening complete: {len(results)} {color_filter} candles{change_msg} found")
    
    return sorted(results, key=lambda x: x.ticker)


__all__ = ["screen_nasdaq", "screen_ticker", "get_candle_color", "ScreenResult"]
