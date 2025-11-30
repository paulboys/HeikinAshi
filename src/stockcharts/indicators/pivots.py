"""Pivot extraction utilities (EMA-derivative based).

Public API:
    ema_derivative_pivots(df: pd.DataFrame, ...) -> dict
Returns pivot indices for price & RSI along with metadata.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

__all__ = ["ema_derivative_pivots"]


def _ema(series: pd.Series, span: int) -> pd.Series:
    """Return exponential moving average for ``series`` using span.

    Args:
        series: Input numeric series.
        span: EMA span (period) for smoothing.
    """
    return series.ewm(span=span, adjust=False).mean()


def ema_derivative_pivots(
    df: pd.DataFrame,
    price_col: str = "Close",
    rsi_col: str = "RSI",
    price_span: int = 5,
    rsi_span: int = 5,
) -> dict[str, Any]:
    """Detect pivot highs/lows via sign changes in first derivative of EMA-smoothed series.

    Method:
        1. Smooth price & RSI with EMA.
        2. Compute first difference (derivative).
        3. Identify sign-change points as pivots:
            - Pivot Low: derivative < 0 then > 0.
            - Pivot High: derivative > 0 then < 0.

    Args:
        df: DataFrame containing at least ``price_col`` and ``rsi_col``.
        price_col: Price column name (default "Close").
        rsi_col: RSI column name (default "RSI").
        price_span: EMA span for price smoothing.
        rsi_span: EMA span for RSI smoothing.

    Returns:
        Dict with keys: ``price_highs``, ``price_lows``, ``rsi_highs``, ``rsi_lows``, ``meta``.
        ``meta`` includes method name and counts.
    """
    if price_col not in df.columns or rsi_col not in df.columns:
        return {
            "price_highs": pd.Index([]),
            "price_lows": pd.Index([]),
            "rsi_highs": pd.Index([]),
            "rsi_lows": pd.Index([]),
            "meta": {"method": "ema-deriv", "error": "Missing required columns"},
        }

    price_smoothed = _ema(df[price_col], price_span)
    rsi_smoothed = _ema(df[rsi_col], rsi_span)

    price_derivative = price_smoothed.diff()
    rsi_derivative = rsi_smoothed.diff()

    price_lows = price_smoothed[(price_derivative.shift(1) < 0) & (price_derivative > 0)].index
    price_highs = price_smoothed[(price_derivative.shift(1) > 0) & (price_derivative < 0)].index
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
