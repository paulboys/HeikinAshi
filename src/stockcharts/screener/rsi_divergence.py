"""RSI Divergence screener for NASDAQ stocks.

Screens stocks for RSI divergences (bullish and bearish) with configurable
detection parameters, breakout filtering, and flexible pivot detection methods.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from stockcharts.data.fetch import fetch_ohlc, fetch_ohlc_batch
from stockcharts.indicators.divergence import (
    check_breakout_occurred,
    check_failed_breakout,
    detect_divergence,
)
from stockcharts.indicators.rsi import compute_rsi
from stockcharts.screener.nasdaq import get_nasdaq_tickers


@dataclass
class RSIDivergenceResult:
    """Result from RSI divergence screening.

    Attributes:
        ticker: Stock symbol.
        company_name: Company name from NASDAQ listing.
        close_price: Most recent close price.
        rsi: Current RSI value.
        divergence_type: Type detected ('bullish', 'bearish', or 'both').
        bullish_divergence: True if bullish divergence detected.
        bearish_divergence: True if bearish divergence detected.
        details: Human-readable description of divergence.
        bullish_indices: Tuple of (p1_idx, p2_idx, r1_idx, r2_idx) for bullish.
        bearish_indices: Tuple of (p1_idx, p2_idx, r1_idx, r2_idx) for bearish.
    """

    ticker: str
    company_name: str
    close_price: float
    rsi: float
    divergence_type: str  # 'bullish', 'bearish', or 'both'
    bullish_divergence: bool
    bearish_divergence: bool
    details: str
    bullish_indices: Optional[tuple] = None  # (p1_idx, p2_idx, r1_idx, r2_idx)
    bearish_indices: Optional[tuple] = None  # (p1_idx, p2_idx, r1_idx, r2_idx)


def screen_rsi_divergence(
    tickers: list[str] | None = None,
    period: str = "3mo",  # Historical lookback e.g. '3mo', '6mo', '1y'
    interval: str = "1d",  # Candle interval '1d','1wk','1mo'
    rsi_period: int = 14,
    divergence_type: str = "all",  # 'bullish', 'bearish', or 'all'
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_volume: Optional[float] = None,
    swing_window: int = 5,
    lookback: int = 60,
    start: Optional[str] = None,
    end: Optional[str] = None,
    exclude_breakouts: bool = False,
    breakout_threshold: float = 0.05,
    exclude_failed_breakouts: bool = False,
    failed_lookback_window: int = 10,
    failed_attempt_threshold: float = 0.03,
    failed_reversal_threshold: float = 0.01,
    min_swing_points: int = 2,
    index_proximity_factor: int = 2,
    sequence_tolerance_pct: float = 0.002,
    rsi_sequence_tolerance: float = 0.0,
    pivot_method: str = "swing",
    zigzag_pct: float = 0.03,
    zigzag_atr_mult: float = 2.0,
    zigzag_atr_period: int = 14,
    ema_price_span: int = 5,
    ema_rsi_span: int = 5,
    use_sequence_scoring: bool = False,
    min_sequence_score: float = 1.0,
    max_bar_gap: int = 10,
    min_magnitude_atr_mult: float = 0.5,
    atr_period: int = 14,
    batch_size: int | None = 50,
    verbose: bool = True,
) -> list[RSIDivergenceResult]:
    """Screen stocks for RSI divergences.

    Args:
        tickers: List of ticker symbols (if None, uses all NASDAQ)
        period: Historical period breadth for yfinance (e.g. '1mo', '3mo', '6mo', '1y') ignored if both start & end provided.
        interval: Candle aggregation interval ('1d','1wk','1mo').
        start: Start date for historical data (YYYY-MM-DD format).
        end: End date for historical data (YYYY-MM-DD format).
        rsi_period: RSI calculation period (default: 14)
        divergence_type: Type to screen for ('bullish', 'bearish', or 'all')
        min_price: Minimum stock price filter
        max_price: Maximum stock price filter
        min_volume: Minimum average daily volume filter
        swing_window: Window for swing point detection (default: 5)
        lookback: Bars to look back for divergence (default: 60)
        exclude_breakouts: If True, filter out divergences where breakout already occurred
        breakout_threshold: % move required to consider breakout complete (default: 0.05 = 5%)
        exclude_failed_breakouts: If True, filter out divergences with failed breakout attempts
        failed_lookback_window: Bars to check for failed breakout (default: 10)
        failed_attempt_threshold: % move to consider breakout "attempted" (default: 0.03 = 3%)
        failed_reversal_threshold: % from divergence to consider "failed" (default: 0.01 = 1%)
        min_swing_points: Minimum swing points required (2 or 3, default: 2)
        index_proximity_factor: Multiplier for swing_window to allow bar index gap (default: 2)
        sequence_tolerance_pct: Relative tolerance for 3-point price sequences (default: 0.002 = 0.2%)
        rsi_sequence_tolerance: Extra RSI tolerance in points for 3-point sequences (default: 0.0)
        pivot_method: Pivot detection method - 'swing' or 'ema-deriv' (default: 'swing')
        zigzag_pct: Percentage threshold for zigzag-pct method (default: 0.03 = 3%) [DEPRECATED]
        zigzag_atr_mult: ATR multiplier for zigzag-atr method (default: 2.0) [DEPRECATED]
        zigzag_atr_period: ATR period for zigzag-atr method (default: 14) [DEPRECATED]
        ema_price_span: EMA smoothing span for price when using ema-deriv (default: 5)
        ema_rsi_span: EMA smoothing span for RSI when using ema-deriv (default: 5)
        use_sequence_scoring: Enable ATR-normalized 3-point scoring (default: False)
        min_sequence_score: Minimum score to accept a 3-point sequence (default: 1.0)
        max_bar_gap: Max bar distance between price and RSI pivots for scoring (default: 10)
        min_magnitude_atr_mult: Min price move as ATR multiple for scoring (default: 0.5)
        atr_period: ATR period for magnitude filtering (default: 14)
        batch_size: Number of tickers to download per batch (default: 50).
            Uses yfinance's built-in threading for parallel downloads.
            Set to None for legacy sequential download mode.
        verbose: Print progress messages (default: True)

    Returns:
        List of RSIDivergenceResult objects
    """
    if tickers is None:
        if verbose:
            print("Fetching NASDAQ ticker list...")
        tickers = get_nasdaq_tickers()
        if verbose:
            print(f"Found {len(tickers)} tickers to screen")

    # Normalize tickers to list of strings
    ticker_list = []
    ticker_names = {}
    for ticker_info in tickers:
        if isinstance(ticker_info, tuple):
            ticker, company_name = ticker_info
            ticker_list.append(ticker)
            ticker_names[ticker] = company_name
        else:
            ticker = str(ticker_info)
            ticker_list.append(ticker)
            ticker_names[ticker] = ticker

    # Build divergence detection kwargs
    divergence_kwargs = {
        "price_col": "Close",
        "rsi_col": "RSI",
        "window": swing_window,
        "lookback": lookback,
        "min_swing_points": min_swing_points,
        "index_proximity_factor": index_proximity_factor,
        "sequence_tolerance_pct": sequence_tolerance_pct,
        "rsi_sequence_tolerance": rsi_sequence_tolerance,
        "pivot_method": pivot_method,
        "zigzag_pct": zigzag_pct,
        "zigzag_atr_mult": zigzag_atr_mult,
        "zigzag_atr_period": zigzag_atr_period,
        "ema_price_span": ema_price_span,
        "ema_rsi_span": ema_rsi_span,
        "use_sequence_scoring": use_sequence_scoring,
        "min_sequence_score": min_sequence_score,
        "max_bar_gap": max_bar_gap,
        "min_magnitude_atr_mult": min_magnitude_atr_mult,
        "atr_period": atr_period,
    }

    # Use batch or sequential mode
    if batch_size is not None and batch_size > 0:
        results = _screen_batch_mode(
            ticker_list=ticker_list,
            ticker_names=ticker_names,
            interval=interval,
            period=period,
            start=start,
            end=end,
            rsi_period=rsi_period,
            divergence_type=divergence_type,
            min_price=min_price,
            max_price=max_price,
            min_volume=min_volume,
            exclude_breakouts=exclude_breakouts,
            breakout_threshold=breakout_threshold,
            exclude_failed_breakouts=exclude_failed_breakouts,
            failed_lookback_window=failed_lookback_window,
            failed_attempt_threshold=failed_attempt_threshold,
            failed_reversal_threshold=failed_reversal_threshold,
            divergence_kwargs=divergence_kwargs,
            batch_size=batch_size,
            verbose=verbose,
        )
    else:
        results = _screen_sequential_mode(
            ticker_list=ticker_list,
            ticker_names=ticker_names,
            interval=interval,
            period=period,
            start=start,
            end=end,
            rsi_period=rsi_period,
            divergence_type=divergence_type,
            min_price=min_price,
            max_price=max_price,
            min_volume=min_volume,
            exclude_breakouts=exclude_breakouts,
            breakout_threshold=breakout_threshold,
            exclude_failed_breakouts=exclude_failed_breakouts,
            failed_lookback_window=failed_lookback_window,
            failed_attempt_threshold=failed_attempt_threshold,
            failed_reversal_threshold=failed_reversal_threshold,
            divergence_kwargs=divergence_kwargs,
            verbose=verbose,
        )

    if verbose:
        print(f"\nScreening complete. Found {len(results)} stocks with divergences.")
    return results


def _process_ticker_divergence(
    ticker: str,
    company_name: str,
    df: pd.DataFrame,
    rsi_period: int,
    divergence_type: str,
    min_price: Optional[float],
    max_price: Optional[float],
    min_volume: Optional[float],
    exclude_breakouts: bool,
    breakout_threshold: float,
    exclude_failed_breakouts: bool,
    failed_lookback_window: int,
    failed_attempt_threshold: float,
    failed_reversal_threshold: float,
    divergence_kwargs: dict,
) -> Optional[RSIDivergenceResult]:
    """Process a single ticker's DataFrame for RSI divergence.

    Returns RSIDivergenceResult if divergence found, None otherwise.
    """
    swing_window = divergence_kwargs.get("window", 5)

    if df is None or len(df) < rsi_period + swing_window:
        return None

    # Get current price
    close_price = df["Close"].iloc[-1]

    # Apply price filters
    if min_price is not None and close_price < min_price:
        return None
    if max_price is not None and close_price > max_price:
        return None

    # Apply volume filter
    if min_volume is not None:
        if "Volume" in df.columns:
            avg_volume = df["Volume"].mean()
            if avg_volume < min_volume:
                return None

    # Calculate RSI
    df = df.copy()
    df["RSI"] = compute_rsi(df["Close"], period=rsi_period)

    if df["RSI"].isna().all():
        return None

    current_rsi = df["RSI"].iloc[-1]

    # Detect divergences
    div_result = detect_divergence(df, **divergence_kwargs)

    # Filter by divergence type
    include = False
    div_type = []
    details = []

    if divergence_type in ["bullish", "all"] and div_result["bullish"]:
        skip_bullish = False

        if exclude_breakouts and div_result["bullish_indices"]:
            indices = div_result["bullish_indices"]
            last_price_idx = indices[2] if len(indices) == 6 else indices[1]
            if check_breakout_occurred(df, last_price_idx, "bullish", breakout_threshold):
                skip_bullish = True

        if not skip_bullish and exclude_failed_breakouts and div_result["bullish_indices"]:
            indices = div_result["bullish_indices"]
            last_price_idx = indices[2] if len(indices) == 6 else indices[1]
            if check_failed_breakout(
                df,
                last_price_idx,
                "bullish",
                failed_lookback_window,
                failed_attempt_threshold,
                failed_reversal_threshold,
            ):
                skip_bullish = True

        if not skip_bullish:
            include = True
            div_type.append("bullish")
            details.append(f"BULLISH: {div_result['bullish_details']}")

    if divergence_type in ["bearish", "all"] and div_result["bearish"]:
        skip_bearish = False

        if exclude_breakouts and div_result["bearish_indices"]:
            indices = div_result["bearish_indices"]
            last_price_idx = indices[2] if len(indices) == 6 else indices[1]
            if check_breakout_occurred(df, last_price_idx, "bearish", breakout_threshold):
                skip_bearish = True

        if not skip_bearish and exclude_failed_breakouts and div_result["bearish_indices"]:
            indices = div_result["bearish_indices"]
            last_price_idx = indices[2] if len(indices) == 6 else indices[1]
            if check_failed_breakout(
                df,
                last_price_idx,
                "bearish",
                failed_lookback_window,
                failed_attempt_threshold,
                failed_reversal_threshold,
            ):
                skip_bearish = True

        if not skip_bearish:
            include = True
            div_type.append("bearish")
            details.append(f"BEARISH: {div_result['bearish_details']}")

    if include:
        return RSIDivergenceResult(
            ticker=ticker,
            company_name=company_name,
            close_price=close_price,
            rsi=current_rsi,
            divergence_type=" & ".join(div_type),
            bullish_divergence=div_result["bullish"],
            bearish_divergence=div_result["bearish"],
            details=" | ".join(details),
            bullish_indices=div_result["bullish_indices"],
            bearish_indices=div_result["bearish_indices"],
        )

    return None


def _screen_batch_mode(
    ticker_list: list[str],
    ticker_names: dict[str, str],
    interval: str,
    period: str,
    start: Optional[str],
    end: Optional[str],
    rsi_period: int,
    divergence_type: str,
    min_price: Optional[float],
    max_price: Optional[float],
    min_volume: Optional[float],
    exclude_breakouts: bool,
    breakout_threshold: float,
    exclude_failed_breakouts: bool,
    failed_lookback_window: int,
    failed_attempt_threshold: float,
    failed_reversal_threshold: float,
    divergence_kwargs: dict,
    batch_size: int,
    verbose: bool,
) -> list[RSIDivergenceResult]:
    """Screen tickers using batch download mode for faster processing.

    Args:
        ticker_list: List of ticker symbols to screen.
        ticker_names: Mapping of ticker to company name.
        interval: Candle aggregation interval ('1d', '1wk', '1mo').
        period: Historical lookback period.
        start: Start date YYYY-MM-DD.
        end: End date YYYY-MM-DD.
        rsi_period: RSI calculation period.
        divergence_type: Type to screen for ('bullish', 'bearish', 'all').
        min_price: Minimum price filter.
        max_price: Maximum price filter.
        min_volume: Minimum volume filter.
        exclude_breakouts: Filter out completed breakouts.
        breakout_threshold: Percentage move for breakout detection.
        exclude_failed_breakouts: Filter out failed breakout attempts.
        failed_lookback_window: Bars to check for failed breakout.
        failed_attempt_threshold: Percentage for attempted breakout.
        failed_reversal_threshold: Percentage for failed reversal.
        divergence_kwargs: Additional kwargs for detect_divergence.
        batch_size: Tickers per batch download.
        verbose: Print progress messages.

    Returns:
        List of RSIDivergenceResult objects passing all filters.
    """
    results: list[RSIDivergenceResult] = []
    total_tickers = len(ticker_list)

    for batch_start in range(0, total_tickers, batch_size):
        batch_end = min(batch_start + batch_size, total_tickers)
        batch_tickers = ticker_list[batch_start:batch_end]
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
                interval=interval,
                lookback=period if not (start and end) else None,
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
                        lookback=period if not (start and end) else None,
                        start=start,
                        end=end,
                    )
                    result = _process_ticker_divergence(
                        ticker=ticker,
                        company_name=ticker_names.get(ticker, ticker),
                        df=df,
                        rsi_period=rsi_period,
                        divergence_type=divergence_type,
                        min_price=min_price,
                        max_price=max_price,
                        min_volume=min_volume,
                        exclude_breakouts=exclude_breakouts,
                        breakout_threshold=breakout_threshold,
                        exclude_failed_breakouts=exclude_failed_breakouts,
                        failed_lookback_window=failed_lookback_window,
                        failed_attempt_threshold=failed_attempt_threshold,
                        failed_reversal_threshold=failed_reversal_threshold,
                        divergence_kwargs=divergence_kwargs,
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
            try:
                result = _process_ticker_divergence(
                    ticker=ticker,
                    company_name=ticker_names.get(ticker, ticker),
                    df=df,
                    rsi_period=rsi_period,
                    divergence_type=divergence_type,
                    min_price=min_price,
                    max_price=max_price,
                    min_volume=min_volume,
                    exclude_breakouts=exclude_breakouts,
                    breakout_threshold=breakout_threshold,
                    exclude_failed_breakouts=exclude_failed_breakouts,
                    failed_lookback_window=failed_lookback_window,
                    failed_attempt_threshold=failed_attempt_threshold,
                    failed_reversal_threshold=failed_reversal_threshold,
                    divergence_kwargs=divergence_kwargs,
                )
                if result:
                    results.append(result)
                    batch_matches += 1
            except Exception:
                pass

        if verbose:
            print(
                f"  Batch {batch_num} complete: {len(batch_data)} downloaded, "
                f"{batch_matches} matches, {len(results)} total matches"
            )

    return results


def _screen_sequential_mode(
    ticker_list: list[str],
    ticker_names: dict[str, str],
    interval: str,
    period: str,
    start: Optional[str],
    end: Optional[str],
    rsi_period: int,
    divergence_type: str,
    min_price: Optional[float],
    max_price: Optional[float],
    min_volume: Optional[float],
    exclude_breakouts: bool,
    breakout_threshold: float,
    exclude_failed_breakouts: bool,
    failed_lookback_window: int,
    failed_attempt_threshold: float,
    failed_reversal_threshold: float,
    divergence_kwargs: dict,
    verbose: bool,
) -> list[RSIDivergenceResult]:
    """Screen tickers using legacy sequential download mode.

    Args:
        ticker_list: List of ticker symbols to screen.
        ticker_names: Mapping of ticker to company name.
        interval: Candle aggregation interval ('1d', '1wk', '1mo').
        period: Historical lookback period.
        start: Start date YYYY-MM-DD.
        end: End date YYYY-MM-DD.
        rsi_period: RSI calculation period.
        divergence_type: Type to screen for ('bullish', 'bearish', 'all').
        min_price: Minimum price filter.
        max_price: Maximum price filter.
        min_volume: Minimum volume filter.
        exclude_breakouts: Filter out completed breakouts.
        breakout_threshold: Percentage move for breakout detection.
        exclude_failed_breakouts: Filter out failed breakout attempts.
        failed_lookback_window: Bars to check for failed breakout.
        failed_attempt_threshold: Percentage for attempted breakout.
        failed_reversal_threshold: Percentage for failed reversal.
        divergence_kwargs: Additional kwargs for detect_divergence.
        verbose: Print progress messages.

    Returns:
        List of RSIDivergenceResult objects passing all filters.
    """
    results: list[RSIDivergenceResult] = []
    total = len(ticker_list)

    for i, ticker in enumerate(ticker_list, 1):
        company_name = ticker_names.get(ticker, ticker)

        if verbose:
            print(f"[{i}/{total}] Screening {ticker}...", end="\r")

        try:
            df = fetch_ohlc(
                ticker,
                interval=interval,
                lookback=period if not (start and end) else None,
                start=start,
                end=end,
            )

            result = _process_ticker_divergence(
                ticker=ticker,
                company_name=company_name,
                df=df,
                rsi_period=rsi_period,
                divergence_type=divergence_type,
                min_price=min_price,
                max_price=max_price,
                min_volume=min_volume,
                exclude_breakouts=exclude_breakouts,
                breakout_threshold=breakout_threshold,
                exclude_failed_breakouts=exclude_failed_breakouts,
                failed_lookback_window=failed_lookback_window,
                failed_attempt_threshold=failed_attempt_threshold,
                failed_reversal_threshold=failed_reversal_threshold,
                divergence_kwargs=divergence_kwargs,
            )
            if result:
                results.append(result)

        except Exception:
            pass

    return results


def save_results_to_csv(
    results: list[RSIDivergenceResult], filename: str = "rsi_divergence_results.csv"
) -> None:
    """Save screening results to CSV file.

    Args:
        results: List of RSIDivergenceResult objects to save.
        filename: Output CSV file path.

    Returns:
        None. Prints status message and writes file to disk.
    """
    if not results:
        print("No results to save.")
        return

    import json

    def serialize_indices(indices: list | tuple | None) -> list[str] | None:
        """Convert timestamp indices to ISO format strings for JSON serialization.

        Args:
            indices: Tuple of timestamp indices or None.

        Returns:
            List of ISO format date strings or None.
        """
        if indices is None:
            return None
        return [idx.isoformat() for idx in indices]

    df = pd.DataFrame(
        [
            {
                "Ticker": r.ticker,
                "Company": r.company_name,
                "Price": r.close_price,
                "RSI": r.rsi,
                "Divergence Type": r.divergence_type,
                "Bullish": r.bullish_divergence,
                "Bearish": r.bearish_divergence,
                "Details": r.details,
                "Bullish_Indices": (
                    json.dumps(serialize_indices(r.bullish_indices)) if r.bullish_indices else ""
                ),
                "Bearish_Indices": (
                    json.dumps(serialize_indices(r.bearish_indices)) if r.bearish_indices else ""
                ),
            }
            for r in results
        ]
    )

    df.to_csv(filename, index=False)
    print(f"Results saved to {filename}")
