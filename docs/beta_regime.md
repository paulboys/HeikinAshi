# Beta Regime Analysis

The Beta Regime module helps identify market risk-on/risk-off conditions by analyzing the relative strength of individual stocks compared to a benchmark (typically SPY).

## Concept Overview

### What is Beta?

Beta (β) measures the volatility of a stock relative to a benchmark index:

$$\beta = \frac{\text{Cov}(r_{\text{asset}}, r_{\text{benchmark}})}{\text{Var}(r_{\text{benchmark}})}$$

- **β > 1**: Stock is more volatile than the benchmark (amplifies market moves)
- **β < 1**: Stock is less volatile than the benchmark (dampens market moves)
- **β ≈ 1**: Stock moves roughly in line with the benchmark
- **β < 0**: Stock moves inversely to the benchmark (rare for stocks)

### Relative Strength & Regime Detection

The regime detection uses a **relative strength ratio**:

$$RS = \frac{\text{Asset Price}}{\text{Benchmark Price}}$$

This ratio is then compared to its moving average:

- **Risk-On**: RS above its moving average → Asset outperforming benchmark
- **Risk-Off**: RS below its moving average → Asset underperforming benchmark

## CLI Commands

### Screen for Beta Regime

```bash
# Screen all NASDAQ stocks
stockcharts-beta-regime

# Filter for risk-on stocks only
stockcharts-beta-regime --regime risk-on

# Screen weekly charts against QQQ benchmark
stockcharts-beta-regime --benchmark QQQ --interval 1wk

# Apply price and volume filters
stockcharts-beta-regime --min-price 10 --max-price 100 --min-volume 500000

# Save results to CSV
stockcharts-beta-regime --output results.csv
```

### Plot Beta Regime Chart

```bash
# Plot a single ticker
stockcharts-plot-beta AAPL

# Compare against QQQ instead of SPY
stockcharts-plot-beta AAPL --benchmark QQQ

# Use weekly interval with custom MA period
stockcharts-plot-beta AAPL --interval 1wk --ma-period 40

# Save chart to file
stockcharts-plot-beta AAPL --output aapl_beta.png
```

## Python API

### Analyze a Single Ticker

```python
from stockcharts.indicators.beta import analyze_beta_regime
from stockcharts.data.fetch import fetch_ohlc

# Fetch data
asset_df = fetch_ohlc("AAPL", lookback="2y")
benchmark_df = fetch_ohlc("SPY", lookback="2y")

# Analyze regime
result = analyze_beta_regime(
    asset_df,
    benchmark_df,
    ma_period=200,
    beta_window=60
)

print(f"Regime: {result['regime']}")
print(f"Relative Strength: {result['rs_current']:.4f}")
print(f"200 MA: {result['rs_ma_current']:.4f}")
print(f"% from MA: {result['pct_from_ma']:.2%}")
print(f"Beta: {result['beta']:.2f}")
```

### Screen Multiple Tickers

```python
from stockcharts.screener.beta_regime import screen_beta_regime, save_results_to_csv

# Screen all NASDAQ for risk-on stocks
results = screen_beta_regime(
    benchmark="SPY",
    regime_filter="risk-on",
    min_price=10,
    min_volume=500000,
    verbose=True
)

# Display results
for r in results[:10]:
    print(f"{r.ticker}: {r.regime} (RS: {r.relative_strength:.4f}, β: {r.beta:.2f})")

# Save to CSV
save_results_to_csv(results, "risk_on_stocks.csv")
```

### Compute Raw Beta

```python
from stockcharts.indicators.beta import compute_rolling_beta
from stockcharts.data.fetch import fetch_ohlc

asset_df = fetch_ohlc("AAPL", lookback="2y")
benchmark_df = fetch_ohlc("SPY", lookback="2y")

# 60-day rolling beta
beta = compute_rolling_beta(
    asset_df["Close"],
    benchmark_df["Close"],
    window=60
)

print(f"Current 60-day Beta: {beta.iloc[-1]:.2f}")
```

## Parameters

### Screener Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `benchmark` | "SPY" | Benchmark ticker (SPY, QQQ, etc.) |
| `interval` | "1d" | Candle interval: "1d", "1wk", "1mo" |
| `ma_period` | 200 | Moving average period for regime detection |
| `beta_window` | 60 | Rolling window for beta calculation |
| `regime_filter` | "all" | Filter: "risk-on", "risk-off", "all" |
| `min_price` | None | Minimum stock price filter |
| `max_price` | None | Maximum stock price filter |
| `min_volume` | None | Minimum average volume filter |
| `batch_size` | 50 | Tickers per batch download |

### Auto-Adjustment for Weekly Interval

When using `--interval 1wk` with `ma_period=200`, the period automatically adjusts to 40 weeks (equivalent to ~200 trading days).

## Trading Applications

### Risk-On Screening

Find stocks that are outperforming the market:

```bash
stockcharts-beta-regime --regime risk-on --min-volume 1000000
```

These stocks are showing relative strength and may continue to outperform.

### Risk-Off Screening

Find stocks that are underperforming:

```bash
stockcharts-beta-regime --regime risk-off --min-price 20
```

These stocks are showing relative weakness; consider for mean-reversion or avoiding longs.

### Combining with Other Signals

Use beta regime as a filter with RSI divergence:

```python
from stockcharts.screener.beta_regime import screen_beta_regime
from stockcharts.screener.rsi_divergence import screen_rsi_divergence

# First find risk-off stocks (underperforming)
weak_stocks = screen_beta_regime(regime_filter="risk-off", verbose=False)
weak_tickers = [r.ticker for r in weak_stocks]

# Then check for bullish divergences (potential reversal)
divergences = screen_rsi_divergence(
    tickers=weak_tickers,
    divergence_type="bullish",
    verbose=True
)
```

## Output Fields

### BetaRegimeResult

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | str | Stock symbol |
| `company_name` | str | Company name |
| `benchmark` | str | Benchmark used |
| `regime` | str | "risk-on" or "risk-off" |
| `relative_strength` | float | Current RS ratio |
| `ma_value` | float | RS moving average value |
| `pct_from_ma` | float | Percentage distance from MA |
| `beta` | float | Rolling beta value |
| `close_price` | float | Current close price |
| `benchmark_price` | float | Current benchmark price |
| `interval` | str | Time interval used |
| `ma_period` | int | MA period used |
## McGlone Contrarian Sector Analysis

The `scripts/sector_regime.py` script implements Mike McGlone's contrarian framework for timing equity sector entry.

### McGlone's 3-Criteria Buy System

Mike McGlone (Bloomberg Intelligence) advocates a **contrarian** approach:

1. **Beta below 200-day MA** (Risk-Off regime) - Sector underperforming SPY
2. **VIX spike to 30-40** - Fear at extreme levels
3. **Market correction ≥ 10%** - Prices discounted from 52-week highs

**BUY signal = All 3 conditions met** (capitulation complete)

### Signal Types

| Signal | Meaning | Action |
|--------|---------|--------|
| `BUY` | All 3 conditions met | Enter positions - capitulation complete |
| `WATCH_BUY` | 2/3 conditions met | Prepare to buy, wait for final trigger |
| `ACCUMULATE` | Risk-off + pullback (5-10%) | Scale in slowly |
| `WATCH` | Deep risk-off (>10% below MA) | Approaching buy zone |
| `WAIT` | Risk-off but no capitulation | Patient - no action yet |
| `HOLD` | Risk-on uptrend | Hold existing positions |
| `EXTENDED` | Far above MA (>15%) | Risky to chase |
| `NEUTRAL` | No clear signal | No action |

### Usage

```bash
# Analyze 11 S&P 500 GICS sectors
python scripts/sector_regime.py

# Industry sub-sectors (XBI, KRE, XHB, etc.)
python scripts/sector_regime.py --industries

# SmallCap sector ETFs (PSC* series)
python scripts/sector_regime.py --smallcap

# Leveraged Bull/Bear ETFs (2x/3x)
python scripts/sector_regime.py --leveraged

# Sectors + Industries combined
python scripts/sector_regime.py --all

# All 90+ ETFs comprehensive
python scripts/sector_regime.py --comprehensive
```

### Available ETF Categories

| Category | Count | Examples |
|----------|-------|----------|
| S&P 500 GICS Sectors | 11 | XLK, XLF, XLE, XLV, XLI, etc. |
| S&P 500 Industries | 18 | XBI, KRE, XHB, XRT, XOP, etc. |
| SmallCap Sectors | 9 | PSCT, PSCF, PSCE, PSCH, etc. |
| iShares Sectors | 4 | IGM, IGV, IGE, IYT |
| Leveraged Bull (2x/3x) | 24 | TECL, FAS, ERX, LABU, etc. |
| Leveraged Bear (2x/3x) | 18 | TECS, FAZ, ERY, LABD, etc. |
| Thematic | 6 | PILL, TEXU, etc. |

### Example Output

```
===============================================================================
MARKET CONDITIONS (McGlone's 3 Criteria)
-------------------------------------------------------------------------------
  [ ] VIX Spike (>=30):     VIX = 20.4 (ELEVATED) -> NO
  [ ] Correction (>=-10%): SPY = $595.23, Drawdown = -1.0% (NEAR_HIGHS) -> NO
  [ ] Risk-Off Regime:   (See sector analysis below)

  MARKET-LEVEL: 0/2 macro conditions met
     WAIT - No capitulation signals yet

===============================================================================
S&P 500 GICS SECTORS - McGlone Contrarian Analysis
===============================================================================

Sector/Industry      ETF   Beta  Regime   %FromMA  Signal       Action
-------------------------------------------------------------------------------
Utilities            XLU    0.45 - risk-off   -4.2% WAIT
Materials            XLB    1.12 - risk-off   -2.8% WAIT
Energy               XLE    1.25 + risk-on    +3.5% NEUTRAL
Technology           XLK    1.35 + risk-on   +12.1% HOLD          
Financials           XLF    1.10 + risk-on   +18.5% EXTENDED      !
```

### Integration with Beta Regime Screener

The sector regime script uses the same underlying `screen_beta_regime()` function with optimized defaults for McGlone's methodology:

- **Period**: 10 years (stable relative strength history)
- **Interval**: Weekly (`1wk`) with 40-bar MA (≈200 daily bars)
- **Benchmark**: SPY

```python
from stockcharts.screener.beta_regime import screen_beta_regime

# Run the same analysis programmatically
results = screen_beta_regime(
    tickers=["XLK", "XLF", "XLE", "XLV", "XLI"],
    interval="1wk",
    lookback="10y",
    regime_filter="all",
)

for r in results:
    print(f"{r.ticker}: {r.regime} ({r.pct_from_ma:+.1f}%)")
```