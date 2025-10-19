"""RSI (Relative Strength Index) calculation module."""

import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate the Relative Strength Index (RSI).
    
    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss
    
    Args:
        close: Series of closing prices
        period: RSI period (default: 14)
    
    Returns:
        Series of RSI values (0-100)
    """
    if len(close) < period + 1:
        return pd.Series([None] * len(close), index=close.index)
    
    # Calculate price changes
    delta = close.diff()
    
    # Separate gains and losses
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # Calculate exponential weighted moving averages
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi
