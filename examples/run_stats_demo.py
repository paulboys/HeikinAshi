"""Manual test script to demonstrate Heiken Ashi run statistics feature.

Run this to see example output with run_length and run_percentile.
"""

import pandas as pd

from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.indicators.heiken_runs import compute_ha_run_stats

# Create sample OHLC data with a clear pattern
dates = pd.date_range("2024-01-01", periods=20, freq="D")
df = pd.DataFrame(
    {
        # Pattern: Uptrend (5 days), downtrend (8 days), uptrend (7 days)
        "Open": [
            100,
            101,
            102,
            103,
            104,
            110,
            109,
            108,
            107,
            106,
            105,
            104,
            103,
            95,
            96,
            97,
            98,
            99,
            100,
            101,
        ],
        "High": [
            102,
            103,
            104,
            105,
            106,
            111,
            110,
            109,
            108,
            107,
            106,
            105,
            104,
            97,
            98,
            99,
            100,
            101,
            102,
            103,
        ],
        "Low": [
            98,
            99,
            100,
            101,
            102,
            108,
            107,
            106,
            105,
            104,
            103,
            102,
            101,
            93,
            94,
            95,
            96,
            97,
            98,
            99,
        ],
        "Close": [
            101,
            102,
            103,
            104,
            105,
            109,
            108,
            107,
            106,
            105,
            104,
            103,
            102,
            96,
            97,
            98,
            99,
            100,
            101,
            102,
        ],
    },
    index=dates,
)

# Compute Heiken Ashi
ha = heiken_ashi(df)

# Compute run statistics
stats = compute_ha_run_stats(ha)

print("=" * 60)
print("Heiken Ashi Run Statistics Demo")
print("=" * 60)
print(f"\nAnalyzing {len(ha)} candles from {ha.index[0].date()} to {ha.index[-1].date()}")
print("\nCurrent Run:")
print(f"  Color:       {stats['run_color']}")
print(f"  Length:      {stats['run_length']} consecutive candles")
print(f"  Percentile:  {stats['run_percentile']:.1f}%")
print("\nHistorical Context:")
print(f"  Total runs:  {stats['total_runs']}")
print("\nInterpretation:")
if stats["run_percentile"] >= 90:
    print(f"  🔥 This is an EXCEPTIONAL {stats['run_color']} run (top 10%)")
elif stats["run_percentile"] >= 75:
    print(f"  📈 This is a STRONG {stats['run_color']} run (top 25%)")
elif stats["run_percentile"] >= 50:
    print(f"  ✓ This is an ABOVE AVERAGE {stats['run_color']} run")
elif stats["run_percentile"] >= 25:
    print(f"  → This is a TYPICAL {stats['run_color']} run")
else:
    print(f"  ↓ This is a SHORT {stats['run_color']} run (bottom 25%)")

print("\n" + "=" * 60)
print("\nLast 5 Heiken Ashi Candles:")
print(ha[["HA_Open", "HA_Close"]].tail(5).to_string())
print("\n" + "=" * 60)
