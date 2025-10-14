# Trading Style Guide: Time Window Parameters

This guide shows how to use the `--period`, `--start`, and `--end` parameters for different trading styles.

## Quick Reference

### Parameter Options

**`--period`**: Pre-defined time windows (easier to use)
- `5d` - 5 days
- `1mo` - 1 month
- `3mo` - 3 months (recommended for swing traders)
- `6mo` - 6 months
- `1y` - 1 year (default if nothing specified)
- `2y` - 2 years
- `5y` - 5 years (good for position traders)
- `ytd` - Year to date
- `max` - Maximum available data

**`--start` and `--end`**: Custom date range (format: YYYY-MM-DD)
- Use together for precise date ranges
- Cannot be used with `--period`

## Trading Style Recommendations

### 🔥 Day Trader
**Goal**: Catch intraday to multi-day moves

```bash
# Short-term reversals (5 days of data)
python scripts\screen_nasdaq.py --color green --changed-only --period 5d --limit 100

# Last month of data
python scripts\screen_nasdaq.py --color green --changed-only --period 1mo --limit 100
```

### 📈 Swing Trader (Recommended Settings)
**Goal**: Hold positions for 2-10 days

```bash
# 3 months of daily data (BEST for swing trading)
python scripts\screen_nasdaq.py --color green --changed-only --period 3mo --interval 1d

# 6 months of data for better context
python scripts\screen_nasdaq.py --color green --changed-only --period 6mo --interval 1d --limit 200

# Weekly chart with 6 months (trend confirmation)
python scripts\screen_nasdaq.py --color green --changed-only --period 6mo --interval 1wk --limit 100
```

### 🎯 Position Trader
**Goal**: Hold positions for weeks to months

```bash
# 1 year of weekly data
python scripts\screen_nasdaq.py --color green --changed-only --period 1y --interval 1wk

# 2-5 years of data for long-term trends
python scripts\screen_nasdaq.py --color green --changed-only --period 5y --interval 1wk --limit 100

# Monthly charts with 5 years
python scripts\screen_nasdaq.py --color green --changed-only --period 5y --interval 1mo
```

### 📅 Custom Date Range
**Goal**: Analyze specific historical periods

```bash
# Analyze Q4 2024
python scripts\screen_nasdaq.py --color green --changed-only --start 2024-10-01 --end 2024-12-31 --limit 100

# Last year specific dates
python scripts\screen_nasdaq.py --color green --changed-only --start 2024-01-01 --end 2025-10-14 --interval 1wk
```

## Multi-Timeframe Analysis

For best results, use multiple timeframes:

```bash
# 1. Check weekly trend (bigger picture)
python scripts\screen_nasdaq.py --color green --changed-only --period 1y --interval 1wk --output weekly_reversals.csv

# 2. Check daily for entry timing
python scripts\screen_nasdaq.py --color green --changed-only --period 3mo --interval 1d --output daily_reversals.csv

# 3. Find stocks that are green on BOTH timeframes (highest probability)
```

## Examples by Use Case

### Find Fresh Reversals (Just Happened)
```bash
# Default 1 year, but looking at most recent candle
python scripts\screen_nasdaq.py --color green --changed-only --limit 100
```

### Backtest Historical Periods
```bash
# What stocks reversed in January 2024?
python scripts\screen_nasdaq.py --color green --changed-only --start 2024-01-01 --end 2024-01-31 --limit 500
```

### Maximum Data for Strong Trends
```bash
# All available data
python scripts\screen_nasdaq.py --color green --changed-only --period max --interval 1wk --limit 50
```

## Parameter Rules

❌ **INVALID** - Cannot use both:
```bash
python scripts\screen_nasdaq.py --period 3mo --start 2024-01-01
```

✅ **VALID** - Use one or the other:
```bash
python scripts\screen_nasdaq.py --period 3mo
python scripts\screen_nasdaq.py --start 2024-01-01 --end 2025-10-14
```

✅ **VALID** - Default to 1 year if nothing specified:
```bash
python scripts\screen_nasdaq.py --color green --changed-only --limit 100
```

## Output Files

Save results for later analysis:
```bash
python scripts\screen_nasdaq.py --color green --changed-only --period 3mo --output swing_reversals_3mo.csv
python scripts\screen_nasdaq.py --color green --changed-only --period 6mo --output swing_reversals_6mo.csv
```

Then generate charts:
```bash
python scripts\plot_reversals.py --input swing_reversals_3mo.csv --output charts/3mo_reversals
```
