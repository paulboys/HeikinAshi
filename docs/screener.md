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

## Reading the output
- A high run percentile means the current run is long relative to that
  series' own history, so it is closer to the tail of its distribution.
- A low run percentile just after a colour change means the new run is
  young by the same measure.
- Counting how much of the cross-section shares a state is the
  market-level reading; a single name's state is close to noise.
- The run percentile is a rank within the fetched window, so it moves
  with `--lookback`. Compare percentiles only across equal windows.

See [`timeframes.md`](timeframes.md) for period, lookback and detector
sensitivity guidance.

## SEC Insider-Trading Screening

The SEC insider module reads Form 4 filings and compares an equal-length
recent window with the preceding baseline window. By default, the activity
numerator includes open-market purchases (`P`) and sales (`S`). The two
screening ratios are:

```text
insider volume ratio   = insider shares transacted / total market shares traded
insider holdings ratio = insider shares transacted / latest total insider holdings
```

```python
from stockcharts.screener.sec_insider import screen_insider_trading

result = screen_insider_trading(
    "AAPL",
    recent_days=30,
    min_volume_increase=2.0,
    min_holding_increase=2.0,
)
if result:
    print(result.volume_ratio_increase, result.holding_ratio_increase)
```

Set `SEC_USER_AGENT` to a descriptive value containing a contact email before
making SEC requests. Use `SECClient(request_delay=0.2)` when scanning a larger
universe, and pass it to `screen_insider_universe` to reuse its in-memory
caches.

### Zero baselines

`volume_ratio_increase` and `holding_ratio_increase` are `None` whenever the
comparison has no finite value. The companion `volume_increase_unbounded` and
`holding_increase_unbounded` flags say why:

| increase | unbounded | meaning |
| --- | --- | --- |
| a number | `False` | ordinary recent-to-baseline multiple |
| `1.0` | `False` | no activity in either window |
| `None` | `True` | zero baseline, positive recent activity |
| `None` | `False` | a ratio could not be computed (no market data) |

An unbounded increase passes any `min_*_increase` threshold, so a ticker whose
insiders resume trading after a quiet baseline still surfaces. Rank those
tickers by `recent_insider_volume_ratio` rather than by the increase, which
carries no magnitude.

### Holdings lookback

Holdings are a point-in-time level, not a flow, so `holdings_lookback_days`
(default 365) searches further back than the screening windows for the last
reported holding of each insider. Without it, any window containing no Form 4
filings reads as zero insider holdings — a reporting gap, not a real zero —
which leaves `holding_ratio_increase` undefined. Lower it to cut SEC requests
on large scans, at the cost of more undefined holding ratios.
