# RSI Price Divergence Screener

## Concept Recap
Divergence highlights momentum disagreement between price action and RSI, hinting at potential reversal or weakening trend.
- Bullish: Price lower low, RSI higher low.
- Bearish: Price higher high, RSI lower high.

## Workflow
1. Fetch OHLC data.
2. Compute RSI (default period=14, EWM-based).
3. Identify swing highs/lows (window default=5).
4. Compare last two valid price + RSI swing pairs.
5. Apply tolerance to avoid noise (>=0.5 RSI point difference required).
6. Output structured results + optional CSV.

## Command-Line Usage
```
stockcharts-rsi-divergence                  # all signals
stockcharts-rsi-divergence --type bullish   # only bullish
stockcharts-rsi-divergence --type bearish   # only bearish
stockcharts-rsi-divergence --min-price 10 --max-price 100
stockcharts-rsi-divergence --rsi-period 21 --lookback 90 --period 6mo
stockcharts-rsi-divergence --min-volume 2_000_000
```

Key options:
```
--type {bullish,bearish,all}
--min-price N --max-price N
--min-volume N
--rsi-period N
--swing-window N
--lookback N  (bars for divergence search)
--period {3mo,6mo,1y}  (data fetch span)
--output FILE
--input-filter FILE (restrict tickers to prior screener results)
```

## Result Object (CSV Columns)
- Ticker, Company, Price, RSI, Divergence Type
- Bullish, Bearish (booleans)
- Details (string describing swing comparison)
- Precomputed indices for chart overlay

## Tolerance Logic
```
BEARISH_RSI_TOLERANCE = 0.5
BULLISH_RSI_TOLERANCE = 0.5
# Bearish: RSI2 + tol < RSI1
# Bullish: RSI2 - tol > RSI1
```
Prevents false positives (e.g., PLTR slight higher RSI not flagged bearish).

## Programmatic Use
```python
from stockcharts.screener.rsi_divergence import screen_rsi_divergence
results = screen_rsi_divergence(divergence_type='bullish', min_price=10.0, period='6mo')
for r in results:
    print(r.ticker, r.divergence_type, r.rsi, r.details)
```

## Plotting
```
stockcharts-plot-divergence --ticker NVDA --period 6mo --interval 1d
```
Overlays price + RSI + detected divergence markers (using precomputed indices if provided).

Note: `stockcharts-plot-divergence` currently uses `--interval` for aggregation (`1d`, `1wk`, `1mo`). Other commands have standardized on `--period`; plot divergence will migrate in a future release. This discrepancy is intentional—use `--interval` here until deprecation notice is published.

## Enhancements Implemented
- Input filtering to intersect signals with HA screener output.
- Volume filter to restrict to liquid setups.
- Precomputed divergence indices to guarantee chart marker alignment.
- RSI tolerance to remove marginal noise.

## Future Improvements
See `docs/roadmap.md`.

---

## Extended Guide (Merged)

The legacy comprehensive guide has been merged here for single-source documentation. It includes detailed trading workflows, expanded CLI examples, Python API usage, interpretation guidelines, strategy integrations (Heiken Ashi + RSI), and troubleshooting. For full historical content refer to repository history; redundant sections have been consolidated to avoid duplication.

### Detailed Concepts

Bullish divergence: Price forms lower low while RSI forms higher low (momentum improvement). Bearish divergence: Price forms higher high while RSI forms lower high (momentum deterioration).

### Expanded CLI Examples
```
stockcharts-rsi-divergence --type bullish --min-price 10 --period 6mo --output results/swing_trades.csv
stockcharts-rsi-divergence --period 1mo --rsi-period 9
stockcharts-rsi-divergence --type bearish --min-price 100 --period 1y
stockcharts-rsi-divergence --rsi-period 21 --lookback 90 --period 1y
```

### Python Usage Pattern
```python
from stockcharts.screener.rsi_divergence import screen_rsi_divergence, save_results_to_csv
results = screen_rsi_divergence(divergence_type='bullish', min_price=10.0, period='6mo')
for r in results:
    print(r.ticker, r.close_price, r.rsi, r.divergence_type, r.details)
save_results_to_csv(results, 'bullish_divergences.csv')
```

### CSV Output Columns
Ticker, Company, Price, RSI, Divergence Type, Bullish, Bearish, Details.

### Strategy Intersection (RSI + Heiken Ashi)
Use divergence screener first, then feed tickers to HA color change screener via `--input-filter` for higher confidence setups.

### Troubleshooting Tips
- No results: increase `--lookback`, decrease `--swing-window`.
- Too many results: raise `--min-volume`, tighten price filters.
- Slow performance: restrict universe with price/volume filters or custom ticker list.

### Best Practices
Confirm divergence with price action (reversal candle patterns), volume expansion, and multi-timeframe alignment. Apply disciplined risk management (stops below swing lows for bullish, above swing highs for bearish).
