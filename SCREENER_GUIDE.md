# NASDAQ Heiken Ashi Screener

Screen NASDAQ stocks for bullish (green) or bearish (red) Heiken Ashi candle patterns.

## Features

- Screen 90+ major NASDAQ stocks
- Filter by candle color: green (bullish), red (bearish), or all
- Support for multiple timeframes: daily (1d), weekly (1wk), monthly (1mo)
- Export results to CSV
- Built-in rate limiting to avoid API throttling
- Progress tracking for long-running scans

## Quick Start

### Screen for green (bullish) daily candles
```powershell
python scripts\screen_nasdaq.py --color green --interval 1d
```

### Screen for red (bearish) weekly candles
```powershell
python scripts\screen_nasdaq.py --color red --interval 1wk
```

### Test with limited tickers
```powershell
python scripts\screen_nasdaq.py --color green --limit 20
```

### Export results to CSV
```powershell
python scripts\screen_nasdaq.py --color all --output results\screen.csv
```

## Command Line Options

```
--color {green,red,all}   Filter by candle color (default: green)
--interval {1d,1wk,1mo}   Data interval (default: 1d)
--limit N                 Screen only first N tickers (for testing)
--delay SECONDS           Delay between API calls (default: 0.5)
--output FILE             Export results to CSV file
--quiet                   Suppress progress messages
```

## Understanding Results

| Column | Description |
|--------|-------------|
| ticker | Stock symbol |
| color | green = bullish (HA_Close >= HA_Open), red = bearish |
| ha_open | Heiken Ashi open price |
| ha_close | Heiken Ashi close price |
| last_date | Date of the most recent candle |
| interval | Time interval used |

## Examples

### Find bullish stocks on daily timeframe
```powershell
python scripts\screen_nasdaq.py --color green --interval 1d
```

Output:
```
Ticker     Color    HA_Open      HA_Close     Last Date    Interval
======================================================================
AVGO       green    338.72       353.09       2025-10-13   1d
GOOG       green    242.65       242.85       2025-10-13   1d
GOOGL      green    241.82       242.14       2025-10-13   1d
======================================================================
Total: 3 tickers with green candles
```

### Find bearish stocks on weekly timeframe
```powershell
python scripts\screen_nasdaq.py --color red --interval 1wk --output results\bearish.csv
```

### Scan all stocks and save both green and red
```powershell
python scripts\screen_nasdaq.py --color all --interval 1d --output results\all_signals.csv
```

## Programmatic Usage

```python
from stockcharts.screener import screen_nasdaq

# Screen for green daily candles
results = screen_nasdaq(
    color_filter="green",
    interval="1d",
    limit=None,  # Scan all tickers
    delay=0.5,
    verbose=True
)

# Process results
for result in results:
    print(f"{result.ticker}: {result.color} @ {result.ha_close:.2f}")
```

## Performance Notes

- Screening 90+ tickers takes ~1-2 minutes with default 0.5s delay
- Reduce delay to speed up (risk: API rate limits)
- Use `--limit` for quick testing
- Results are cached during the run (re-run for fresh data)

## Ticker List

Currently includes 90+ major NASDAQ stocks including:
- Tech giants: AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA
- NASDAQ-100 constituents
- High-volume liquid stocks

To modify the ticker list, edit `src/stockcharts/screener/nasdaq.py`.

## How It Works

1. Fetches historical OHLC data for each ticker via yfinance
2. Computes Heiken Ashi candles using the formula:
   - HA_Close = (O + H + L + C) / 4
   - HA_Open = (prev_HA_Open + prev_HA_Close) / 2
3. Checks if the most recent HA candle is green (bullish) or red (bearish)
4. Filters and returns matching tickers

## Limitations

- Requires active internet connection
- Subject to yfinance API availability and rate limits
- Historical data only (not real-time streaming)
- Limited to pre-defined ticker list (expandable)
