# Volume Filtering

## Motivation
Divergence signals on illiquid tickers are prone to false triggers due to erratic prints. Volume filtering restricts results to symbols with sufficient trading interest.

## Parameter
```
--min-volume N
```
Applied to the most recent bar's volume (or optionally average in future enhancement).

## Usage Examples
```
stockcharts-rsi-divergence --min-volume 2_000_000
stockcharts-rsi-divergence --type bullish --min-volume 5_000_000 --min-price 10
```

## Impact
- Reduces total divergence count.
- Increases average reliability of remaining setups.
- Helps align with institutional-grade liquidity.

## Suggested Thresholds
- 1,000,000: Light filter
- 2,000,000: Moderate baseline
- 5,000,000: High liquidity focus

---

## Extended Guide (Merged)

### Why Volume Matters
Low volume → wider spreads, manipulation risk; high volume → tighter spreads, reliable price action.

### Recommended Thresholds By Style
Day: ≥1,000,000; Swing: ≥500,000; Position: ≥300,000.

### Progressive Filtering Workflow
```
stockcharts-screen --color green --changed-only --min-volume 500000 --output green_500k.csv
stockcharts-screen --color green --changed-only --min-volume 1000000 --output green_1m.csv
stockcharts-screen --color green --changed-only --min-volume 5000000 --output green_5m.csv
```

### Combined Daily + Weekly Confirmation
Use same volume threshold across intervals to reinforce liquidity consistency.

### Volume Calculation
Current implementation uses last bar volume; future enhancement: rolling average (20-bar) or relative volume.

### Quick Reference Threshold Categories
<100K Avoid; 300K–500K Moderate; 500K–1M Good; 1M–5M High; >5M Very High.

## Future Extensions
- Average volume (20-day) filtering.
- Relative volume measures (current / average).
- Combined price*volume market cap proxy.
