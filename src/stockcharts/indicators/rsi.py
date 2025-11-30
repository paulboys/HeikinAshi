"""RSI (Relative Strength Index) calculation module.

Public API:
    compute_rsi(close: pd.Series, period: int = 14) -> pd.Series
"""

from __future__ import annotations

import pandas as pd

__all__ = ["compute_rsi"]


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Compute Relative Strength Index (RSI).

    RSI = 100 - (100 / (1 + RS)) where RS = Average Gain / Average Loss.

    Args:
        close: Series of closing prices.
        period: Lookback period length (must be >=1, default 14).

    Returns:
        Series of RSI values in range [0,100]. NaN values where insufficient history.

    Raises:
        ValueError: If ``period`` < 1.
    """
    if period < 1:
        raise ValueError("period must be >= 1")

    if len(close) < period + 1:
        # Not enough data to seed RSI calculation: return NaNs aligned to index
        return pd.Series([pd.NA] * len(close), index=close.index, dtype="Float64")

    # Price changes
    delta = close.diff()

    # Gains & losses separated
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # EWMA averages (EWM chosen for smoother adaptation)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.astype(float)
