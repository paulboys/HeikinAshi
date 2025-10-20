# Trading Style Guidance

## Swing Trading
Focus on daily bullish divergences confirmed by green HA candles. Parameters:
```
stockcharts-screen --color green --interval 1d --output results/ha_green.csv
stockcharts-rsi-divergence --type bullish --input-filter results/ha_green.csv --min-price 10 --period 6mo
```
Combine with volume filter for higher quality: `--min-volume 2_000_000`.

## Trend Continuation
Weekly green HA + absence of bearish divergence can indicate sustained momentum. Monitor RSI staying above 50.

## Exhaustion / Reversal Short
Bearish divergence + red HA candle on daily/weekly near prior resistance:
```
stockcharts-rsi-divergence --type bearish --min-price 50 --min-volume 2_000_000
```

## High Liquidity Focus
Use both price and volume constraints:
```
--min-price 20 --min-volume 5_000_000
```
Filters out thin and erratic names.

## Conservative Filtering
Increase swing window (7) and RSI period (21) for smoother signals.

## Aggressive Scouting
Lower RSI period (9) and swing window (3) for early/premature signals (expect more noise). Use for watchlist generation.

## Multi-Factor Intersection
Workflow:
1. Run HA screener (green).
2. Feed tickers into divergence screener (`--input-filter`).
3. Plot top setups for manual validation.

## Manual Validation Checklist
- Divergence distance (RSI difference > 0.5 confirmed)
- Price context (support/resistance proximity)
- Volume trend (expansion on reversal attempt?)
- Broader market alignment (index direction)

## Risk Management Notes
- Divergence ≠ guaranteed reversal.
- Use stop below swing low (bullish) / above swing high (bearish).
- Position size adjusts for volatility (ATR or percentage basis).
