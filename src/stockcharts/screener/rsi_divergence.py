"""RSI Divergence screener for NASDAQ stocks."""

import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.screener.nasdaq import get_nasdaq_tickers
from stockcharts.indicators.rsi import compute_rsi
from stockcharts.indicators.divergence import detect_divergence


@dataclass
class RSIDivergenceResult:
    """Result from RSI divergence screening."""
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
    tickers: Optional[List[str]] = None,
    period: str = '3mo',  # Historical lookback e.g. '3mo', '6mo', '1y'
    interval: str = '1d',  # Candle interval '1d','1wk','1mo'
    rsi_period: int = 14,
    divergence_type: str = 'all',  # 'bullish', 'bearish', or 'all'
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_volume: Optional[float] = None,
    swing_window: int = 5,
    lookback: int = 60,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[RSIDivergenceResult]:
    """
    Screen stocks for RSI divergences.
    
    Args:
        tickers: List of ticker symbols (if None, uses all NASDAQ)
    period: Historical period breadth for yfinance (e.g. '1mo', '3mo', '6mo', '1y') ignored if both start & end provided.
    interval: Candle aggregation interval ('1d','1wk','1mo').
        rsi_period: RSI calculation period (default: 14)
        divergence_type: Type to screen for ('bullish', 'bearish', or 'all')
        min_price: Minimum stock price filter
        max_price: Maximum stock price filter
        min_volume: Minimum average daily volume filter
        swing_window: Window for swing point detection (default: 5)
        lookback: Bars to look back for divergence (default: 60)
    
    Returns:
        List of RSIDivergenceResult objects
    """
    if tickers is None:
        print("Fetching NASDAQ ticker list...")
        tickers = get_nasdaq_tickers()
        print(f"Found {len(tickers)} tickers to screen")
    
    results = []
    total = len(tickers)
    
    for i, ticker_info in enumerate(tickers, 1):
        if isinstance(ticker_info, tuple):
            ticker, company_name = ticker_info
        else:
            ticker = ticker_info
            company_name = ticker
        
        print(f"[{i}/{total}] Screening {ticker}...", end='\r')
        
        try:
            # Fetch OHLC data using updated fetch_ohlc API
            df = fetch_ohlc(
                ticker,
                interval=interval,
                lookback=period if not (start and end) else None,
                start=start,
                end=end,
            )
            
            if df is None or len(df) < rsi_period + swing_window:
                continue
            
            # Get current price
            close_price = df['Close'].iloc[-1]
            
            # Apply price filters
            if min_price is not None and close_price < min_price:
                continue
            if max_price is not None and close_price > max_price:
                continue
            
            # Apply volume filter
            if min_volume is not None:
                if 'Volume' in df.columns:
                    avg_volume = df['Volume'].mean()
                    if avg_volume < min_volume:
                        continue
            
            # Calculate RSI
            df['RSI'] = compute_rsi(df['Close'], period=rsi_period)
            
            if df['RSI'].isna().all():
                continue
            
            current_rsi = df['RSI'].iloc[-1]
            
            # Detect divergences
            div_result = detect_divergence(
                df,
                price_col='Close',
                rsi_col='RSI',
                window=swing_window,
                lookback=lookback
            )
            
            # Filter by divergence type
            include = False
            div_type = []
            details = []
            
            if divergence_type in ['bullish', 'all'] and div_result['bullish']:
                include = True
                div_type.append('bullish')
                details.append(f"BULLISH: {div_result['bullish_details']}")
            
            if divergence_type in ['bearish', 'all'] and div_result['bearish']:
                include = True
                div_type.append('bearish')
                details.append(f"BEARISH: {div_result['bearish_details']}")
            
            if include:
                results.append(RSIDivergenceResult(
                    ticker=ticker,
                    company_name=company_name,
                    close_price=close_price,
                    rsi=current_rsi,
                    divergence_type=' & '.join(div_type),
                    bullish_divergence=div_result['bullish'],
                    bearish_divergence=div_result['bearish'],
                    details=' | '.join(details),
                    bullish_indices=div_result['bullish_indices'],
                    bearish_indices=div_result['bearish_indices']
                ))
        
        except Exception as e:
            # Silently skip errors for individual tickers
            pass
    
    print(f"\nScreening complete. Found {len(results)} stocks with divergences.")
    return results


def save_results_to_csv(results: List[RSIDivergenceResult], filename: str = 'rsi_divergence_results.csv'):
    """Save screening results to CSV file."""
    if not results:
        print("No results to save.")
        return
    
    import json
    
    def serialize_indices(indices):
        """Convert timestamp indices to ISO format strings for JSON serialization."""
        if indices is None:
            return None
        return [idx.isoformat() for idx in indices]
    
    df = pd.DataFrame([
        {
            'Ticker': r.ticker,
            'Company': r.company_name,
            'Price': r.close_price,
            'RSI': r.rsi,
            'Divergence Type': r.divergence_type,
            'Bullish': r.bullish_divergence,
            'Bearish': r.bearish_divergence,
            'Details': r.details,
            'Bullish_Indices': json.dumps(serialize_indices(r.bullish_indices)) if r.bullish_indices else '',
            'Bearish_Indices': json.dumps(serialize_indices(r.bearish_indices)) if r.bearish_indices else ''
        }
        for r in results
    ])
    
    df.to_csv(filename, index=False)
    print(f"Results saved to {filename}")
