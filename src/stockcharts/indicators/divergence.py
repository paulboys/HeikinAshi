"""Divergence detection module for price vs RSI analysis."""

from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from stockcharts.indicators.pivots import ema_derivative_pivots

# Tolerance constants to avoid false divergences due to minor RSI fluctuations
BEARISH_RSI_TOLERANCE = (
    0.5  # RSI must be at least 0.5 points lower for bearish divergence
)
BULLISH_RSI_TOLERANCE = (
    0.5  # RSI must be at least 0.5 points higher for bullish divergence
)


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute Average True Range for volatility normalization.

    Args:
        df: DataFrame with High, Low, Close columns
        period: ATR period (default: 14)

    Returns:
        Series of ATR values
    """
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def find_three_point_sequences(
    df: pd.DataFrame,
    price_idx: Iterable,
    rsi_idx: Iterable,
    kind: str = "low",
    price_col: str = "Close",
    rsi_col: str = "RSI",
    max_bar_gap: int = 10,
    sequence_tolerance_pct: float = 0.01,
    min_magnitude_atr_mult: float = 0.5,
    atr_period: int = 14,
    require_strict_order: bool = False,
) -> List[Dict[str, Any]]:
    """
    Find and score 3-point divergence sequences from pivot indices.

    Returns candidate triples (3 consecutive pivots) that form valid divergence patterns,
    sorted by conviction score (higher = stronger signal).

    Args:
        df: DataFrame with price and RSI data (typically tail(lookback))
        price_idx: Ordered pivot indices for price (timestamps from EMA-derivative or swing)
        rsi_idx: Ordered pivot indices for RSI
        kind: 'low' for bullish divergence (descending price, ascending RSI)
              'high' for bearish divergence (ascending price, descending RSI)
        price_col: Name of price column (default: 'Close')
        rsi_col: Name of RSI column (default: 'RSI')
        max_bar_gap: Maximum bar distance between price and RSI pivots (default: 10)
        sequence_tolerance_pct: Relative tolerance for price monotonicity (default: 0.01 = 1%)
        min_magnitude_atr_mult: Minimum price move as multiple of ATR (default: 0.5)
        atr_period: Period for ATR calculation (default: 14)
        require_strict_order: If True, enforce strict < or > (default: False allows tolerance)

    Returns:
        List of dicts with keys:
            - kind: 'low' or 'high'
            - price_idx: tuple of 3 price pivot timestamps
            - rsi_idx: tuple of 3 RSI pivot timestamps
            - price_vals: tuple of 3 price values
            - rsi_vals: tuple of 3 RSI values
            - score: conviction score (higher = better)
            - meta: dict with span12, span23, atr values
    """
    # Build position map for bar-distance calculations
    pos = {idx: i for i, idx in enumerate(df.index)}
    price_idx = [i for i in price_idx if i in pos]
    rsi_idx = [i for i in rsi_idx if i in pos]

    if len(price_idx) < 3 or len(rsi_idx) < 3:
        return []

    # Helper: find nearest RSI pivot by bar distance within max_bar_gap
    def nearest_rsi(target_idx):
        tpos = pos[target_idx]
        best = None
        best_gap = max_bar_gap + 1
        for c in rsi_idx:
            gap = abs(pos[c] - tpos)
            if gap <= max_bar_gap and gap < best_gap:
                best_gap = gap
                best = c
        return best

    # Precompute ATR for magnitude filtering
    atr = _compute_atr(df, period=atr_period)

    candidates = []

    # Slide window of 3 consecutive price pivots
    for i in range(len(price_idx) - 2):
        p1_idx, p2_idx, p3_idx = price_idx[i], price_idx[i + 1], price_idx[i + 2]

        # Ensure reasonable bar separation (avoid ultra-tight clusters)
        if abs(pos[p3_idx] - pos[p1_idx]) < 2:
            continue

        # Map each price pivot to nearest RSI pivot
        r1_idx = nearest_rsi(p1_idx)
        r2_idx = nearest_rsi(p2_idx)
        r3_idx = nearest_rsi(p3_idx)

        if not (r1_idx and r2_idx and r3_idx):
            continue

        # Extract values
        p1 = float(df.at[p1_idx, price_col])
        p2 = float(df.at[p2_idx, price_col])
        p3 = float(df.at[p3_idx, price_col])
        r1 = float(df.at[r1_idx, rsi_col])
        r2 = float(df.at[r2_idx, rsi_col])
        r3 = float(df.at[r3_idx, rsi_col])

        # Check monotonicity with tolerance
        if kind == "low":
            # Bullish divergence: price descending, RSI ascending
            if require_strict_order:
                ok_price = (p2 < p1) and (p3 < p2)
                ok_rsi = (r2 > r1) and (r3 > r2)
            else:
                ok_price = (p2 <= p1 * (1 + sequence_tolerance_pct)) and (
                    p3 <= p2 * (1 + sequence_tolerance_pct)
                )
                ok_rsi = (r2 >= r1 - 0.5) and (r3 >= r2 - 0.5)
        else:  # 'high'
            # Bearish divergence: price ascending, RSI descending
            if require_strict_order:
                ok_price = (p2 > p1) and (p3 > p2)
                ok_rsi = (r2 < r1) and (r3 < r2)
            else:
                ok_price = (p2 >= p1 * (1 - sequence_tolerance_pct)) and (
                    p3 >= p2 * (1 - sequence_tolerance_pct)
                )
                ok_rsi = (r2 <= r1 + 0.5) and (r3 <= r2 + 0.5)

        if not (ok_price and ok_rsi):
            continue

        # Magnitude filter: at least one leg must exceed ATR threshold
        atr_p1 = float(atr.at[p1_idx]) if p1_idx in atr.index else np.nan
        atr_p2 = float(atr.at[p2_idx]) if p2_idx in atr.index else np.nan
        atr_p3 = float(atr.at[p3_idx]) if p3_idx in atr.index else np.nan

        span12 = abs(p1 - p2)
        span23 = abs(p2 - p3)

        mag_ok = False
        if (
            not np.isnan(atr_p1)
            and atr_p1 > 0
            and span12 >= min_magnitude_atr_mult * atr_p1
        ):
            mag_ok = True
        if (
            not np.isnan(atr_p2)
            and atr_p2 > 0
            and span23 >= min_magnitude_atr_mult * atr_p2
        ):
            mag_ok = True

        if not mag_ok:
            continue

        # Compute conviction score: (normalized price span) + (RSI delta)
        score = 0.0
        if not np.isnan(atr_p2) and atr_p2 > 0:
            score += (span12 + span23) / (atr_p2 * 2.0)

        # Add RSI contribution
        if kind == "low":
            score += ((r2 - r1) + (r3 - r2)) / 10.0  # Scale RSI delta
        else:
            score += ((r1 - r2) + (r2 - r3)) / 10.0

        candidates.append(
            {
                "kind": kind,
                "price_idx": (p1_idx, p2_idx, p3_idx),
                "rsi_idx": (r1_idx, r2_idx, r3_idx),
                "price_vals": (p1, p2, p3),
                "rsi_vals": (r1, r2, r3),
                "score": float(score),
                "meta": {
                    "span12": span12,
                    "span23": span23,
                    "atr_p1": atr_p1,
                    "atr_p2": atr_p2,
                    "atr_p3": atr_p3,
                },
            }
        )

    # Sort by score descending (highest conviction first)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def find_swing_points(
    series: pd.Series, window: int = 5
) -> Tuple[pd.Series, pd.Series]:
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
    price_col: str = "Close",
    rsi_col: str = "RSI",
    window: int = 5,
    lookback: int = 60,
    min_swing_points: int = 2,
    index_proximity_factor: int = 2,
    sequence_tolerance_pct: float = 0.002,
    rsi_sequence_tolerance: float = 0.0,
    pivot_method: str = "swing",
    zigzag_pct: float = 0.03,
    zigzag_atr_mult: float = 2.0,
    zigzag_atr_period: int = 14,
    ema_price_span: int = 5,
    ema_rsi_span: int = 5,
    use_sequence_scoring: bool = False,
    min_sequence_score: float = 1.0,
    max_bar_gap: int = 10,
    min_magnitude_atr_mult: float = 0.5,
    atr_period: int = 14,
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
        use_sequence_scoring: Enable ATR-normalized 3-point scoring (default: False)
        min_sequence_score: Minimum score to accept a 3-point sequence (default: 1.0)
        max_bar_gap: Max bar distance between price and RSI pivots for scoring (default: 10)
        min_magnitude_atr_mult: Min price move as ATR multiple for scoring (default: 0.5)
        atr_period: ATR period for magnitude filtering (default: 14)

    Returns:
        Dict with:
            - 'bullish': bool, True if bullish divergence detected
            - 'bearish': bool, True if bearish divergence detected
            - 'bullish_details': str, description of bullish divergence
            - 'bearish_details': str, description of bearish divergence
            - 'last_signal': str, 'bullish', 'bearish', or 'none'
            - 'bullish_indices': tuple of price/RSI indices or None
            - 'bearish_indices': tuple of price/RSI indices or None
            - 'bullish_score': float, conviction score (if use_sequence_scoring=True)
            - 'bearish_score': float, conviction score (if use_sequence_scoring=True)
    """
    result = {
        "bullish": False,
        "bearish": False,
        "bullish_details": "",
        "bearish_details": "",
        "last_signal": "none",
        "bullish_indices": None,
        "bearish_indices": None,
        "bullish_score": 0.0,
        "bearish_score": 0.0,
    }

    if len(df) < lookback:
        return result

    # Use only recent data
    recent_df = df.tail(lookback).copy()

    # Find swing points in price and RSI using selected method
    if pivot_method == "ema-deriv":
        # Use EMA-derivative pivot detection
        pivots_dict = ema_derivative_pivots(
            recent_df,
            price_col=price_col,
            rsi_col=rsi_col,
            price_span=ema_price_span,
            rsi_span=ema_rsi_span,
        )
        price_high_idx = pivots_dict["price_highs"]
        price_low_idx = pivots_dict["price_lows"]
        rsi_high_idx = pivots_dict["rsi_highs"]
        rsi_low_idx = pivots_dict["rsi_lows"]
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
    max_bar_gap_fallback = window * index_proximity_factor

    def nearest_by_bar(target_idx, candidates):
        """Return candidate with smallest absolute bar index distance within max_bar_gap."""
        if target_idx not in pos_map:
            return None
        tpos = pos_map[target_idx]
        viable = [
            (abs(pos_map[c] - tpos), c)
            for c in candidates
            if c in pos_map and abs(pos_map[c] - tpos) <= max_bar_gap_fallback
        ]
        if not viable:
            return None
        return min(viable)[1]

    # NEW: Use advanced 3-point sequence scoring if enabled
    if use_sequence_scoring and min_swing_points == 3:
        # Find scored 3-point sequences
        bullish_candidates = find_three_point_sequences(
            recent_df,
            price_idx=price_low_idx,
            rsi_idx=rsi_low_idx,
            kind="low",
            price_col=price_col,
            rsi_col=rsi_col,
            max_bar_gap=max_bar_gap,
            sequence_tolerance_pct=sequence_tolerance_pct,
            min_magnitude_atr_mult=min_magnitude_atr_mult,
            atr_period=atr_period,
            require_strict_order=False,
        )

        bearish_candidates = find_three_point_sequences(
            recent_df,
            price_idx=price_high_idx,
            rsi_idx=rsi_high_idx,
            kind="high",
            price_col=price_col,
            rsi_col=rsi_col,
            max_bar_gap=max_bar_gap,
            sequence_tolerance_pct=sequence_tolerance_pct,
            min_magnitude_atr_mult=min_magnitude_atr_mult,
            atr_period=atr_period,
            require_strict_order=False,
        )

        # Take best bullish candidate above threshold
        if bullish_candidates and bullish_candidates[0]["score"] >= min_sequence_score:
            best = bullish_candidates[0]
            p1_idx, p2_idx, p3_idx = best["price_idx"]
            r1_idx, r2_idx, r3_idx = best["rsi_idx"]
            p1, p2, p3 = best["price_vals"]
            r1, r2, r3 = best["rsi_vals"]

            result["bullish"] = True
            result["bullish_score"] = best["score"]
            result["bullish_details"] = (
                f"3-Point (score={best['score']:.2f}): "
                f"Price {p1:.2f}→{p2:.2f}→{p3:.2f} (descending) | "
                f"RSI {r1:.2f}→{r2:.2f}→{r3:.2f} (ascending)"
            )
            result["last_signal"] = "bullish"
            result["bullish_indices"] = (p1_idx, p2_idx, p3_idx, r1_idx, r2_idx, r3_idx)

        # Take best bearish candidate above threshold
        if bearish_candidates and bearish_candidates[0]["score"] >= min_sequence_score:
            best = bearish_candidates[0]
            p1_idx, p2_idx, p3_idx = best["price_idx"]
            r1_idx, r2_idx, r3_idx = best["rsi_idx"]
            p1, p2, p3 = best["price_vals"]
            r1, r2, r3 = best["rsi_vals"]

            result["bearish"] = True
            result["bearish_score"] = best["score"]
            result["bearish_details"] = (
                f"3-Point (score={best['score']:.2f}): "
                f"Price {p1:.2f}→{p2:.2f}→{p3:.2f} (ascending) | "
                f"RSI {r1:.2f}→{r2:.2f}→{r3:.2f} (descending)"
            )
            if result["last_signal"] == "none":
                result["last_signal"] = "bearish"
            result["bearish_indices"] = (p1_idx, p2_idx, p3_idx, r1_idx, r2_idx, r3_idx)

        # Return early if scoring found valid signals
        if result["bullish"] or result["bearish"]:
            return result

    # FALLBACK: Standard divergence detection (original logic)
    # Detect Bullish Divergence (price lower lows, RSI higher lows)
    if len(price_low_idx) >= min_swing_points and len(rsi_low_idx) >= min_swing_points:
        # Try 3-point divergence first if requested
        if min_swing_points == 3 and len(price_low_idx) >= 3 and len(rsi_low_idx) >= 3:
            p1_idx, p2_idx, p3_idx = (
                price_low_idx[-3],
                price_low_idx[-2],
                price_low_idx[-1],
            )

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
                price_desc = (p2 <= p1 * (1 - sequence_tolerance_pct)) and (
                    p3 <= p2 * (1 - sequence_tolerance_pct)
                )

                r1 = recent_df.loc[r1_idx, rsi_col]
                r2 = recent_df.loc[r2_idx, rsi_col]
                r3 = recent_df.loc[r3_idx, rsi_col]

                # RSI should be ascending with tolerance
                rsi_asc = (
                    r2 - r1 >= max(BULLISH_RSI_TOLERANCE, rsi_sequence_tolerance)
                ) and (r3 - r2 >= max(BULLISH_RSI_TOLERANCE, rsi_sequence_tolerance))

                if price_desc and rsi_asc:
                    result["bullish"] = True
                    result["bullish_details"] = (
                        f"3-Point: Price {p1:.2f}→{p2:.2f}→{p3:.2f} (descending) | "
                        f"RSI {r1:.2f}→{r2:.2f}→{r3:.2f} (ascending)"
                    )
                    result["last_signal"] = "bullish"
                    result["bullish_indices"] = (
                        p1_idx,
                        p2_idx,
                        p3_idx,
                        r1_idx,
                        r2_idx,
                        r3_idx,
                    )

        # Fall back to 2-point if 3-point not found or min_swing_points==2
        if not result["bullish"] and len(price_low_idx) >= 2 and len(rsi_low_idx) >= 2:
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
                    result["bullish"] = True
                    result["bullish_details"] = (
                        f"Price {p1:.2f}→{p2:.2f} (LL) | RSI {r1:.2f}→{r2:.2f} (HL)"
                    )
                    result["last_signal"] = "bullish"
                    result["bullish_indices"] = (p1_idx, p2_idx, r1_idx, r2_idx)

    # Detect Bearish Divergence (price higher highs, RSI lower highs)
    if (
        len(price_high_idx) >= min_swing_points
        and len(rsi_high_idx) >= min_swing_points
    ):
        # Try 3-point divergence first if requested
        if (
            min_swing_points == 3
            and len(price_high_idx) >= 3
            and len(rsi_high_idx) >= 3
        ):
            p1_idx, p2_idx, p3_idx = (
                price_high_idx[-3],
                price_high_idx[-2],
                price_high_idx[-1],
            )

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
                price_asc = (p2 >= p1 * (1 + sequence_tolerance_pct)) and (
                    p3 >= p2 * (1 + sequence_tolerance_pct)
                )

                r1 = recent_df.loc[r1_idx, rsi_col]
                r2 = recent_df.loc[r2_idx, rsi_col]
                r3 = recent_df.loc[r3_idx, rsi_col]

                # RSI should be descending with tolerance
                rsi_desc = (
                    r1 - r2 >= max(BEARISH_RSI_TOLERANCE, rsi_sequence_tolerance)
                ) and (r2 - r3 >= max(BEARISH_RSI_TOLERANCE, rsi_sequence_tolerance))

                if price_asc and rsi_desc:
                    result["bearish"] = True
                    result["bearish_details"] = (
                        f"3-Point: Price {p1:.2f}→{p2:.2f}→{p3:.2f} (ascending) | "
                        f"RSI {r1:.2f}→{r2:.2f}→{r3:.2f} (descending)"
                    )
                    if result["last_signal"] == "none":
                        result["last_signal"] = "bearish"
                    result["bearish_indices"] = (
                        p1_idx,
                        p2_idx,
                        p3_idx,
                        r1_idx,
                        r2_idx,
                        r3_idx,
                    )

        # Fall back to 2-point if 3-point not found or min_swing_points==2
        if (
            not result["bearish"]
            and len(price_high_idx) >= 2
            and len(rsi_high_idx) >= 2
        ):
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
                    result["bearish"] = True
                    result["bearish_details"] = (
                        f"Price {p1:.2f}→{p2:.2f} (HH) | RSI {r1:.2f}→{r2:.2f} (LH)"
                    )
                    if result["last_signal"] == "none":
                        result["last_signal"] = "bearish"
                    result["bearish_indices"] = (p1_idx, p2_idx, r1_idx, r2_idx)

    return result


def check_breakout_occurred(
    df: pd.DataFrame,
    divergence_idx: pd.Timestamp,
    divergence_type: str,
    threshold: float = 0.05,
    price_col: str = "Close",
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

    if divergence_type == "bullish":
        # Bullish divergence: check if price already rallied past threshold
        breakout_price = divergence_price * (1 + threshold)
        return current_price >= breakout_price

    elif divergence_type == "bearish":
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
    price_col: str = "Close",
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

    recent_data = df.iloc[div_loc : div_loc + lookback_window + 1]
    if len(recent_data) < 2:
        return False

    divergence_price = df.loc[divergence_idx, price_col]
    current_close = df[price_col].iloc[-1]

    if divergence_type == "bullish":
        # Check for failed bullish attempt
        attempted_high = recent_data["High"].max()
        attempt_target = divergence_price * (1 + attempt_threshold)
        failed_level = divergence_price * (1 + reversal_threshold)

        # Price tried to rally (reached attempt threshold) but closed back low
        if attempted_high >= attempt_target and current_close < failed_level:
            return True

    elif divergence_type == "bearish":
        # Check for failed bearish attempt
        attempted_low = recent_data["Low"].min()
        attempt_target = divergence_price * (1 - attempt_threshold)
        failed_level = divergence_price * (1 - reversal_threshold)

        # Price tried to drop (reached attempt threshold) but closed back high
        if attempted_low <= attempt_target and current_close > failed_level:
            return True

    return False
