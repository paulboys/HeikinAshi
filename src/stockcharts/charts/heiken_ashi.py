"""Heiken Ashi candle computation.

Heiken Ashi formulas:
HA_Close = (O + H + L + C) / 4
HA_Open = (prev_HA_Open + prev_HA_Close) / 2  (seed first row as (O0 + C0)/2)
HA_High = max(H, HA_Open, HA_Close)
HA_Low = min(L, HA_Open, HA_Close)
"""
from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ["Open", "High", "Low", "Close"]


def heiken_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Return a new DataFrame with Heiken Ashi candles.

    Input DataFrame must contain columns Open, High, Low, Close.
    Index is preserved.
    Output columns: HA_Open, HA_High, HA_Low, HA_Close
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Input DataFrame missing required columns: {missing}")

    ha = pd.DataFrame(index=df.index.copy())
    # Flatten to 1D arrays (handles both single and multi-level column indexes)
    o = df["Open"].values.flatten()
    h = df["High"].values.flatten()
    l = df["Low"].values.flatten()
    c = df["Close"].values.flatten()

    ha_close = (o + h + l + c) / 4.0
    ha_open = ha_close.copy()
    # Seed first value
    ha_open[0] = (o[0] + c[0]) / 2.0
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0

    ha_high = pd.concat([
        pd.Series(h),
        pd.Series(ha_open),
        pd.Series(ha_close),
    ], axis=1).max(axis=1).values
    ha_low = pd.concat([
        pd.Series(l),
        pd.Series(ha_open),
        pd.Series(ha_close),
    ], axis=1).min(axis=1).values

    ha["HA_Open"] = ha_open
    ha["HA_Close"] = ha_close
    ha["HA_High"] = ha_high
    ha["HA_Low"] = ha_low
    return ha[["HA_Open", "HA_High", "HA_Low", "HA_Close"]]

__all__ = ["heiken_ashi"]
