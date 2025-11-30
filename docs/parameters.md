# Parameters & Configuration

## Price Filters
- `--min-price` / `--max-price` narrow universe to viable capital ranges.
- Avoid illiquid penny stocks with `--min-price 5` or `10`.

## Volume Filter (RSI Divergence)
- `--min-volume N` ensures recent average volume (last bar) exceeds threshold.
- Helps eliminate thinly traded noise setups.

## RSI Settings
- `--rsi-period` (default 14). Lower values (9) increase sensitivity; higher (21) smooth.
- Consider longer period for weekly scans.

## Swing Window
- `--swing-window` controls local extremum detection width.
- Larger window = fewer, more significant swing points.

## Lookback
- `--lookback` bars to search for last two qualifying swings.
- Typical range: 50–80 for daily; can expand for weekly.

## Data Period
- `--period` sets fetch span (3mo, 6mo, 1y). Must cover at least `lookback + buffer`.

## Interval
- `--interval` (1d/1wk/1mo). Screener supports all, but divergence reliability best on daily/weekly.

## Tolerance
- Fixed RSI tolerance (0.5) ensures meaningful divergence.
- Adjustable in `divergence.py` if needed.

## Input Filter
- `--input-filter FILE` loads tickers from a previous screener CSV to intersect signals.
- Enables multi-factor workflows (e.g., green HA AND bullish divergence).

## Output
- `--output FILE` writes results to CSV.
- For reproducibility, include parameters in filename (e.g., `div_bullish_6mo_tol0.5.csv`).

## Delay (HA Screener)
- `--delay` controls per-ticker pause for yfinance.
- Reduce cautiously (risk rate limiting).

## Quiet Mode
- `--quiet` suppresses progress logging for cleaner automation output.

## Recommended Combos
- Momentum exhaustion: `--type bearish --min-price 50 --min-volume 2_000_000`
- Reversal scan: `--type bullish --swing-window 7 --rsi-period 21`
- Liquidity focus: `--min-volume 5_000_000 --min-price 10`

---

## Extended Terminology Guide (Merged)

### Aggregation Period (`--period`)
Defines candle size: `1d`, `1wk`, `1mo`.

### Time Window (`--lookback`)
Historical span fetched: `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`.

### Explicit Date Range (`--start` / `--end`)
Overrides lookback when both provided; format YYYY-MM-DD.

### Example Commands
```
stockcharts-screen --color green --period 1d --lookback 3mo --output green_reversals.csv
stockcharts-screen --color green --period 1wk --lookback 1y --output weekly_reversals.csv
stockcharts-screen --color green --period 1d --start 2024-01-01 --end 2024-12-31
```

### Common Mistakes
- Mixing lookback with start/end.
- Using too short lookback to detect color change.

### Multi-Timeframe Workflow
Weekly context → Daily execution → Optional charting.
