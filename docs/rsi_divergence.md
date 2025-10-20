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

## Enhancements Implemented
- Input filtering to intersect signals with HA screener output.
- Volume filter to restrict to liquid setups.
- Precomputed divergence indices to guarantee chart marker alignment.
- RSI tolerance to remove marginal noise.

## Future Improvements
See `docs/roadmap.md`.
