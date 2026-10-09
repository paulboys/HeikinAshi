"""Stochastic Oscillator calculation module.

Computes the Slow Stochastic Oscillator (%K and %D) used to identify
overbought/oversold conditions and momentum shifts.

Public API:
    compute_stochastic(
        high: pd.Series, low: pd.Series, close: pd.Series,
        k_period: int = 14, d_period: int = 3, smooth_k: int = 3,
    ) -> pd.DataFrame
"""

from __future__ import annotations

import pandas as pd

__all__ = ["compute_stochastic"]


def compute_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
) -> pd.DataFrame:
    """Compute the Stochastic Oscillator (%K and %D).

    The raw (fast) %K is::

        %K_raw = (Close - Lowest_Low(k_period)) / (Highest_High(k_period) - Lowest_Low(k_period)) * 100

    The slow %K is an SMA of %K_raw over *smooth_k* periods, and %D is
    an SMA of the slow %K over *d_period* periods.

    Setting ``smooth_k=1`` gives the *Fast Stochastic*; ``smooth_k=3``
    (the default) gives the more common *Slow Stochastic*.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        k_period: Lookback window for the highest-high / lowest-low
                  calculation (must be >= 1, default 14).
        d_period: SMA smoothing period for %D (must be >= 1, default 3).
        smooth_k: SMA smoothing period applied to raw %K to produce the
                  reported %K (must be >= 1, default 3).

    Returns:
        DataFrame with columns ``['%K', '%D']``, values in [0, 100].
        NaN where insufficient history exists.

    Raises:
        ValueError: If any period parameter is < 1.
    """
    if k_period < 1:
        raise ValueError("k_period must be >= 1")
    if d_period < 1:
        raise ValueError("d_period must be >= 1")
    if smooth_k < 1:
        raise ValueError("smooth_k must be >= 1")

    n = len(close)
    if n < k_period:
        return pd.DataFrame(
            {"pctK": [float("nan")] * n, "pctD": [float("nan")] * n},
            index=close.index,
        )

    # Lowest low and highest high over the k_period window
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()

    # Raw (fast) %K
    denom = highest_high - lowest_low
    # Avoid division by zero when high == low over entire window
    denom = denom.replace(0, float("nan"))
    k_raw = ((close - lowest_low) / denom) * 100.0

    # Slow %K = SMA(raw %K, smooth_k)
    pct_k = k_raw.rolling(window=smooth_k, min_periods=smooth_k).mean()

    # %D = SMA(slow %K, d_period)
    pct_d = pct_k.rolling(window=d_period, min_periods=d_period).mean()

    return pd.DataFrame({"pctK": pct_k, "pctD": pct_d}, index=close.index)
