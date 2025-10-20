# Quick Reference

## Core Commands
```
stockcharts-screen --color green --interval 1d
stockcharts-screen --color red --interval 1wk
stockcharts-rsi-divergence --type bullish --min-price 10
stockcharts-rsi-divergence --type bearish --min-volume 2_000_000
stockcharts-plot-divergence --ticker NVDA --period 6mo
```

## Common Parameter Combos
| Goal | Command |
|------|---------|
| Bullish divergences mid-price | `stockcharts-rsi-divergence --type bullish --min-price 10 --max-price 100 --period 6mo` |
| Bearish exhaustion high caps | `stockcharts-rsi-divergence --type bearish --min-price 100 --period 1y` |
| Green HA weekly continuation | `stockcharts-screen --color green --interval 1wk` |
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
