# Heiken Ashi Screener

## Purpose
Identify immediate bullish (green) or bearish (red) Heiken Ashi candle conditions across a curated NASDAQ list.

## Core Concept
A Heiken Ashi candle is green when `HA_Close >= HA_Open` and red otherwise. Latest candle color offers a bias snapshot.

### Run Statistics
Each contiguous sequence of same-color candles forms a "run". The screener now reports:
- `run_length`: Count of consecutive candles of the current color ending at the latest bar.
- `run_percentile`: Inclusive percentile rank (0–100) of `run_length` within all historical run lengths over the fetched lookback + period aggregation.

Interpretation:
- High percentile (e.g. 90+): Extended move; watch for exhaustion or reversal catalysts.
- Low percentile (e.g. <25): Early/immature move; potential continuation room.
- Combine with `--changed-only` to isolate fresh color flips versus mature trends.

## Command-Line Usage
```
stockcharts-screen --color green --period 1d
stockcharts-screen --color red --period 1wk
stockcharts-screen --color all --period 1d --output results/all.csv
stockcharts-screen --color green --period 1d --limit 20 --delay 0.2

# Extended run scan (top decile)
stockcharts-screen --min-run-percentile 90 --period 1d

# Short/early run scan (bottom quartile)
stockcharts-screen --max-run-percentile 25 --period 1d

# Range filter (mid-maturity 40–70%)
stockcharts-screen --min-run-percentile 40 --max-run-percentile 70 --period 1d
```

Options:
```
--color {green,red,all}
--period {1d,1wk,1mo}
--limit N
--delay SECONDS
--output FILE
--quiet
--min-run-percentile PCT   (include runs >= PCT)
--max-run-percentile PCT   (include runs <= PCT)
--changed-only             (only tickers whose color flipped on last bar)
```

## Programmatic Usage
```python
from stockcharts.screener.screener import screen_nasdaq
results = screen_nasdaq(color_filter="green", period="1d", delay=0.5)
for r in results:
    print(r.ticker, r.color, r.run_length, r.run_percentile)
```
Dataclass (simplified):
```python
@dataclass
class ScreenResult:
    ticker: str
    color: Literal['green','red']
    ha_open: float
    ha_close: float
    last_date: str
    period: str
    run_length: int
    run_percentile: float  # 0.0–100.0
```

## Ticker Universe
Located in `src/stockcharts/screener/nasdaq.py` (90+ high-liquidity NASDAQ names). Extend by editing the list.

## Performance
- ~1–2 minutes for full list with default 0.5s delay.
- Reduce delay at risk of API throttling.
- Use `--limit` for development/testing.

## How It Works
1. Download OHLC data via yfinance.
2. Compute Heiken Ashi candles.
3. Determine last candle color.
4. Filter & aggregate results.
5. Optionally output CSV.

## Integration Points
- Shares data retrieval logic with RSI divergence screener.
- Charts can visualize individual tickers with HA candles (using `charts/heiken_ashi.py`).

## Example Output
```
Ticker  Color  HA_Open  HA_Close  Last Date   Period  Run Length  Run Percentile
AVGO    green  338.72   353.09    2025-10-13  1d      6           92.3
AAPL    red    253.25   248.07    2025-10-13  1d      2           28.6
```

## Trading Style Guidance
- Bullish daily green: potential continuation.
- Weekly red emerging: possible broader weakness.
- High run percentile + divergence: watch for reversal setups.
- Low run percentile after color flip: monitor for early momentum follow-through.
- Combine with RSI divergence for confirmation.

See `docs/trading_styles.md` for deeper strategy notes.
