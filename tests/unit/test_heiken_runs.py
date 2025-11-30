"""Unit tests for Heiken Ashi run length analysis."""

import pandas as pd

from stockcharts.indicators.heiken_runs import (
    _compute_all_run_lengths,
    _compute_percentile,
    compute_ha_run_stats,
)


def test_compute_ha_run_stats_empty_df():
    """Test handling of empty DataFrame."""
    df = pd.DataFrame(columns=["HA_Open", "HA_Close"])
    stats = compute_ha_run_stats(df)

    assert stats["run_length"] == 0
    assert stats["run_percentile"] == 0.0
    assert stats["run_color"] == "none"
    assert stats["total_runs"] == 0


def test_compute_ha_run_stats_single_candle():
    """Test single candle returns run_length=1, percentile=100."""
    # Green candle
    df = pd.DataFrame({"HA_Open": [100.0], "HA_Close": [101.0]})
    stats = compute_ha_run_stats(df)

    assert stats["run_length"] == 1
    assert stats["run_percentile"] == 100.0
    assert stats["run_color"] == "green"
    assert stats["total_runs"] == 1

    # Red candle
    df = pd.DataFrame({"HA_Open": [100.0], "HA_Close": [99.0]})
    stats = compute_ha_run_stats(df)

    assert stats["run_length"] == 1
    assert stats["run_percentile"] == 100.0
    assert stats["run_color"] == "red"
    assert stats["total_runs"] == 1


def test_compute_ha_run_stats_all_same_color():
    """Test all candles same color results in single run."""
    # All green
    df = pd.DataFrame(
        {
            "HA_Open": [100, 101, 102, 103, 104],
            "HA_Close": [101, 102, 103, 104, 105],
        }
    )
    stats = compute_ha_run_stats(df)

    assert stats["run_length"] == 5
    assert stats["run_percentile"] == 100.0
    assert stats["run_color"] == "green"
    assert stats["total_runs"] == 1


def test_compute_ha_run_stats_alternating_colors():
    """Test alternating colors creates all runs of length 1."""
    df = pd.DataFrame(
        {
            "HA_Open": [100, 101, 102, 103, 104],
            "HA_Close": [101, 100, 103, 102, 105],  # g, r, g, r, g
        }
    )
    stats = compute_ha_run_stats(df)

    assert stats["run_length"] == 1
    assert stats["run_color"] == "green"
    # All 5 runs have length 1, so percentile = 5/5 = 100
    assert stats["run_percentile"] == 100.0
    assert stats["total_runs"] == 5


def test_compute_ha_run_stats_mixed_runs():
    """Test mixed run lengths with realistic scenario."""
    # Pattern: 3 green, 2 red, 4 green, 1 red, 2 green
    df = pd.DataFrame(
        {
            "HA_Open": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111],
            "HA_Close": [
                101,
                102,
                103,  # 3 green
                103,
                102,  # 2 red
                106,
                107,
                108,
                109,  # 4 green
                108,  # 1 red
                111,
                112,  # 2 green (current)
            ],
        }
    )
    stats = compute_ha_run_stats(df)

    # Current run: 2 green
    assert stats["run_length"] == 2
    assert stats["run_color"] == "green"
    assert stats["total_runs"] == 5

    # Distribution: [3, 2, 4, 1, 2]
    # Runs with length <= 2: [2, 1, 2] = 3 out of 5
    # Percentile = 3/5 * 100 = 60%
    assert stats["run_percentile"] == 60.0


def test_compute_ha_run_stats_rare_long_run():
    """Test long current run results in high percentile."""
    # Pattern: 1 green, 2 red, 1 green, 10 red (current)
    df = pd.DataFrame(
        {
            "HA_Open": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113],
            "HA_Close": [
                101,  # 1 green
                101,
                100,  # 2 red
                104,  # 1 green
                103,
                102,
                101,
                100,
                99,
                98,
                97,
                96,
                95,
                94,  # 10 red (current)
            ],
        }
    )
    stats = compute_ha_run_stats(df)

    assert stats["run_length"] == 10
    assert stats["run_color"] == "red"
    assert stats["total_runs"] == 4

    # Distribution: [1, 2, 1, 10]
    # Runs with length <= 10: all 4
    # Percentile = 4/4 * 100 = 100%
    assert stats["run_percentile"] == 100.0


def test_compute_ha_run_stats_common_short_run():
    """Test short current run after many longer runs."""
    # Pattern: 5 green, 8 red, 10 green, 2 red (current)
    # Need to construct HA_Open and HA_Close such that colors follow the pattern
    ha_open = (
        [100, 101, 102, 103, 104]  # 5 values
        + [110, 109, 108, 107, 106, 105, 104, 103]  # 8 values
        + [95, 96, 97, 98, 99, 100, 101, 102, 103, 104]  # 10 values
        + [112, 111]  # 2 values
    )
    ha_close = (
        [101, 102, 103, 104, 105]  # 5 green (close > open)
        + [109, 108, 107, 106, 105, 104, 103, 102]  # 8 red (close < open)
        + [96, 97, 98, 99, 100, 101, 102, 103, 104, 105]  # 10 green (close > open)
        + [111, 110]  # 2 red (close < open) - current
    )

    df = pd.DataFrame({"HA_Open": ha_open, "HA_Close": ha_close})
    stats = compute_ha_run_stats(df)

    assert stats["run_length"] == 2
    assert stats["run_color"] == "red"
    assert stats["total_runs"] == 4

    # Distribution: [5, 8, 10, 2]
    # Runs with length <= 2: [2] = 1 out of 4
    # Percentile = 1/4 * 100 = 25%
    assert stats["run_percentile"] == 25.0


def test_compute_all_run_lengths():
    """Test run length extraction from binary series."""
    colors = pd.Series([1, 1, 1, 0, 0, 1, 1, 1, 1, 0])
    # Pattern: 3 green, 2 red, 4 green, 1 red
    expected = [3, 2, 4, 1]

    result = _compute_all_run_lengths(colors)
    assert result == expected


def test_compute_all_run_lengths_single_value():
    """Test single value series."""
    colors = pd.Series([1])
    result = _compute_all_run_lengths(colors)
    assert result == [1]


def test_compute_all_run_lengths_empty():
    """Test empty series."""
    colors = pd.Series([], dtype=int)
    result = _compute_all_run_lengths(colors)
    assert result == []


def test_compute_percentile():
    """Test percentile calculation."""
    # Value 3 in distribution [1, 2, 3, 4, 5]
    # Values <= 3: [1, 2, 3] = 3 out of 5 = 60%
    assert _compute_percentile(3, [1, 2, 3, 4, 5]) == 60.0

    # Value 10 in distribution [1, 2, 3]
    # All values <= 10, so 3/3 = 100%
    assert _compute_percentile(10, [1, 2, 3]) == 100.0

    # Value 1 in distribution [1, 2, 3, 4, 5]
    # Only 1 <= 1, so 1/5 = 20%
    assert _compute_percentile(1, [1, 2, 3, 4, 5]) == 20.0

    # Value 0 in distribution [1, 2, 3]
    # No values <= 0, so 0/3 = 0%
    assert _compute_percentile(0, [1, 2, 3]) == 0.0


def test_compute_percentile_ties():
    """Test percentile with duplicate values."""
    # Distribution: [1, 2, 2, 3, 3, 3]
    # For value 2: values <= 2 are [1, 2, 2] = 3/6 = 50%
    assert _compute_percentile(2, [1, 2, 2, 3, 3, 3]) == 50.0

    # For value 3: values <= 3 are all 6 = 6/6 = 100%
    assert _compute_percentile(3, [1, 2, 2, 3, 3, 3]) == 100.0


def test_compute_percentile_empty_distribution():
    """Test percentile with empty distribution."""
    assert _compute_percentile(5, []) == 0.0


def test_ha_run_stats_with_equal_candles():
    """Test candles where HA_Close == HA_Open (treated as green)."""
    df = pd.DataFrame(
        {
            "HA_Open": [100, 101, 102, 103],
            "HA_Close": [100, 101, 103, 102],  # equal, equal, green, red
        }
    )
    stats = compute_ha_run_stats(df)

    # First two are "green" (HA_Close >= HA_Open with >=)
    # Then one more green, then red
    # Pattern: 3 green, 1 red
    assert stats["run_length"] == 1
    assert stats["run_color"] == "red"
    assert stats["total_runs"] == 2
    # Distribution: [3, 1]; current is 1; runs <= 1 are [1] = 1/2 = 50%
    assert stats["run_percentile"] == 50.0
