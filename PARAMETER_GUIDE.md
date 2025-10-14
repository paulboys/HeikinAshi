# Parameter Guide: Correct Usage

## ✅ Corrected Parameter Terminology

The parameters have been updated to use clearer, more accurate terminology:

### **`--period`** (Aggregation Period)
**What it controls:** How data is grouped/aggregated
**Options:**
- `1d` - Daily candles (default)
- `1wk` - Weekly candles
- `1mo` - Monthly candles

**Think of it as:** "What size candles do I want to see?"

### **`--lookback`** (Time Window)
**What it controls:** How far back to fetch data
**Options:**
- `5d` - 5 days
- `1mo` - 1 month
- `3mo` - 3 months
- `6mo` - 6 months
- `1y` - 1 year (default if not specified)
- `2y` - 2 years
- `5y` - 5 years

**Think of it as:** "How much history do I want to analyze?"

### **`--start` and `--end`** (Date Range)
**What it controls:** Explicit date boundaries
**Format:** YYYY-MM-DD
**Example:** `--start 2024-01-01 --end 2025-10-14`

**Cannot be used together with `--lookback`**

---

## 📊 Correct Commands

### Daily Candles with 3 Months of Data (Swing Trading)
```bash
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --limit 100 --output green_reversals.csv
```
- **period=1d**: Show me daily candles
- **lookback=3mo**: Go back 3 months
- Result: ~65 daily candles over 3 months

### Weekly Candles with 1 Year of Data (Position Trading)
```bash
python scripts\screen_nasdaq.py --color green --changed-only --period 1wk --lookback 1y --limit 100
```
- **period=1wk**: Show me weekly candles
- **lookback=1y**: Go back 1 year
- Result: ~52 weekly candles over 1 year

### Monthly Candles with 5 Years of Data (Long-term)
```bash
python scripts\screen_nasdaq.py --color green --changed-only --period 1mo --lookback 5y --limit 50
```
- **period=1mo**: Show me monthly candles
- **lookback=5y**: Go back 5 years
- Result: ~60 monthly candles over 5 years

### Custom Date Range with Daily Candles
```bash
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --start 2024-01-01 --end 2025-10-14 --limit 100
```
- **period=1d**: Show me daily candles
- **start/end**: Exact date range
- Result: All trading days between those dates

---

## 🎯 Trading Style Recommendations

### Day Trader
```bash
# Daily candles, last 5 days
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 5d --limit 100

# Daily candles, last month
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 1mo --limit 100
```

### Swing Trader (2-10 day holds)
```bash
# Daily candles, 3 months of data (RECOMMENDED)
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --limit 100

# Daily candles, 6 months for better context
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 6mo --limit 100

# Weekly candles for trend confirmation
python scripts\screen_nasdaq.py --color green --changed-only --period 1wk --lookback 6mo --limit 100
```

### Position Trader (weeks to months)
```bash
# Weekly candles, 1 year
python scripts\screen_nasdaq.py --color green --changed-only --period 1wk --lookback 1y --limit 100

# Weekly candles, 2-5 years for long-term trends
python scripts\screen_nasdaq.py --color green --changed-only --period 1wk --lookback 5y --limit 50

# Monthly candles for major trends
python scripts\screen_nasdaq.py --color green --changed-only --period 1mo --lookback 5y --limit 50
```

---

## 🔄 Multi-Timeframe Analysis

Best practice: Use multiple timeframes together

```bash
# Step 1: Weekly trend (bigger picture)
python scripts\screen_nasdaq.py --color green --changed-only --period 1wk --lookback 1y --output weekly_green.csv

# Step 2: Daily for entry timing
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --output daily_green.csv

# Step 3: Generate charts
python scripts\plot_reversals.py --input daily_green.csv --output charts/daily_reversals
```

---

## ❌ Common Mistakes

### WRONG: Using short lookback
```bash
# Only gets 1 candle - can't detect color change!
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 1d
```

### WRONG: Mixing lookback with start/end
```bash
# Error: Can't use both
python scripts\screen_nasdaq.py --lookback 3mo --start 2024-01-01 --end 2025-10-14
```

### CORRECT: Minimum 2 candles needed
```bash
# At least 5 days for daily candles
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 5d --limit 100
```

---

## 📝 Full Command Reference

### Minimal Command (Uses defaults)
```bash
python scripts\screen_nasdaq.py --color green --changed-only --limit 100
# Uses: period=1d, lookback=1y (default)
```

### Full Command with All Options
```bash
python scripts\screen_nasdaq.py \
  --color green \
  --changed-only \
  --period 1d \
  --lookback 3mo \
  --limit 100 \
  --delay 0.5 \
  --output green_reversals.csv \
  --debug
```

### Alternative with Date Range
```bash
python scripts\screen_nasdaq.py \
  --color green \
  --changed-only \
  --period 1wk \
  --start 2024-01-01 \
  --end 2025-10-14 \
  --limit 100 \
  --output weekly_reversals.csv
```

---

## 🚀 Quick Start: 100 Stocks Red-to-Green

**Swing Trading Setup (Recommended):**
```bash
# Screen for reversals
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --limit 100 --output green_reversals.csv

# Generate charts
python scripts\plot_reversals.py --input green_reversals.csv --output charts/reversals
```

**One-liner (Windows PowerShell):**
```powershell
python scripts\screen_nasdaq.py --color green --changed-only --period 1d --lookback 3mo --limit 100 --output green_reversals.csv; python scripts\plot_reversals.py --input green_reversals.csv --output charts/reversals
```
