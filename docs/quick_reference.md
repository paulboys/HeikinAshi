# Quick Reference

## Core Commands
```
stockcharts-screen --color green --period 1d
stockcharts-screen --color red --period 1wk
stockcharts-screen --min-run-percentile 90 --period 1d          # Extended runs
stockcharts-screen --max-run-percentile 25 --period 1d          # Early runs
stockcharts-rsi-divergence --type bullish --min-price 10
stockcharts-rsi-divergence --type bearish --min-volume 2_000_000
stockcharts-plot-divergence --ticker NVDA --period 6mo
```

## Common Parameter Combos
| Goal | Command |
|------|---------|
| Bullish divergences mid-price | `stockcharts-rsi-divergence --type bullish --min-price 10 --max-price 100 --period 6mo` |
| Bearish exhaustion high caps | `stockcharts-rsi-divergence --type bearish --min-price 100 --period 1y` |
| Green HA weekly continuation | `stockcharts-screen --color green --period 1wk` |
| Extended HA runs (top decile) | `stockcharts-screen --min-run-percentile 90 --period 1d` |
| Mid-maturity HA runs (40–70%) | `stockcharts-screen --min-run-percentile 40 --max-run-percentile 70 --period 1d` |
| Divergences liquid only | `stockcharts-rsi-divergence --min-volume 5_000_000` |
| Intersect HA + RSI | `stockcharts-rsi-divergence --input-filter results/ha_green.csv --type bullish` |

## Files to Know
- `divergence.py` (RSI divergence logic)
- `rsi.py` (RSI computation)
- `screener/screener.py` (Heiken Ashi logic)
- `charts/divergence.py` (price + RSI chart)

## Adjusting Tolerance
Edit `BEARISH_RSI_TOLERANCE` / `BULLISH_RSI_TOLERANCE` in `divergence.py`.

## Troubleshooting
| Issue | Fix |
|-------|-----|
| No divergences | Increase `--lookback` or lower `--swing-window` |
| Too many signals | Raise `--min-volume` or increase tolerance |
| Rate limit errors | Increase `--delay` |
| Missing charts markers | Ensure precomputed indices available |

---

## Extended Daily Workflow (Merged)

### Environment Setup
```
conda create -n stockcharts python=3.12 -y
conda activate stockcharts
pip install -r requirements.txt
pip install -e .
```

### Morning Scan
```
stockcharts-screen --color all --output results/morning_scan.csv
```

### Weekly Bullish/Bearish Sets
```
stockcharts-screen --color green --period 1wk --output results/weekly_bullish.csv
stockcharts-screen --color red --period 1wk --output results/weekly_bearish.csv
```

### Batch Chart Generation (PowerShell)
```
$tickers = @('AAPL','MSFT','GOOGL','NVDA')
foreach ($t in $tickers) { python scripts\plot_heiken_ashi.py --ticker $t --output "charts\$t.png" }
```

### Programmatic Example
```python
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.indicators.heiken_runs import compute_ha_run_stats

df = fetch_ohlc('AAPL', period='1d', lookback='3mo')
ha = heiken_ashi(df)
stats = compute_ha_run_stats(ha)
print(stats['run_length'], stats['run_percentile'])
```
