"""Price and RSI divergence visualization module.

This module provides functionality to plot candlestick price charts with RSI
indicator subplots, highlighting detected divergences.
"""
from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
import numpy as np

from ..indicators.rsi import compute_rsi
from ..indicators.divergence import find_swing_points


def plot_price_rsi(
    df: pd.DataFrame,
    ticker: str = "",
    rsi_period: int = 14,
    show_divergence: bool = True,
    divergence_window: int = 5,
    divergence_lookback: int = 60,
    figsize: tuple[float, float] = (14, 10),
    overbought: float = 70.0,
    oversold: float = 30.0,
    precomputed_divergence: dict = None,
) -> Figure:
    """
    Create a two-panel chart with candlestick price and RSI indicator.
    
    Args:
        df: DataFrame with OHLC data (columns: Open, High, Low, Close)
        ticker: Stock ticker symbol for title
        rsi_period: RSI calculation period (default: 14)
        show_divergence: If True, mark detected divergences on chart
        divergence_window: Window size for swing point detection
        divergence_lookback: How many bars to look back for divergences
        figsize: Figure size (width, height) in inches
        overbought: RSI overbought level (default: 70)
        oversold: RSI oversold level (default: 30)
        precomputed_divergence: Dict with 'bullish_indices' and/or 'bearish_indices' 
                                from screener (overrides auto-detection)
    
    Returns:
        Matplotlib Figure object
    """
    # Compute RSI
    df = df.copy()
    df['RSI'] = compute_rsi(df['Close'], period=rsi_period)
    
    # Use precomputed divergence if provided, otherwise auto-detect
    divergence_data = None
    if precomputed_divergence:
        # Convert precomputed indices to DataFrame format
        divergence_data = _convert_precomputed_to_df(df, precomputed_divergence)
    elif show_divergence and len(df) >= divergence_lookback:
        recent_df = df.tail(divergence_lookback)
        divergence_data = _find_divergence_points(
            recent_df, 
            divergence_window
        )
    
    # Create figure with 2 subplots
    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=figsize,
        height_ratios=[3, 1],
        sharex=True
    )
    
    # Plot candlesticks on top panel
    _plot_candlesticks(ax1, df)
    
    # Add divergence markers to price chart
    if divergence_data is not None:
        _plot_price_divergences(ax1, df, divergence_data)
    
    # Format top panel
    ax1.set_ylabel('Price', fontsize=12, fontweight='bold')
    ax1.set_title(
        f'{ticker} - Price Action with RSI Divergence' if ticker else 'Price Action with RSI Divergence',
        fontsize=14,
        fontweight='bold',
        pad=20
    )
    ax1.grid(True, alpha=0.3, linestyle='--')
    if divergence_data is not None:
        ax1.legend(loc='upper left', fontsize=10)
    
    # Plot RSI on bottom panel
    _plot_rsi(ax2, df, overbought=overbought, oversold=oversold)
    
    # Add divergence markers to RSI chart
    if divergence_data is not None:
        _plot_rsi_divergences(ax2, df, divergence_data)
    
    # Format bottom panel
    ax2.set_ylabel('RSI', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.legend(loc='upper left', fontsize=10)
    ax2.set_ylim(0, 100)
    
    # Rotate x-axis labels
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    return fig


def _convert_precomputed_to_df(df: pd.DataFrame, precomputed: dict) -> pd.DataFrame:
    """
    Convert precomputed divergence indices to DataFrame format.
    
    Args:
        df: Full OHLC DataFrame with RSI
        precomputed: Dict with 'bullish_indices' and/or 'bearish_indices'
                     Each is a tuple: (p1_idx, p2_idx, r1_idx, r2_idx)
    
    Returns:
        DataFrame with divergence information or None
    """
    divergences = []
    
    # Handle bullish divergence
    if precomputed.get('bullish_indices'):
        p1_idx, p2_idx, r1_idx, r2_idx = precomputed['bullish_indices']
        # Check if indices exist in current dataframe
        if all(idx in df.index for idx in [p1_idx, p2_idx, r1_idx, r2_idx]):
            divergences.append({
                'divergence_type': 'bullish',
                'swing_start_date': p1_idx,
                'swing_end_date': p2_idx,
                'price_start': df.loc[p1_idx, 'Close'],
                'price_end': df.loc[p2_idx, 'Close'],
                'rsi_start': df.loc[r1_idx, 'RSI'],
                'rsi_end': df.loc[r2_idx, 'RSI']
            })
    
    # Handle bearish divergence
    if precomputed.get('bearish_indices'):
        p1_idx, p2_idx, r1_idx, r2_idx = precomputed['bearish_indices']
        # Check if indices exist in current dataframe
        if all(idx in df.index for idx in [p1_idx, p2_idx, r1_idx, r2_idx]):
            divergences.append({
                'divergence_type': 'bearish',
                'swing_start_date': p1_idx,
                'swing_end_date': p2_idx,
                'price_start': df.loc[p1_idx, 'Close'],
                'price_end': df.loc[p2_idx, 'Close'],
                'rsi_start': df.loc[r1_idx, 'RSI'],
                'rsi_end': df.loc[r2_idx, 'RSI']
            })
    
    return pd.DataFrame(divergences) if divergences else None


def _find_divergence_points(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """
    Find divergence points in price and RSI.
    
    Returns DataFrame with columns:
        - divergence_type: 'bullish' or 'bearish'
        - swing_start_date: Date of first swing point
        - swing_end_date: Date of second swing point
        - price_start: Price at first swing
        - price_end: Price at second swing
        - rsi_start: RSI at first swing
        - rsi_end: RSI at second swing
    """
    # Find swing points
    price_highs, price_lows = find_swing_points(df['Close'], window)
    rsi_highs, rsi_lows = find_swing_points(df['RSI'], window)
    
    divergences = []
    
    # Find bullish divergences (price lower lows, RSI higher lows)
    price_low_idx = price_lows.dropna().index
    rsi_low_idx = rsi_lows.dropna().index
    
    if len(price_low_idx) >= 2 and len(rsi_low_idx) >= 2:
        for i in range(len(price_low_idx) - 1):
            p1_idx = price_low_idx[i]
            p2_idx = price_low_idx[i + 1]
            
            # Find nearest RSI lows
            rsi_near_p1 = [idx for idx in rsi_low_idx if abs((idx - p1_idx).days) <= window * 2]
            rsi_near_p2 = [idx for idx in rsi_low_idx if abs((idx - p2_idx).days) <= window * 2]
            
            if rsi_near_p1 and rsi_near_p2:
                r1_idx = min(rsi_near_p1, key=lambda x: abs((x - p1_idx).days))
                r2_idx = min(rsi_near_p2, key=lambda x: abs((x - p2_idx).days))
                
                price_ll = df.loc[p2_idx, 'Close'] < df.loc[p1_idx, 'Close']
                rsi_hl = df.loc[r2_idx, 'RSI'] > df.loc[r1_idx, 'RSI']
                
                if price_ll and rsi_hl:
                    divergences.append({
                        'divergence_type': 'bullish',
                        'swing_start_date': p1_idx,
                        'swing_end_date': p2_idx,
                        'price_start': df.loc[p1_idx, 'Close'],
                        'price_end': df.loc[p2_idx, 'Close'],
                        'rsi_start': df.loc[r1_idx, 'RSI'],
                        'rsi_end': df.loc[r2_idx, 'RSI']
                    })
    
    # Find bearish divergences (price higher highs, RSI lower highs)
    price_high_idx = price_highs.dropna().index
    rsi_high_idx = rsi_highs.dropna().index
    
    if len(price_high_idx) >= 2 and len(rsi_high_idx) >= 2:
        for i in range(len(price_high_idx) - 1):
            p1_idx = price_high_idx[i]
            p2_idx = price_high_idx[i + 1]
            
            # Find nearest RSI highs
            rsi_near_p1 = [idx for idx in rsi_high_idx if abs((idx - p1_idx).days) <= window * 2]
            rsi_near_p2 = [idx for idx in rsi_high_idx if abs((idx - p2_idx).days) <= window * 2]
            
            if rsi_near_p1 and rsi_near_p2:
                r1_idx = min(rsi_near_p1, key=lambda x: abs((x - p1_idx).days))
                r2_idx = min(rsi_near_p2, key=lambda x: abs((x - p2_idx).days))
                
                price_hh = df.loc[p2_idx, 'Close'] > df.loc[p1_idx, 'Close']
                rsi_lh = df.loc[r2_idx, 'RSI'] < df.loc[r1_idx, 'RSI']
                
                if price_hh and rsi_lh:
                    divergences.append({
                        'divergence_type': 'bearish',
                        'swing_start_date': p1_idx,
                        'swing_end_date': p2_idx,
                        'price_start': df.loc[p1_idx, 'Close'],
                        'price_end': df.loc[p2_idx, 'Close'],
                        'rsi_start': df.loc[r1_idx, 'RSI'],
                        'rsi_end': df.loc[r2_idx, 'RSI']
                    })
    
    return pd.DataFrame(divergences) if divergences else None


def _plot_candlesticks(ax: Axes, df: pd.DataFrame) -> None:
    """Plot candlestick chart on given axes."""
    # Convert index to numeric for plotting
    x = np.arange(len(df))
    
    # Determine candle colors
    colors = ['green' if close >= open_ else 'red' 
              for open_, close in zip(df['Open'], df['Close'])]
    
    # Plot wicks (high-low lines)
    for i, (high, low) in enumerate(zip(df['High'], df['Low'])):
        ax.plot([i, i], [low, high], color='black', linewidth=0.5, zorder=1)
    
    # Plot candle bodies
    for i, (open_, close, color) in enumerate(zip(df['Open'], df['Close'], colors)):
        height = abs(close - open_)
        bottom = min(open_, close)
        ax.bar(i, height, bottom=bottom, width=0.6, color=color, 
               edgecolor='black', linewidth=0.5, alpha=0.8, zorder=2)
    
    # Set x-axis ticks to dates
    tick_spacing = max(len(df) // 10, 1)
    ax.set_xticks(x[::tick_spacing])
    ax.set_xticklabels(df.index[::tick_spacing].strftime('%Y-%m-%d'))


def _plot_rsi(ax: Axes, df: pd.DataFrame, overbought: float, oversold: float) -> None:
    """Plot RSI line chart with overbought/oversold levels."""
    x = np.arange(len(df))
    
    # Plot RSI line
    ax.plot(x, df['RSI'], color='blue', linewidth=2, label=f'RSI', zorder=3)
    
    # Plot overbought/oversold lines
    ax.axhline(y=overbought, color='red', linestyle='--', linewidth=1, 
               alpha=0.7, label=f'Overbought ({overbought})')
    ax.axhline(y=oversold, color='green', linestyle='--', linewidth=1, 
               alpha=0.7, label=f'Oversold ({oversold})')
    ax.axhline(y=50, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
    
    # Set x-axis ticks to dates
    tick_spacing = max(len(df) // 10, 1)
    ax.set_xticks(x[::tick_spacing])
    ax.set_xticklabels(df.index[::tick_spacing].strftime('%Y-%m-%d'))


def _plot_price_divergences(ax: Axes, df: pd.DataFrame, divergences: pd.DataFrame) -> None:
    """Mark divergence points on price chart."""
    x = np.arange(len(df))
    
    # Create a mapping of dates to x positions
    date_to_x = {date: i for i, date in enumerate(df.index)}
    
    # Track if we've already added labels (to avoid duplicates)
    bullish_labeled = False
    bearish_labeled = False
    
    for _, div in divergences.iterrows():
        div_type = div['divergence_type']
        start_date = div['swing_start_date']
        end_date = div['swing_end_date']
        
        # Skip if dates not in dataframe
        if start_date not in date_to_x or end_date not in date_to_x:
            continue
            
        start_x = date_to_x[start_date]
        end_x = date_to_x[end_date]
        start_price = df.loc[start_date, 'Close']
        end_price = df.loc[end_date, 'Close']
        
        # Color and style based on divergence type
        if div_type == 'bullish':
            color = 'green'
            marker = '^'
            label = 'Bullish Divergence' if not bullish_labeled else None
            bullish_labeled = True
        else:  # bearish
            color = 'red'
            marker = 'v'
            label = 'Bearish Divergence' if not bearish_labeled else None
            bearish_labeled = True
        
        # Plot divergence line
        ax.plot([start_x, end_x], [start_price, end_price], 
                color=color, linewidth=2, linestyle='--', alpha=0.7, zorder=4,
                label=label)
        
        # Plot markers at swing points
        ax.scatter([start_x, end_x], [start_price, end_price], 
                  color=color, marker=marker, s=100, zorder=5, 
                  edgecolors='black', linewidths=1.5)


def _plot_rsi_divergences(ax: Axes, df: pd.DataFrame, divergences: pd.DataFrame) -> None:
    """Mark divergence points on RSI chart."""
    x = np.arange(len(df))
    
    # Create a mapping of dates to x positions
    date_to_x = {date: i for i, date in enumerate(df.index)}
    
    for _, div in divergences.iterrows():
        div_type = div['divergence_type']
        start_date = div['swing_start_date']
        end_date = div['swing_end_date']
        
        # Skip if dates not in dataframe
        if start_date not in date_to_x or end_date not in date_to_x:
            continue
            
        start_x = date_to_x[start_date]
        end_x = date_to_x[end_date]
        start_rsi = df.loc[start_date, 'RSI']
        end_rsi = df.loc[end_date, 'RSI']
        
        # Color based on divergence type
        color = 'green' if div_type == 'bullish' else 'red'
        marker = '^' if div_type == 'bullish' else 'v'
        
        # Plot divergence line
        ax.plot([start_x, end_x], [start_rsi, end_rsi], 
                color=color, linewidth=2, linestyle='--', alpha=0.7, zorder=4)
        
        # Plot markers at swing points
        ax.scatter([start_x, end_x], [start_rsi, end_rsi], 
                  color=color, marker=marker, s=100, zorder=5,
                  edgecolors='black', linewidths=1.5)


__all__ = ['plot_price_rsi']
