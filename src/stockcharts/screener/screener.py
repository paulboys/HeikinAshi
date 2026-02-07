"""NASDAQ Heiken Ashi screener module.

Screens NASDAQ stocks for bullish (green) or bearish (red) Heiken Ashi patterns.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.data.fetch import fetch_ohlc, fetch_ohlc_batch
from stockcharts.indicators.heiken_runs import compute_ha_run_stats
from stockcharts.screener.nasdaq import get_nasdaq_tickers


@dataclass
class ScreenResult:
    """Result for a single ticker Heiken Ashi screening.

    Attributes:
        ticker: Stock symbol.
        color: Current candle color ('green' = bullish, 'red' = bearish).
        previous_color: Previous candle color.
        color_changed: True if color changed from previous candle.
        ha_open: Heiken Ashi open price.
        ha_close: Heiken Ashi close price.
        last_date: Date of the most recent candle.
        interval: Time interval used ('1d', '1wk', '1mo').
        avg_volume: Average trading volume over recent period.
        run_length: Consecutive candles of same color.
        run_percentile: Percentile rank of run length (0-100).
    """

    ticker: str
    color: Literal["green", "red"]
    previous_color: Literal["green", "red"]
    color_changed: bool
    ha_open: float
    ha_close: float
    last_date: str
    interval: str
    avg_volume: float
    run_length: int
    run_percentile: float


def get_candle_color(ha_df: pd.DataFrame, index: int = -1) -> Literal["green", "red"]:
    """Determine if a Heiken Ashi candle is green or red.

    Args:
        ha_df: Heiken Ashi DataFrame with columns HA_Open, HA_Close.
        index: Index of the candle to check (-1 for most recent, -2 for previous).

    Returns:
        'green' if HA_Close >= HA_Open (bullish), 'red' otherwise (bearish).
    """
    row = ha_df.iloc[index]
    return "green" if row["HA_Close"] >= row["HA_Open"] else "red"


def screen_ticker(
    ticker: str,
    period: str = "1d",
    lookback: str | None = None,
    start: str | None = None,
    end: str | None = None,
    debug: bool = False,
) -> ScreenResult | None:
    """Screen a single ticker for its latest Heiken Ashi candle color.

    Args:
        ticker: Stock symbol.
        period: Aggregation period ('1d', '1wk', '1mo').
        lookback: How far back to fetch ('1mo', '3mo', '6mo', '1y', '2y', '5y', etc.).
        start: Start date YYYY-MM-DD.
        end: End date YYYY-MM-DD.
        debug: When True, prints detailed error information during screening.

    Returns:
        ScreenResult or None if data unavailable or error occurs.
    """
    try:
        # Fetch recent data
        df = fetch_ohlc(ticker, interval=period, lookback=lookback, start=start, end=end)
        return _process_ticker_dataframe(ticker, df, period, debug=debug)
    except Exception as e:
        if debug:
            print(f"  DEBUG: Error screening {ticker}: {type(e).__name__}: {e}")
        return None


def _process_ticker_dataframe(
    ticker: str,
    df: pd.DataFrame,
    period: str,
    debug: bool = False,
) -> ScreenResult | None:
    """Process a pre-downloaded DataFrame to compute Heiken Ashi screening result.

    This is the core processing logic extracted from screen_ticker to allow
    reuse with batch-downloaded data.

    Args:
        ticker: Stock symbol.
        df: OHLC DataFrame with columns Open, High, Low, Close, Volume.
        period: Aggregation period used (for result metadata).
        debug: When True, prints detailed error information.

    Returns:
        ScreenResult or None if data unavailable or error occurs.
    """
    try:
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
        avg_volume = float(df["Volume"].tail(volume_window).mean())

        # Compute run statistics
        run_stats = compute_ha_run_stats(ha)

        return ScreenResult(
            ticker=ticker,
            color=current_color,
            previous_color=previous_color,
            color_changed=color_changed,
            ha_open=float(last_row["HA_Open"]),
            ha_close=float(last_row["HA_Close"]),
            last_date=str(ha.index[-1].date()),
            interval=period,
            avg_volume=avg_volume,
            run_length=int(run_stats["run_length"]),
            run_percentile=float(run_stats["run_percentile"]),
        )

    except Exception as e:
        if debug:
            print(f"  DEBUG: Error processing {ticker}: {type(e).__name__}: {e}")
        return None


def _apply_filters(
    result: ScreenResult,
    color_filter: Literal["green", "red", "all"],
    changed_only: bool,
    min_volume: float | None,
    min_price: float | None,
    min_run_percentile: float | None,
    max_run_percentile: float | None,
) -> bool:
    """Check if a ScreenResult passes all filter criteria.

    Args:
        result: ScreenResult object to evaluate.
        color_filter: Filter by candle color ('green', 'red', or 'all').
        changed_only: If True, only pass results where color changed.
        min_volume: Minimum average volume threshold.
        min_price: Minimum price threshold.
        min_run_percentile: Minimum run percentile threshold (0-100).
        max_run_percentile: Maximum run percentile threshold (0-100).

    Returns:
        True if result passes all filters, False otherwise.
    """
    # Apply color filter
    if color_filter != "all" and result.color != color_filter:
        return False

    # Apply color change filter
    if changed_only and not result.color_changed:
        return False

    # Apply volume filter
    if min_volume is not None and result.avg_volume < min_volume:
        return False

    # Apply price filter
    if min_price is not None and result.ha_close < min_price:
        return False

    # Apply run percentile filters
    if min_run_percentile is not None and result.run_percentile < min_run_percentile:
        return False
    if max_run_percentile is not None and result.run_percentile > max_run_percentile:
        return False

    return True


def screen_nasdaq(
    color_filter: Literal["green", "red", "all"] = "all",
    period: str = "1d",
    limit: int | None = None,
    delay: float = 0.5,
    verbose: bool = True,
    changed_only: bool = False,
    lookback: str | None = None,
    start: str | None = None,
    end: str | None = None,
    debug: bool = False,
    min_volume: float | None = None,
    min_price: float | None = None,
    min_run_percentile: float | None = None,
    max_run_percentile: float | None = None,
    ticker_filter: list[str] | None = None,
    batch_size: int | None = 50,
) -> list[ScreenResult]:
    """Screen NASDAQ stocks for Heiken Ashi candle colors.

    Args:
        color_filter: Filter results by current candle color ('green', 'red', 'all').
        period: Aggregation period ('1d', '1wk', '1mo').
        limit: Maximum number of tickers to screen (for testing). None = all.
        delay: Delay in seconds between API calls. Only used when batch_size=None
            (sequential mode). Ignored when using batch downloads.
        verbose: Print progress messages.
        changed_only: If True, only return tickers where the candle color just changed.
        lookback: How far back to fetch ('1mo', '3mo', '6mo', '1y', '2y', '5y', etc.).
        start: Start date YYYY-MM-DD. Cannot be used with lookback.
        end: End date YYYY-MM-DD. Cannot be used with lookback.
        debug: When True, enables debug output in underlying ticker screening.
        min_volume: Minimum average daily volume (in shares).
        min_price: Minimum stock price (in dollars).
        min_run_percentile: Minimum run percentile (0-100). Find rare long runs.
        max_run_percentile: Maximum run percentile (0-100). Find common short runs.
        ticker_filter: Optional list of ticker symbols to screen instead of all NASDAQ.
        batch_size: Tickers per batch for parallel download (default: 50).
            Set to None for legacy sequential mode with delay.

    Returns:
        List of ScreenResult objects matching filters, sorted by ticker.
    """
    # Use provided ticker filter or fetch all NASDAQ tickers
    if ticker_filter is not None:
        tickers = ticker_filter
        if limit is not None:
            tickers = tickers[:limit]
    else:
        tickers = get_nasdaq_tickers(limit=limit)

    results: list[ScreenResult] = []

    change_msg = " that just changed color" if changed_only else ""
    filter_msg = " (filtered list)" if ticker_filter is not None else ""
    mode_msg = f"batch size {batch_size}" if batch_size else "sequential"

    if verbose:
        print(
            f"Screening {len(tickers)} tickers{filter_msg} for {color_filter} "
            f"Heiken Ashi candles{change_msg} ({period} period, {mode_msg})..."
        )
        print("-" * 70)

    # Use batch download mode if batch_size is specified
    if batch_size is not None and batch_size > 0:
        results = _screen_batch_mode(
            tickers=tickers,
            period=period,
            lookback=lookback,
            start=start,
            end=end,
            batch_size=batch_size,
            color_filter=color_filter,
            changed_only=changed_only,
            min_volume=min_volume,
            min_price=min_price,
            min_run_percentile=min_run_percentile,
            max_run_percentile=max_run_percentile,
            verbose=verbose,
            debug=debug,
        )
    else:
        # Legacy sequential mode
        results = _screen_sequential_mode(
            tickers=tickers,
            period=period,
            lookback=lookback,
            start=start,
            end=end,
            delay=delay,
            color_filter=color_filter,
            changed_only=changed_only,
            min_volume=min_volume,
            min_price=min_price,
            min_run_percentile=min_run_percentile,
            max_run_percentile=max_run_percentile,
            verbose=verbose,
            debug=debug,
        )

    if verbose:
        print("-" * 70)
        print(f"Screening complete: {len(results)} {color_filter} candles{change_msg} found")

    return sorted(results, key=lambda x: x.ticker)


def _screen_batch_mode(
    tickers: list[str],
    period: str,
    lookback: str | None,
    start: str | None,
    end: str | None,
    batch_size: int,
    color_filter: Literal["green", "red", "all"],
    changed_only: bool,
    min_volume: float | None,
    min_price: float | None,
    min_run_percentile: float | None,
    max_run_percentile: float | None,
    verbose: bool,
    debug: bool,
) -> list[ScreenResult]:
    """Screen tickers using batch download mode for faster processing.

    Args:
        tickers: List of ticker symbols to screen.
        period: Aggregation period ('1d', '1wk', '1mo').
        lookback: Relative period for history.
        start: Start date YYYY-MM-DD.
        end: End date YYYY-MM-DD.
        batch_size: Number of tickers to download per batch.
        color_filter: Filter by candle color.
        changed_only: Only return tickers where color changed.
        min_volume: Minimum average volume threshold.
        min_price: Minimum price threshold.
        min_run_percentile: Minimum run percentile threshold.
        max_run_percentile: Maximum run percentile threshold.
        verbose: Print progress messages.
        debug: Enable debug output.

    Returns:
        List of ScreenResult objects passing all filters.
    """
    results: list[ScreenResult] = []
    total_tickers = len(tickers)

    # Process in batches
    for batch_start in range(0, total_tickers, batch_size):
        batch_end = min(batch_start + batch_size, total_tickers)
        batch_tickers = tickers[batch_start:batch_end]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (total_tickers + batch_size - 1) // batch_size

        if verbose:
            print(
                f"Batch {batch_num}/{total_batches}: Downloading {len(batch_tickers)} tickers "
                f"({batch_start + 1}-{batch_end} of {total_tickers})..."
            )

        # Batch download all tickers in this chunk
        try:
            batch_data = fetch_ohlc_batch(
                batch_tickers,
                interval=period,
                lookback=lookback,
                start=start,
                end=end,
                threads=True,
                progress=False,
            )
        except Exception as e:
            if debug:
                print(f"  DEBUG: Batch download error: {type(e).__name__}: {e}")
            # Fall back to sequential for this batch
            for ticker in batch_tickers:
                result = screen_ticker(
                    ticker, period=period, lookback=lookback, start=start, end=end, debug=debug
                )
                if result is not None and _apply_filters(
                    result,
                    color_filter,
                    changed_only,
                    min_volume,
                    min_price,
                    min_run_percentile,
                    max_run_percentile,
                ):
                    results.append(result)
            continue

        # Process each downloaded DataFrame
        batch_matches = 0
        for ticker in batch_tickers:
            if ticker not in batch_data:
                continue

            df = batch_data[ticker]
            result = _process_ticker_dataframe(ticker, df, period, debug=debug)

            if result is not None and _apply_filters(
                result,
                color_filter,
                changed_only,
                min_volume,
                min_price,
                min_run_percentile,
                max_run_percentile,
            ):
                results.append(result)
                batch_matches += 1

        if verbose:
            print(
                f"  Batch {batch_num} complete: {len(batch_data)} downloaded, "
                f"{batch_matches} matches, {len(results)} total matches"
            )

    return results


def _screen_sequential_mode(
    tickers: list[str],
    period: str,
    lookback: str | None,
    start: str | None,
    end: str | None,
    delay: float,
    color_filter: Literal["green", "red", "all"],
    changed_only: bool,
    min_volume: float | None,
    min_price: float | None,
    min_run_percentile: float | None,
    max_run_percentile: float | None,
    verbose: bool,
    debug: bool,
) -> list[ScreenResult]:
    """Screen tickers using legacy sequential download mode.

    Args:
        tickers: List of ticker symbols to screen.
        period: Aggregation period ('1d', '1wk', '1mo').
        lookback: Relative period for history.
        start: Start date YYYY-MM-DD.
        end: End date YYYY-MM-DD.
        delay: Delay in seconds between API calls for rate limiting.
        color_filter: Filter by candle color.
        changed_only: Only return tickers where color changed.
        min_volume: Minimum average volume threshold.
        min_price: Minimum price threshold.
        min_run_percentile: Minimum run percentile threshold.
        max_run_percentile: Maximum run percentile threshold.
        verbose: Print progress messages.
        debug: Enable debug output.

    Returns:
        List of ScreenResult objects passing all filters.
    """
    results: list[ScreenResult] = []

    for i, ticker in enumerate(tickers, 1):
        if verbose and i % 10 == 0:
            print(
                f"Progress: {i}/{len(tickers)} tickers screened, "
                f"{len(results)} matches found..."
            )

        result = screen_ticker(
            ticker, period=period, lookback=lookback, start=start, end=end, debug=debug
        )

        if result is not None and _apply_filters(
            result,
            color_filter,
            changed_only,
            min_volume,
            min_price,
            min_run_percentile,
            max_run_percentile,
        ):
            results.append(result)

        # Rate limiting
        if delay > 0 and i < len(tickers):
            time.sleep(delay)

    return results


__all__ = ["screen_nasdaq", "screen_ticker", "get_candle_color", "ScreenResult"]
