"""Divergence detection module for price vs RSI analysis."""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, List
from stockcharts.indicators.pivots import ema_derivative_pivots

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
    lookback: int = 60,
    min_swing_points: int = 2,
    index_proximity_factor: int = 2,
    sequence_tolerance_pct: float = 0.002,
    rsi_sequence_tolerance: float = 0.0,
    pivot_method: str = 'swing',
    zigzag_pct: float = 0.03,
    zigzag_atr_mult: float = 2.0,
    zigzag_atr_period: int = 14,
    ema_price_span: int = 5,
    ema_rsi_span: int = 5
) -> dict:
    """
    Detect bullish and bearish divergences between price and RSI.
    
    Bullish Divergence (potential reversal up):
    - Price makes lower lows (2 or 3 points)
    - RSI makes higher lows (2 or 3 points)
    - Indicates weakening downtrend
    
    Bearish Divergence (potential reversal down):
    - Price makes higher highs (2 or 3 points)
    - RSI makes lower highs (2 or 3 points)
    - Indicates weakening uptrend
    
    Args:
        df: DataFrame with price and RSI columns
        price_col: Name of price column (default: 'Close')
        rsi_col: Name of RSI column (default: 'RSI')
        window: Window for swing point detection (default: 5)
        lookback: Number of bars to look back for divergence (default: 60)
        min_swing_points: Minimum swing points required (2 or 3, default: 2)
        index_proximity_factor: Multiplier for window to allow bar index gap tolerance (default: 2)
        sequence_tolerance_pct: Relative tolerance for 3-point price sequences (default: 0.002 = 0.2%)
        rsi_sequence_tolerance: Extra RSI tolerance in points for 3-point sequences (default: 0.0)
        pivot_method: Method for detecting pivots - 'swing' or 'ema-deriv' (default: 'swing')
        zigzag_pct: [DEPRECATED] Not used
        zigzag_atr_mult: [DEPRECATED] Not used
        zigzag_atr_period: [DEPRECATED] Not used
        ema_price_span: EMA smoothing span for price when using ema-deriv (default: 5)
        ema_rsi_span: EMA smoothing span for RSI when using ema-deriv (default: 5)
    
    Returns:
        Dict with:
            - 'bullish': bool, True if bullish divergence detected
            - 'bearish': bool, True if bearish divergence detected
            - 'bullish_details': str, description of bullish divergence
            - 'bearish_details': str, description of bearish divergence
            - 'last_signal': str, 'bullish', 'bearish', or 'none'
            - 'bullish_indices': tuple of price/RSI indices or None
            - 'bearish_indices': tuple of price/RSI indices or None
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
    
    # Find swing points in price and RSI using selected method
    if pivot_method == 'ema-deriv':
        # Use EMA-derivative pivot detection
        pivots_dict = ema_derivative_pivots(
            recent_df,
            price_col=price_col,
            rsi_col=rsi_col,
            price_span=ema_price_span,
            rsi_span=ema_rsi_span
        )
        price_high_idx = pivots_dict['price_highs']
        price_low_idx = pivots_dict['price_lows']
        rsi_high_idx = pivots_dict['rsi_highs']
        rsi_low_idx = pivots_dict['rsi_lows']
    else:
        # Traditional window-based swing point detection
        price_highs, price_lows = find_swing_points(recent_df[price_col], window)
        rsi_highs, rsi_lows = find_swing_points(recent_df[rsi_col], window)
        
        # Get indices where swing points exist
        price_high_idx = price_highs.dropna().index
        price_low_idx = price_lows.dropna().index
        rsi_high_idx = rsi_highs.dropna().index
        rsi_low_idx = rsi_lows.dropna().index
    
    # Precompute positional indices for bar-distance based alignment (handles weekends/holidays)
    pos_map = {idx: i for i, idx in enumerate(recent_df.index)}
    max_bar_gap = window * index_proximity_factor
    
    def nearest_by_bar(target_idx, candidates):
        """Return candidate with smallest absolute bar index distance within max_bar_gap."""
        if target_idx not in pos_map:
            return None
        tpos = pos_map[target_idx]
        viable = [(abs(pos_map[c] - tpos), c) for c in candidates if c in pos_map and abs(pos_map[c] - tpos) <= max_bar_gap]
        if not viable:
            return None
        return min(viable)[1]
    
    # Detect Bullish Divergence (price lower lows, RSI higher lows)
    if len(price_low_idx) >= min_swing_points and len(rsi_low_idx) >= min_swing_points:
        # Try 3-point divergence first if requested
        if min_swing_points == 3 and len(price_low_idx) >= 3 and len(rsi_low_idx) >= 3:
            p1_idx, p2_idx, p3_idx = price_low_idx[-3], price_low_idx[-2], price_low_idx[-1]
            
            # Find corresponding RSI lows using bar distance instead of calendar days
            r1_idx = nearest_by_bar(p1_idx, rsi_low_idx)
            r2_idx = nearest_by_bar(p2_idx, rsi_low_idx)
            r3_idx = nearest_by_bar(p3_idx, rsi_low_idx)
            
            if r1_idx and r2_idx and r3_idx:
                p1 = recent_df.loc[p1_idx, price_col]
                p2 = recent_df.loc[p2_idx, price_col]
                p3 = recent_df.loc[p3_idx, price_col]
                
                # Allow slight tolerance: each next low should be materially lower
                # p2 <= p1 * (1 - tolerance) and p3 <= p2 * (1 - tolerance)
                price_desc = (
                    (p2 <= p1 * (1 - sequence_tolerance_pct)) and
                    (p3 <= p2 * (1 - sequence_tolerance_pct))
                )
                
                r1 = recent_df.loc[r1_idx, rsi_col]
                r2 = recent_df.loc[r2_idx, rsi_col]
                r3 = recent_df.loc[r3_idx, rsi_col]
                
                # RSI should be ascending with tolerance
                rsi_asc = (
                    (r2 - r1 >= max(BULLISH_RSI_TOLERANCE, rsi_sequence_tolerance)) and
                    (r3 - r2 >= max(BULLISH_RSI_TOLERANCE, rsi_sequence_tolerance))
                )
                
                if price_desc and rsi_asc:
                    result['bullish'] = True
                    result['bullish_details'] = (
                        f"3-Point: Price {p1:.2f}→{p2:.2f}→{p3:.2f} (descending) | "
                        f"RSI {r1:.2f}→{r2:.2f}→{r3:.2f} (ascending)"
                    )
                    result['last_signal'] = 'bullish'
                    result['bullish_indices'] = (p1_idx, p2_idx, p3_idx, r1_idx, r2_idx, r3_idx)
        
        # Fall back to 2-point if 3-point not found or min_swing_points==2
        if not result['bullish'] and len(price_low_idx) >= 2 and len(rsi_low_idx) >= 2:
            p1_idx, p2_idx = price_low_idx[-2], price_low_idx[-1]
            
            # Find corresponding RSI lows using bar distance
            r1_idx = nearest_by_bar(p1_idx, rsi_low_idx)
            r2_idx = nearest_by_bar(p2_idx, rsi_low_idx)
            
            if r1_idx and r2_idx:
                p1 = recent_df.loc[p1_idx, price_col]
                p2 = recent_df.loc[p2_idx, price_col]
                r1 = recent_df.loc[r1_idx, rsi_col]
                r2 = recent_df.loc[r2_idx, rsi_col]
                
                price_ll = p2 < p1
                # RSI must be at least BULLISH_RSI_TOLERANCE points higher to confirm divergence
                rsi_hl = r2 - r1 >= BULLISH_RSI_TOLERANCE
                
                if price_ll and rsi_hl:
                    result['bullish'] = True
                    result['bullish_details'] = (
                        f"Price {p1:.2f}→{p2:.2f} (LL) | RSI {r1:.2f}→{r2:.2f} (HL)"
                    )
                    result['last_signal'] = 'bullish'
                    result['bullish_indices'] = (p1_idx, p2_idx, r1_idx, r2_idx)
    
    # Detect Bearish Divergence (price higher highs, RSI lower highs)
    if len(price_high_idx) >= min_swing_points and len(rsi_high_idx) >= min_swing_points:
        # Try 3-point divergence first if requested
        if min_swing_points == 3 and len(price_high_idx) >= 3 and len(rsi_high_idx) >= 3:
            p1_idx, p2_idx, p3_idx = price_high_idx[-3], price_high_idx[-2], price_high_idx[-1]
            
            # Find corresponding RSI highs using bar distance
            r1_idx = nearest_by_bar(p1_idx, rsi_high_idx)
            r2_idx = nearest_by_bar(p2_idx, rsi_high_idx)
            r3_idx = nearest_by_bar(p3_idx, rsi_high_idx)
            
            if r1_idx and r2_idx and r3_idx:
                p1 = recent_df.loc[p1_idx, price_col]
                p2 = recent_df.loc[p2_idx, price_col]
                p3 = recent_df.loc[p3_idx, price_col]
                
                # Allow slight tolerance: each next high should be materially higher
                # p2 >= p1 * (1 + tolerance) and p3 >= p2 * (1 + tolerance)
                price_asc = (
                    (p2 >= p1 * (1 + sequence_tolerance_pct)) and
                    (p3 >= p2 * (1 + sequence_tolerance_pct))
                )
                
                r1 = recent_df.loc[r1_idx, rsi_col]
                r2 = recent_df.loc[r2_idx, rsi_col]
                r3 = recent_df.loc[r3_idx, rsi_col]
                
                # RSI should be descending with tolerance
                rsi_desc = (
                    (r1 - r2 >= max(BEARISH_RSI_TOLERANCE, rsi_sequence_tolerance)) and
                    (r2 - r3 >= max(BEARISH_RSI_TOLERANCE, rsi_sequence_tolerance))
                )
                
                if price_asc and rsi_desc:
                    result['bearish'] = True
                    result['bearish_details'] = (
                        f"3-Point: Price {p1:.2f}→{p2:.2f}→{p3:.2f} (ascending) | "
                        f"RSI {r1:.2f}→{r2:.2f}→{r3:.2f} (descending)"
                    )
                    if result['last_signal'] == 'none':
                        result['last_signal'] = 'bearish'
                    result['bearish_indices'] = (p1_idx, p2_idx, p3_idx, r1_idx, r2_idx, r3_idx)
        
        # Fall back to 2-point if 3-point not found or min_swing_points==2
        if not result['bearish'] and len(price_high_idx) >= 2 and len(rsi_high_idx) >= 2:
            p1_idx, p2_idx = price_high_idx[-2], price_high_idx[-1]
            
            # Find corresponding RSI highs using bar distance
            r1_idx = nearest_by_bar(p1_idx, rsi_high_idx)
            r2_idx = nearest_by_bar(p2_idx, rsi_high_idx)
            
            if r1_idx and r2_idx:
                p1 = recent_df.loc[p1_idx, price_col]
                p2 = recent_df.loc[p2_idx, price_col]
                r1 = recent_df.loc[r1_idx, rsi_col]
                r2 = recent_df.loc[r2_idx, rsi_col]
                
                price_hh = p2 > p1
                # RSI must be at least BEARISH_RSI_TOLERANCE points lower to confirm divergence
                rsi_lh = r1 - r2 >= BEARISH_RSI_TOLERANCE
                
                if price_hh and rsi_lh:
                    result['bearish'] = True
                    result['bearish_details'] = (
                        f"Price {p1:.2f}→{p2:.2f} (HH) | RSI {r1:.2f}→{r2:.2f} (LH)"
                    )
                    if result['last_signal'] == 'none':
                        result['last_signal'] = 'bearish'
                    result['bearish_indices'] = (p1_idx, p2_idx, r1_idx, r2_idx)
    
    return result


def check_breakout_occurred(
    df: pd.DataFrame,
    divergence_idx: pd.Timestamp,
    divergence_type: str,
    threshold: float = 0.05,
    price_col: str = 'Close'
) -> bool:
    """
    Check if a breakout has already occurred after divergence detection.
    
    For bullish divergence: Price moved up significantly from divergence point.
    For bearish divergence: Price moved down significantly from divergence point.
    
    Args:
        df: DataFrame with price data
        divergence_idx: Index of the divergence point (second swing low/high)
        divergence_type: 'bullish' or 'bearish'
        threshold: Percentage move required to consider it a breakout (default: 0.05 = 5%)
        price_col: Name of price column (default: 'Close')
    
    Returns:
        True if breakout already occurred (signal is stale), False if still valid
    """
    if divergence_idx not in df.index:
        return False
    
    divergence_price = df.loc[divergence_idx, price_col]
    current_price = df[price_col].iloc[-1]
    
    if divergence_type == 'bullish':
        # Bullish divergence: check if price already rallied past threshold
        breakout_price = divergence_price * (1 + threshold)
        return current_price >= breakout_price
    
    elif divergence_type == 'bearish':
        # Bearish divergence: check if price already dropped past threshold
        breakout_price = divergence_price * (1 - threshold)
        return current_price <= breakout_price
    
    return False


def check_failed_breakout(
    df: pd.DataFrame,
    divergence_idx: pd.Timestamp,
    divergence_type: str,
    lookback_window: int = 10,
    attempt_threshold: float = 0.03,
    reversal_threshold: float = 0.01,
    price_col: str = 'Close'
) -> bool:
    """
    Check if divergence led to a failed breakout attempt.
    
    A failed breakout means price tried to move in the divergence direction
    but reversed and closed back near/below the divergence level.
    
    Args:
        df: DataFrame with price data
        divergence_idx: Index of the divergence point
        divergence_type: 'bullish' or 'bearish'
        lookback_window: Number of recent bars to check (default: 10)
        attempt_threshold: % move required to consider an "attempt" (default: 0.03 = 3%)
        reversal_threshold: % from divergence price to consider "failed" (default: 0.01 = 1%)
        price_col: Name of price column (default: 'Close')
    
    Returns:
        True if failed breakout detected (signal is weak), False otherwise
    """
    if divergence_idx not in df.index:
        return False
    
    # Get data after divergence point
    div_loc = df.index.get_loc(divergence_idx)
    if div_loc >= len(df) - 1:
        return False  # No data after divergence
    
    recent_data = df.iloc[div_loc:div_loc + lookback_window + 1]
    if len(recent_data) < 2:
        return False
    
    divergence_price = df.loc[divergence_idx, price_col]
    current_close = df[price_col].iloc[-1]
    
    if divergence_type == 'bullish':
        # Check for failed bullish attempt
        attempted_high = recent_data['High'].max()
        attempt_target = divergence_price * (1 + attempt_threshold)
        failed_level = divergence_price * (1 + reversal_threshold)
        
        # Price tried to rally (reached attempt threshold) but closed back low
        if attempted_high >= attempt_target and current_close < failed_level:
            return True
    
    elif divergence_type == 'bearish':
        # Check for failed bearish attempt
        attempted_low = recent_data['Low'].min()
        attempt_target = divergence_price * (1 - attempt_threshold)
        failed_level = divergence_price * (1 - reversal_threshold)
        
        # Price tried to drop (reached attempt threshold) but closed back high
        if attempted_low <= attempt_target and current_close > failed_level:
            return True
    
    return False
