# Quick Reference Guide

## Setup (First Time)

```powershell
# Navigate to project
cd C:\Users\User\Documents\StockCharts

# Create conda environment
conda create -n stockcharts python=3.12 -y
conda activate stockcharts

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

## Daily Workflow

### Activate Environment
```powershell
conda activate stockcharts
```

### Generate Single Chart
```powershell
# Daily chart for AAPL
python scripts\plot_heiken_ashi.py --ticker AAPL

# Weekly chart for MSFT (last 6 months)
python scripts\plot_heiken_ashi.py --ticker MSFT --interval 1wk --start 2024-04-01

# Custom output location
python scripts\plot_heiken_ashi.py --ticker TSLA --output charts\tesla_daily.png
```

### Screen for Opportunities

```powershell
# Find all bullish daily setups
python scripts\screen_nasdaq.py --color green --interval 1d

# Find bearish weekly setups
python scripts\screen_nasdaq.py --color red --interval 1wk

# Quick scan (20 tickers)
python scripts\screen_nasdaq.py --color green --limit 20

# Export to Excel/CSV
python scripts\screen_nasdaq.py --color all --output results\today_scan.csv
```

## Common Scenarios

### Morning Routine: Check Overnight Moves
```powershell
python scripts\screen_nasdaq.py --color all --output results\morning_scan.csv
```

### Weekly Analysis
```powershell
python scripts\screen_nasdaq.py --color green --interval 1wk --output results\weekly_bullish.csv
python scripts\screen_nasdaq.py --color red --interval 1wk --output results\weekly_bearish.csv
```

### Generate Charts for Watchlist
```powershell
python scripts\plot_heiken_ashi.py --ticker AAPL --output charts\AAPL.png
python scripts\plot_heiken_ashi.py --ticker MSFT --output charts\MSFT.png
python scripts\plot_heiken_ashi.py --ticker GOOGL --output charts\GOOGL.png
python scripts\plot_heiken_ashi.py --ticker NVDA --output charts\NVDA.png
```

## Programmatic Usage (Python)

```python
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.screener import screen_nasdaq

# Fetch and compute HA for single ticker
df = fetch_ohlc('AAPL', interval='1d')
ha = heiken_ashi(df)
print(ha.tail())

# Screen programmatically
results = screen_nasdaq(color_filter='green', interval='1d', limit=50)
for r in results:
    print(f"{r.ticker}: {r.color} candle @ {r.ha_close:.2f}")
```

## Tips

1. **Faster Screening**: Reduce delay between API calls
   ```powershell
   python scripts\screen_nasdaq.py --color green --delay 0.2
   ```

2. **Quiet Mode**: Suppress progress output
   ```powershell
   python scripts\screen_nasdaq.py --color green --quiet
   ```

3. **Test First**: Use `--limit 10` when testing new settings

4. **Batch Charts**: Create a PowerShell loop
   ```powershell
   $tickers = @('AAPL', 'MSFT', 'GOOGL', 'NVDA')
   foreach ($t in $tickers) {
       python scripts\plot_heiken_ashi.py --ticker $t --output "charts\$t.png"
   }
   ```

## Troubleshooting

### "ModuleNotFoundError: No module named 'stockcharts'"
```powershell
pip install -e .
```

### "No data returned for ticker"
- Check ticker symbol spelling
- Verify market hours (or use historical dates)
- Some delisted stocks have no data

### Slow screening
- Reduce `--delay` (risk: API throttling)
- Use `--limit` for testing
- Consider screening at off-peak hours

### Monthly data issues
- Monthly candles require completed months
- Partial month = incomplete data
- Use daily or weekly for most recent signals
