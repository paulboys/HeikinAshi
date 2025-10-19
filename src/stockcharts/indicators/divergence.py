"""Divergence detection module for price vs RSI analysis."""

import pandas as pd
import numpy as np
from typing import Tuple, Optional

# Tolerance constants to avoid false divergences due to minor RSI fluctuations
BEARISH_RSI_TOLERANCE = 0.5  # RSI must be at least 0.5 points lower for bearish divergence
BULLISH_RSI_TOLERANCE = 0.5  # RSI must be at least 0.5 points higher for bullish divergence


def find_swing_points(series: pd.Series, window: int = 5) -> Tuple[pd.Series, pd.Series]:
    """
    Find swing highs and lows in a price or indicator series.
    
    A swing high is a local maximum (higher than surrounding points).
    A swing low is a local minimum (lower than surrounding points).
    
    Args:
        series: Price or indicator series
        window: Number of bars on each side to compare (default: 5)
    
    Returns:
        Tuple of (swing_highs, swing_lows) where each is a Series with values at swing points
    """
    swing_highs = pd.Series(index=series.index, dtype=float)
    swing_lows = pd.Series(index=series.index, dtype=float)
    
    for i in range(window, len(series) - window):
        # Check if current point is a swing high
        is_high = True
        for j in range(-window, window + 1):
            if j != 0 and series.iloc[i] <= series.iloc[i + j]:
                is_high = False
                break
        if is_high:
            swing_highs.iloc[i] = series.iloc[i]
        
        # Check if current point is a swing low
        is_low = True
        for j in range(-window, window + 1):
            if j != 0 and series.iloc[i] >= series.iloc[i + j]:
                is_low = False
                break
        if is_low:
            swing_lows.iloc[i] = series.iloc[i]
    
    return swing_highs, swing_lows


def detect_divergence(
    df: pd.DataFrame,
    price_col: str = 'Close',
    rsi_col: str = 'RSI',
    window: int = 5,
    lookback: int = 60
) -> dict:
    """
    Detect bullish and bearish divergences between price and RSI.
    
    Bullish Divergence (potential reversal up):
    - Price makes lower low
    - RSI makes higher low
    - Indicates weakening downtrend
    
    Bearish Divergence (potential reversal down):
    - Price makes higher high
    - RSI makes lower high
    - Indicates weakening uptrend
    
    Args:
        df: DataFrame with price and RSI columns
        price_col: Name of price column (default: 'Close')
        rsi_col: Name of RSI column (default: 'RSI')
        window: Window for swing point detection (default: 5)
        lookback: Number of bars to look back for divergence (default: 60)
    
    Returns:
        Dict with:
            - 'bullish': bool, True if bullish divergence detected
            - 'bearish': bool, True if bearish divergence detected
            - 'bullish_details': str, description of bullish divergence
            - 'bearish_details': str, description of bearish divergence
            - 'last_signal': str, 'bullish', 'bearish', or 'none'
            - 'bullish_indices': tuple (p1_idx, p2_idx, r1_idx, r2_idx) or None
            - 'bearish_indices': tuple (p1_idx, p2_idx, r1_idx, r2_idx) or None
    """
    result = {
        'bullish': False,
        'bearish': False,
        'bullish_details': '',
        'bearish_details': '',
        'last_signal': 'none',
        'bullish_indices': None,
        'bearish_indices': None
    }
    
    if len(df) < lookback:
        return result
    
    # Use only recent data
    recent_df = df.tail(lookback).copy()
    
    # Find swing points in price and RSI
    price_highs, price_lows = find_swing_points(recent_df[price_col], window)
    rsi_highs, rsi_lows = find_swing_points(recent_df[rsi_col], window)
    
    # Get indices where swing points exist
    price_high_idx = price_highs.dropna().index
    price_low_idx = price_lows.dropna().index
    rsi_high_idx = rsi_highs.dropna().index
    rsi_low_idx = rsi_lows.dropna().index
    
    # Detect Bullish Divergence (price lower low, RSI higher low)
    if len(price_low_idx) >= 2 and len(rsi_low_idx) >= 2:
        # Get last two price lows
        last_two_price_lows = price_low_idx[-2:]
        p1_idx, p2_idx = last_two_price_lows[0], last_two_price_lows[1]
        
        # Find corresponding RSI lows (within reasonable time window)
        rsi_lows_near_p1 = [idx for idx in rsi_low_idx if abs((idx - p1_idx).days) <= window * 2]
        rsi_lows_near_p2 = [idx for idx in rsi_low_idx if abs((idx - p2_idx).days) <= window * 2]
        
        if rsi_lows_near_p1 and rsi_lows_near_p2:
            r1_idx = min(rsi_lows_near_p1, key=lambda x: abs((x - p1_idx).days))
            r2_idx = min(rsi_lows_near_p2, key=lambda x: abs((x - p2_idx).days))
            
            price_ll = recent_df.loc[p2_idx, price_col] < recent_df.loc[p1_idx, price_col]
            # RSI must be at least BULLISH_RSI_TOLERANCE points higher to confirm divergence
            rsi_hl = recent_df.loc[r2_idx, rsi_col] - BULLISH_RSI_TOLERANCE > recent_df.loc[r1_idx, rsi_col]
            
            if price_ll and rsi_hl:
                result['bullish'] = True
                result['bullish_details'] = (
                    f"Price: {recent_df.loc[p1_idx, price_col]:.2f} → "
                    f"{recent_df.loc[p2_idx, price_col]:.2f} (lower low) | "
                    f"RSI: {recent_df.loc[r1_idx, rsi_col]:.2f} → "
                    f"{recent_df.loc[r2_idx, rsi_col]:.2f} (higher low)"
                )
                result['last_signal'] = 'bullish'
                result['bullish_indices'] = (p1_idx, p2_idx, r1_idx, r2_idx)
    
    # Detect Bearish Divergence (price higher high, RSI lower high)
    if len(price_high_idx) >= 2 and len(rsi_high_idx) >= 2:
        # Get last two price highs
        last_two_price_highs = price_high_idx[-2:]
        p1_idx, p2_idx = last_two_price_highs[0], last_two_price_highs[1]
        
        # Find corresponding RSI highs (within reasonable time window)
        rsi_highs_near_p1 = [idx for idx in rsi_high_idx if abs((idx - p1_idx).days) <= window * 2]
        rsi_highs_near_p2 = [idx for idx in rsi_high_idx if abs((idx - p2_idx).days) <= window * 2]
        
        if rsi_highs_near_p1 and rsi_highs_near_p2:
            r1_idx = min(rsi_highs_near_p1, key=lambda x: abs((x - p1_idx).days))
            r2_idx = min(rsi_highs_near_p2, key=lambda x: abs((x - p2_idx).days))
            
            price_hh = recent_df.loc[p2_idx, price_col] > recent_df.loc[p1_idx, price_col]
            # RSI must be at least BEARISH_RSI_TOLERANCE points lower to confirm divergence
            rsi_lh = recent_df.loc[r2_idx, rsi_col] + BEARISH_RSI_TOLERANCE < recent_df.loc[r1_idx, rsi_col]
            
            if price_hh and rsi_lh:
                result['bearish'] = True
                result['bearish_details'] = (
                    f"Price: {recent_df.loc[p1_idx, price_col]:.2f} → "
                    f"{recent_df.loc[p2_idx, price_col]:.2f} (higher high) | "
                    f"RSI: {recent_df.loc[r1_idx, rsi_col]:.2f} → "
                    f"{recent_df.loc[r2_idx, rsi_col]:.2f} (lower high)"
                )
                if result['last_signal'] == 'none':
                    result['last_signal'] = 'bearish'
                result['bearish_indices'] = (p1_idx, p2_idx, r1_idx, r2_idx)
    
    return result
