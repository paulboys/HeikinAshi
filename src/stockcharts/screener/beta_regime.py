"""Beta regime screener for NASDAQ stocks.

Screens stocks for risk-on/risk-off regime based on Mike McGlone's methodology:
- Relative strength ratio vs benchmark (e.g., SPY)
- Ratio compared to its 200-day (or 40-week) moving average
- Above MA = risk-on, Below MA = risk-off
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from stockcharts.data.fetch import fetch_ohlc, fetch_ohlc_batch
from stockcharts.indicators.beta import analyze_beta_regime
from stockcharts.screener.nasdaq import get_nasdaq_tickers


@dataclass
class BetaRegimeResult:
    """Result from beta regime screening.

    Attributes:
        ticker: Stock symbol.
        company_name: Full company name or ticker if unavailable.
        benchmark: Benchmark ticker used for comparison.
        regime: Current regime status ("risk-on", "risk-off", or "insufficient-data").
        relative_strength: Asset price / benchmark price ratio.
        ma_value: Moving average of relative strength ratio.
        pct_from_ma: Percentage distance from moving average.
        beta: Rolling beta coefficient vs benchmark.
        beta_percentile: Percentile rank (0-100) of current beta in history.
            High percentile (90+) = beta historically elevated.
            Low percentile (<25) = beta historically low.
        close_price: Current asset closing price.
        benchmark_price: Current benchmark closing price.
        interval: Candle interval used ("1d", "1wk", "1mo").
        ma_period: Moving average period used for regime detection.
    """

    ticker: str
    company_name: str
    benchmark: str
    regime: Literal["risk-on", "risk-off", "insufficient-data"]
    relative_strength: float
    ma_value: float
    pct_from_ma: float
    beta: float
    beta_percentile: float
    close_price: float
    benchmark_price: float
    interval: str
    ma_period: int


def screen_beta_regime(
    tickers: list[str] | None = None,
    benchmark: str = "SPY",
    interval: str = "1d",
    ma_period: int = 200,
    beta_window: int = 60,
    regime_filter: Literal["risk-on", "risk-off", "all"] = "all",
    min_price: float | None = None,
    max_price: float | None = None,
    min_volume: float | None = None,
    lookback: str | None = None,
    start: str | None = None,
    end: str | None = None,
    batch_size: int | None = 50,
    verbose: bool = True,
) -> list[BetaRegimeResult]:
    """Screen stocks for beta regime status.

    Args:
        tickers: List of ticker symbols (if None, uses all NASDAQ).
        benchmark: Benchmark ticker for comparison (default: "SPY").
            Can be any valid yfinance ticker (SPY, QQQ, BTC-USD, etc.).
        interval: Candle interval - "1d", "1wk", "1mo" (default: "1d").
        ma_period: Moving average period for regime detection.
            Default: 200 for daily, auto-adjusts to 40 for weekly if 200 is passed.
        beta_window: Rolling window for beta calculation (default: 60).
        regime_filter: Filter results by regime - "risk-on", "risk-off", or "all".
        min_price: Minimum stock price filter.
        max_price: Maximum stock price filter.
        min_volume: Minimum average daily volume filter.
        lookback: Historical period (e.g., "1y", "2y", "5y"). Should be longer
            than ma_period to ensure sufficient data.
        start: Start date YYYY-MM-DD (overrides lookback if end also provided).
        end: End date YYYY-MM-DD.
        batch_size: Tickers per batch for parallel download (default: 50).
            Set to None for sequential mode.
        verbose: Print progress messages (default: True).

    Returns:
        List of BetaRegimeResult objects.
    """
    # Auto-adjust MA period for weekly interval
    effective_ma_period = ma_period
    if interval == "1wk" and ma_period == 200:
        effective_ma_period = 40  # 40 weeks ≈ 200 days
        if verbose:
            print(f"Auto-adjusted MA period to {effective_ma_period} for weekly interval")

    # Auto-set lookback if not specified
    if lookback is None and start is None:
        # Need enough history for MA calculation + buffer
        if interval == "1d":
            lookback = "2y" if effective_ma_period <= 200 else "5y"
        elif interval == "1wk":
            lookback = "3y" if effective_ma_period <= 52 else "5y"
        else:
            lookback = "5y"

    # Get ticker list
    if tickers is None:
        if verbose:
            print("Fetching NASDAQ ticker list...")
        tickers = get_nasdaq_tickers()
        if verbose:
            print(f"Found {len(tickers)} tickers to screen")

    # Fetch benchmark data first
    if verbose:
        print(f"Fetching benchmark data ({benchmark})...")

    try:
        benchmark_df = fetch_ohlc(
            benchmark,
            interval=interval,
            lookback=lookback if not (start and end) else None,
            start=start,
            end=end,
        )
    except Exception as e:
        if verbose:
            print(f"Error fetching benchmark {benchmark}: {e}")
        return []

    if benchmark_df is None or benchmark_df.empty:
        if verbose:
            print(f"No data for benchmark {benchmark}")
        return []

    # Validate sufficient bars for MA calculation
    bars_available = len(benchmark_df)
    min_recommended = int(effective_ma_period * 1.5)  # 50% buffer for meaningful trend
    if bars_available < effective_ma_period:
        if verbose:
            print(
                f"⚠️  WARNING: Only {bars_available} bars available, but MA period is "
                f"{effective_ma_period}. No regime signals possible."
            )
            print("    Increase --period (e.g., 5y, 10y) or reduce --ma-period")
        return []
    elif bars_available < min_recommended:
        if verbose:
            print(
                f"⚠️  WARNING: Only {bars_available} bars for {effective_ma_period}-period MA. "
                f"Recommend {min_recommended}+ bars for reliable regime detection."
            )
            print("    Consider using --period 5y or --period 10y for better accuracy.")

    if verbose:
        print(f"Benchmark {benchmark}: {len(benchmark_df)} bars loaded")
        mode_msg = f"batch size {batch_size}" if batch_size else "sequential"
        print(f"Screening {len(tickers)} tickers ({mode_msg})...")
        print("-" * 70)

    # Screen tickers
    if batch_size is not None and batch_size > 0:
        results = _screen_batch_mode(
            tickers=tickers,
            benchmark=benchmark,
            benchmark_df=benchmark_df,
            interval=interval,
            lookback=lookback,
            start=start,
            end=end,
            effective_ma_period=effective_ma_period,
            beta_window=beta_window,
            regime_filter=regime_filter,
            min_price=min_price,
            max_price=max_price,
            min_volume=min_volume,
            batch_size=batch_size,
            verbose=verbose,
        )
    else:
        results = _screen_sequential_mode(
            tickers=tickers,
            benchmark=benchmark,
            benchmark_df=benchmark_df,
            interval=interval,
            lookback=lookback,
            start=start,
            end=end,
            effective_ma_period=effective_ma_period,
            beta_window=beta_window,
            regime_filter=regime_filter,
            min_price=min_price,
            max_price=max_price,
            min_volume=min_volume,
            verbose=verbose,
        )

    if verbose:
        print("-" * 70)
        print(f"Screening complete. Found {len(results)} stocks matching criteria.")

    return sorted(results, key=lambda x: x.ticker)


def _process_ticker_beta(
    ticker: str,
    df: pd.DataFrame,
    benchmark: str,
    benchmark_df: pd.DataFrame,
    interval: str,
    effective_ma_period: int,
    beta_window: int,
    regime_filter: str,
    min_price: float | None,
    max_price: float | None,
    min_volume: float | None,
    company_name: str = "",
) -> BetaRegimeResult | None:
    """Process a single ticker for beta regime analysis.

    Applies price/volume filters and computes beta regime metrics.

    Args:
        ticker: Stock symbol.
        df: OHLC DataFrame for the asset.
        benchmark: Benchmark ticker symbol.
        benchmark_df: OHLC DataFrame for the benchmark.
        interval: Candle interval used.
        effective_ma_period: Moving average period (adjusted for interval).
        beta_window: Rolling window for beta calculation.
        regime_filter: Filter by regime ("risk-on", "risk-off", or "all").
        min_price: Minimum stock price filter (None to skip).
        max_price: Maximum stock price filter (None to skip).
        min_volume: Minimum average volume filter (None to skip).
        company_name: Company name for result display.

    Returns:
        BetaRegimeResult if ticker passes filters and has valid data,
        None otherwise.
    """
    if df is None or df.empty:
        return None

    # Check minimum data requirement
    if len(df) < effective_ma_period:
        return None

    # Apply price filter
    current_price = df["Close"].iloc[-1]
    if min_price is not None and current_price < min_price:
        return None
    if max_price is not None and current_price > max_price:
        return None

    # Apply volume filter
    if min_volume is not None and "Volume" in df.columns:
        avg_volume = df["Volume"].mean()
        if avg_volume < min_volume:
            return None

    try:
        # Analyze beta regime
        analysis = analyze_beta_regime(
            asset_df=df,
            benchmark_df=benchmark_df,
            ma_period=effective_ma_period,
            beta_window=beta_window,
        )

        regime = analysis["regime"]

        # Apply regime filter
        if regime_filter != "all" and regime != regime_filter:
            return None

        return BetaRegimeResult(
            ticker=ticker,
            company_name=company_name,
            benchmark=benchmark,
            regime=regime,
            relative_strength=float(analysis["relative_strength"]),
            ma_value=float(analysis["rs_ma"]),
            pct_from_ma=float(analysis["pct_from_ma"]),
            beta=float(analysis["rolling_beta"]),
            beta_percentile=float(analysis["beta_percentile"]),
            close_price=float(analysis["asset_price"]),
            benchmark_price=float(analysis["benchmark_price"]),
            interval=interval,
            ma_period=effective_ma_period,
        )
    except Exception:
        return None


def _screen_batch_mode(
    tickers: list[str],
    benchmark: str,
    benchmark_df: pd.DataFrame,
    interval: str,
    lookback: str | None,
    start: str | None,
    end: str | None,
    effective_ma_period: int,
    beta_window: int,
    regime_filter: str,
    min_price: float | None,
    max_price: float | None,
    min_volume: float | None,
    batch_size: int,
    verbose: bool,
) -> list[BetaRegimeResult]:
    """Screen tickers using batch download mode for faster processing.

    Downloads tickers in parallel batches using yfinance threading,
    then processes each for beta regime analysis.

    Args:
        tickers: List of ticker symbols to screen.
        benchmark: Benchmark ticker symbol.
        benchmark_df: Pre-fetched benchmark OHLC data.
        interval: Candle interval ("1d", "1wk", "1mo").
        lookback: Historical period for data fetch.
        start: Start date (overrides lookback if end also provided).
        end: End date.
        effective_ma_period: Moving average period (adjusted for interval).
        beta_window: Rolling window for beta calculation.
        regime_filter: Filter by regime status.
        min_price: Minimum price filter.
        max_price: Maximum price filter.
        min_volume: Minimum volume filter.
        batch_size: Number of tickers per batch.
        verbose: Print progress messages.

    Returns:
        List of BetaRegimeResult objects matching filters.
    """
    results: list[BetaRegimeResult] = []
    total_tickers = len(tickers)

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

        try:
            batch_data = fetch_ohlc_batch(
                batch_tickers,
                interval=interval,
                lookback=lookback if not (start and end) else None,
                start=start,
                end=end,
                threads=True,
                progress=False,
            )
        except Exception as e:
            if verbose:
                print(f"  Batch download error: {e}, falling back to sequential...")
            # Fall back to sequential for this batch
            for ticker in batch_tickers:
                try:
                    df = fetch_ohlc(
                        ticker,
                        interval=interval,
                        lookback=lookback if not (start and end) else None,
                        start=start,
                        end=end,
                    )
                    result = _process_ticker_beta(
                        ticker,
                        df,
                        benchmark,
                        benchmark_df,
                        interval,
                        effective_ma_period,
                        beta_window,
                        regime_filter,
                        min_price,
                        max_price,
                        min_volume,
                        company_name=ticker,
                    )
                    if result:
                        results.append(result)
                except Exception:
                    pass
            continue

        # Process each downloaded DataFrame
        batch_matches = 0
        for ticker in batch_tickers:
            if ticker not in batch_data:
                continue

            df = batch_data[ticker]
            result = _process_ticker_beta(
                ticker,
                df,
                benchmark,
                benchmark_df,
                interval,
                effective_ma_period,
                beta_window,
                regime_filter,
                min_price,
                max_price,
                min_volume,
                company_name=ticker,
            )
            if result:
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
    benchmark: str,
    benchmark_df: pd.DataFrame,
    interval: str,
    lookback: str | None,
    start: str | None,
    end: str | None,
    effective_ma_period: int,
    beta_window: int,
    regime_filter: str,
    min_price: float | None,
    max_price: float | None,
    min_volume: float | None,
    verbose: bool,
) -> list[BetaRegimeResult]:
    """Screen tickers using legacy sequential download mode.

    Downloads and processes tickers one at a time. Slower than batch mode
    but useful for debugging or when batch downloads fail.

    Args:
        tickers: List of ticker symbols to screen.
        benchmark: Benchmark ticker symbol.
        benchmark_df: Pre-fetched benchmark OHLC data.
        interval: Candle interval ("1d", "1wk", "1mo").
        lookback: Historical period for data fetch.
        start: Start date (overrides lookback if end also provided).
        end: End date.
        effective_ma_period: Moving average period (adjusted for interval).
        beta_window: Rolling window for beta calculation.
        regime_filter: Filter by regime status.
        min_price: Minimum price filter.
        max_price: Maximum price filter.
        min_volume: Minimum volume filter.
        verbose: Print progress messages.

    Returns:
        List of BetaRegimeResult objects matching filters.
    """
    results: list[BetaRegimeResult] = []
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        if verbose:
            print(f"[{i}/{total}] Screening {ticker}...", end="\r")

        try:
            df = fetch_ohlc(
                ticker,
                interval=interval,
                lookback=lookback if not (start and end) else None,
                start=start,
                end=end,
            )

            result = _process_ticker_beta(
                ticker,
                df,
                benchmark,
                benchmark_df,
                interval,
                effective_ma_period,
                beta_window,
                regime_filter,
                min_price,
                max_price,
                min_volume,
                company_name=ticker,
            )
            if result:
                results.append(result)

        except Exception:
            pass

    return results


def save_results_to_csv(
    results: list[BetaRegimeResult],
    filename: str = "beta_regime_results.csv",
) -> None:
    """Save screening results to CSV file.

    Args:
        results: List of BetaRegimeResult objects to save.
        filename: Output CSV file path.

    Returns:
        None. Prints status message and writes file to disk.
    """
    if not results:
        print("No results to save.")
        return

    df = pd.DataFrame(
        [
            {
                "Ticker": r.ticker,
                "Company_Name": r.company_name,
                "Benchmark": r.benchmark,
                "Regime": r.regime,
                "Relative_Strength": r.relative_strength,
                "MA_Value": r.ma_value,
                "Pct_From_MA": r.pct_from_ma,
                "Beta": r.beta,
                "Beta_Percentile": r.beta_percentile,
                "Close_Price": r.close_price,
                "Benchmark_Price": r.benchmark_price,
                "Interval": r.interval,
                "MA_Period": r.ma_period,
            }
            for r in results
        ]
    )

    df.to_csv(filename, index=False)
    print(f"Results saved to {filename}")


__all__ = ["screen_beta_regime", "save_results_to_csv", "BetaRegimeResult"]
