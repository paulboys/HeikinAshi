"""Alternative pivot extraction methods for divergence detection."""

from typing import Dict

import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    """Calculate exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def ema_derivative_pivots(
    df: pd.DataFrame,
    price_col: str = "Close",
    rsi_col: str = "RSI",
    price_span: int = 5,
    rsi_span: int = 5,
) -> Dict:
    """
    Detect pivot highs/lows using sign changes in first derivative of EMA-smoothed series.

    This method smooths the price and RSI with EMA, then detects where the slope (derivative)
    changes sign. More robust than window-based methods for noisy data.

    Pivot Detection Logic:
    - Pivot Low: derivative transitions from negative to positive (valley)
    - Pivot High: derivative transitions from positive to negative (peak)

    Args:
        df: DataFrame with price and RSI data
        price_col: Column name for price (default: 'Close')
        rsi_col: Column name for RSI (default: 'RSI')
        price_span: EMA smoothing span for price (default: 5)
        rsi_span: EMA smoothing span for RSI (default: 5)

    Returns:
        Dict with keys: 'price_highs', 'price_lows', 'rsi_highs', 'rsi_lows', 'meta'
        Each contains a list/Index of timestamps where pivots occur.

    Example:
        # Use 7-period EMA for smoother pivots
        pivots = ema_derivative_pivots(df, price_span=7, rsi_span=7)
        print(f"Found {len(pivots['price_lows'])} price lows")
    """
    if price_col not in df.columns or rsi_col not in df.columns:
        return {
            "price_highs": pd.Index([]),
            "price_lows": pd.Index([]),
            "rsi_highs": pd.Index([]),
            "rsi_lows": pd.Index([]),
            "meta": {"method": "ema-deriv", "error": "Missing required columns"},
        }

    # Smooth the series with EMA
    price_smoothed = _ema(df[price_col], price_span)
    rsi_smoothed = _ema(df[rsi_col], rsi_span)

    # Calculate first derivative (rate of change)
    price_derivative = price_smoothed.diff()
    rsi_derivative = rsi_smoothed.diff()

    # Detect sign changes in derivative
    # Pivot low: derivative goes from negative to positive
    price_lows = price_smoothed[
        (price_derivative.shift(1) < 0) & (price_derivative > 0)
    ].index

    # Pivot high: derivative goes from positive to negative
    price_highs = price_smoothed[
        (price_derivative.shift(1) > 0) & (price_derivative < 0)
    ].index

    # Same logic for RSI
    rsi_lows = rsi_smoothed[(rsi_derivative.shift(1) < 0) & (rsi_derivative > 0)].index
    rsi_highs = rsi_smoothed[(rsi_derivative.shift(1) > 0) & (rsi_derivative < 0)].index

    return {
        "price_highs": price_highs,
        "price_lows": price_lows,
        "rsi_highs": rsi_highs,
        "rsi_lows": rsi_lows,
        "meta": {
            "method": "ema-deriv",
            "price_span": price_span,
            "rsi_span": rsi_span,
            "price_pivots": len(price_highs) + len(price_lows),
            "rsi_pivots": len(rsi_highs) + len(rsi_lows),
        },
    }
