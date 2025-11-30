"""Heiken Ashi consecutive run length analysis.

Computes the most recent consecutive same-color candle run length
and ranks it as a percentile against all historical runs for the same ticker.
"""

from __future__ import annotations

import pandas as pd


def compute_ha_run_stats(ha_df: pd.DataFrame) -> dict[str, float | int | str]:
    """Compute Heikin Ashi run statistics for the most recent candle sequence.

    Analyzes the DataFrame to find:
    1. The current consecutive run length (same color candles)
    2. All historical run lengths in the dataset
    3. The percentile rank of the current run

    Parameters
    ----------
    ha_df : pd.DataFrame
        Heiken Ashi DataFrame with columns HA_Open, HA_Close
        Index should be datetime (chronologically ordered)

    Returns:
    --------
    dict with keys:
        - run_length: int - number of consecutive same-color candles ending at latest
        - run_percentile: float - percentile rank (0-100) of current run vs historical
        - run_color: str - "green" or "red" for the current run
        - total_runs: int - total number of runs found in history

    Examples:
    ---------
    >>> ha_df = pd.DataFrame({
    ...     'HA_Open': [100, 101, 102, 103, 104],
    ...     'HA_Close': [101, 102, 103, 102, 101]  # green, green, green, red, red
    ... })
    >>> stats = compute_ha_run_stats(ha_df)
    >>> stats['run_length']
    2
    >>> stats['run_color']
    'red'
    """
    if ha_df.empty:
        return {
            "run_length": 0,
            "run_percentile": 0.0,
            "run_color": "none",
            "total_runs": 0,
        }

    if len(ha_df) == 1:
        # Single candle: run length is 1, percentile is 100 (only run)
        color = "green" if ha_df.iloc[0]["HA_Close"] >= ha_df.iloc[0]["HA_Open"] else "red"
        return {
            "run_length": 1,
            "run_percentile": 100.0,
            "run_color": color,
            "total_runs": 1,
        }

    # Determine color for each candle (green if HA_Close >= HA_Open)
    colors = (ha_df["HA_Close"] >= ha_df["HA_Open"]).astype(int)  # 1=green, 0=red

    # Find all run lengths by detecting color changes
    run_lengths = _compute_all_run_lengths(colors)

    # Current run is the last one
    current_run_length = run_lengths[-1]
    current_color = "green" if colors.iloc[-1] == 1 else "red"

    # Compute percentile: what percent of all runs are <= current run length
    # Use inclusive count (runs with length <= current) / total runs
    percentile = _compute_percentile(current_run_length, run_lengths)

    return {
        "run_length": int(current_run_length),
        "run_percentile": round(percentile, 2),
        "run_color": current_color,
        "total_runs": len(run_lengths),
    }


def _compute_all_run_lengths(colors: pd.Series) -> list[int]:
    """Extract all consecutive run lengths from a binary color series.

    Parameters
    ----------
    colors : pd.Series
        Binary series where 1=green, 0=red

    Returns:
    --------
    list[int]
        List of run lengths in chronological order

    Examples:
    ---------
    >>> colors = pd.Series([1, 1, 1, 0, 0, 1])  # 3 green, 2 red, 1 green
    >>> _compute_all_run_lengths(colors)
    [3, 2, 1]
    """
    if len(colors) == 0:
        return []

    run_lengths = []
    current_length = 1
    prev_color = colors.iloc[0]

    for i in range(1, len(colors)):
        if colors.iloc[i] == prev_color:
            current_length += 1
        else:
            run_lengths.append(current_length)
            current_length = 1
            prev_color = colors.iloc[i]

    # Don't forget the final run
    run_lengths.append(current_length)

    return run_lengths


def _compute_percentile(value: int, distribution: list[int]) -> float:
    """Compute percentile rank of a value within a distribution.

    Uses the inclusive definition: (count of values <= target) / total * 100

    Parameters
    ----------
    value : int
        The value to rank
    distribution : list[int]
        All values in the distribution

    Returns:
    --------
    float
        Percentile rank (0-100)

    Examples:
    ---------
    >>> _compute_percentile(3, [1, 2, 3, 4, 5])
    60.0
    >>> _compute_percentile(10, [1, 2, 3])
    100.0
    """
    if not distribution:
        return 0.0

    count_lte = sum(1 for v in distribution if v <= value)
    return (count_lte / len(distribution)) * 100.0
