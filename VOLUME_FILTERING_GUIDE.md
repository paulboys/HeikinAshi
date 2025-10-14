# Volume Filtering Guide

The `--min-volume` parameter filters out low-volume stocks to ensure sufficient liquidity for trading.

## Why Volume Matters

**Low volume stocks** have:
- ❌ Wide bid-ask spreads (high slippage)
- ❌ Difficulty entering/exiting positions
- ❌ More price manipulation risk
- ❌ Harder to scale positions

**High volume stocks** have:
- ✅ Tight bid-ask spreads (low slippage)
- ✅ Easy entry/exit
- ✅ More reliable price action
- ✅ Better for larger positions

---

## Recommended Volume Thresholds

### By Trading Style

| Trading Style | Minimum Volume | Command Example |
|--------------|----------------|-----------------|
| **Day Trader** | 1,000,000+ shares | `--min-volume 1000000` |
| **Swing Trader** | 500,000+ shares | `--min-volume 500000` |
| **Position Trader** | 300,000+ shares | `--min-volume 300000` |
| **Conservative** | 1,000,000+ shares | `--min-volume 1000000` |

### By Account Size

| Account Size | Minimum Volume | Reasoning |
|-------------|----------------|-----------|
| Under $10K | 300K+ | Can trade smaller positions |
| $10K - $50K | 500K+ | Need decent liquidity |
| $50K - $250K | 1M+ | Larger positions need volume |
| $250K+ | 2M+ | Significant size needs high liquidity |

---

## Usage Examples

### Swing Trading (Recommended: 500K)
```bash
# Find green reversals with minimum 500K daily volume
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 500000 --limit 100 --output swing_trades.csv
```

### Day Trading (Recommended: 1M+)
```bash
# High volume stocks only for day trading
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 5d --min-volume 1000000 --limit 100
```

### Conservative Filter (1M+)
```bash
# Only highly liquid stocks
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 1000000 --limit 200
```

### Very High Volume (5M+)
```bash
# Institutional-grade liquidity
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 5000000 --limit 50
```

### No Volume Filter
```bash
# Include all stocks (not recommended for trading)
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --limit 100
```

---

## Complete Command: 100 Stocks with Volume Filter

**Recommended for Swing Trading:**
```bash
# Screen 100 stocks, daily candles, 3 months data, minimum 500K volume
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 500000 --limit 100 --output green_reversals.csv

# Generate charts
python scripts\plot_reversals.py --input green_reversals.csv --output charts/reversals
```

**One-liner (Windows PowerShell):**
```powershell
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 500000 --limit 100 --output green_reversals.csv; python scripts\plot_reversals.py --input green_reversals.csv --output charts/reversals
```

---

## How Volume is Calculated

The screener calculates **average volume** using:
- **Window**: Last 20 periods (or all available if less)
- **Metric**: Mean of Volume column from OHLCV data

Example:
- Daily candles: Average of last 20 days
- Weekly candles: Average of last 20 weeks
- Monthly candles: Average of last 20 months

---

## Volume in Output

### Terminal Display
Shows average volume with comma formatting:
```
Ticker     Color    Previous   Changed    Avg Volume      HA_Open      HA_Close     Last Date
============================================================================================
AAON       green    red        ✓          1,112,605       101.63       102.01       2025-10-13
ABVE       green    red        ✓          5,558,313       4.08         4.10         2025-10-14
```

### CSV Export
Includes `avg_volume` column:
```csv
ticker,color,previous_color,color_changed,avg_volume,ha_open,ha_close,last_date,interval
AAON,green,red,True,1112605.0,101.63,102.01,2025-10-13,1d
ABVE,green,red,True,5558313.0,4.08,4.10,2025-10-14,1d
```

---

## Filtering Strategy

### Multi-Level Filter
Progressively tighten volume requirements:

```bash
# Step 1: Screen with 500K minimum
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 500000 --limit 200 --output green_500k.csv

# Step 2: Higher volume subset (1M+)
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 1000000 --limit 200 --output green_1m.csv

# Step 3: Highest volume (5M+)
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 5000000 --limit 200 --output green_5m.csv
```

### Combined with Weekly Confirmation
```bash
# Daily reversals with volume filter
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 500000 --output daily_green.csv

# Weekly trend confirmation (same volume)
python scripts\screen_nasdaq.py --color green --period 1wk --lookback 6mo --min-volume 500000 --output weekly_green.csv

# Find tickers in both lists (strongest candidates)
```

---

## Tips

1. **Start Conservative**: Use 1M minimum volume when learning
2. **Scale Down**: Reduce to 500K as you gain experience
3. **Never Go Below 100K**: High risk of manipulation and slippage
4. **Check Multiple Timeframes**: Volume should be consistent across daily/weekly
5. **Avoid Penny Stocks**: Often have fake volume from market makers

---

## Common Volume Thresholds

| Shares/Day | Category | Suitable For |
|-----------|----------|--------------|
| < 100K | Very Low | ❌ Avoid |
| 100K - 300K | Low | ⚠️ Experienced only |
| 300K - 500K | Moderate | ✅ Small positions |
| 500K - 1M | Good | ✅ Swing trading |
| 1M - 5M | High | ✅ Day trading |
| 5M+ | Very High | ✅ All strategies |

---

## Quick Reference

**Conservative (1M minimum):**
```bash
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 1000000 --limit 100
```

**Balanced (500K minimum):**
```bash
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 500000 --limit 100
```

**Aggressive (300K minimum):**
```bash
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --min-volume 300000 --limit 100
```
