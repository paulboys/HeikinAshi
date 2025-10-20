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

## Future Extensions
- Average volume (20-day) filtering.
- Relative volume measures (current / average).
- Combined price*volume market cap proxy.
