# Price/RSI Divergence Charting Guide

## Overview

The divergence charting module (`stockcharts.charts.divergence`) provides powerful visualization tools for analyzing price and RSI divergences. The charts display:

1. **Price Action** (top panel): Candlestick chart with marked divergence points
2. **RSI Indicator** (bottom panel): RSI line with overbought/oversold levels and divergence markers

## Quick Start

### Using the CLI

The simplest way to generate divergence charts is using the `stockcharts-plot-divergence` command:

```bash
# Plot divergences from RSI screener results
stockcharts-plot-divergence

# Plot from custom CSV file
stockcharts-plot-divergence --input results/my_divergences.csv

# Customize output directory and parameters
stockcharts-plot-divergence --output-dir my_charts/ --lookback 6mo --rsi-period 21
```

### Using Python

```python
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.divergence import plot_price_rsi
import matplotlib.pyplot as plt

# Fetch data
df = fetch_ohlc('AAPL', interval='1d', lookback='6mo')

# Create divergence chart
fig = plot_price_rsi(
    df,
    ticker='AAPL',
    rsi_period=14,
    show_divergence=True,
    divergence_window=5,
    divergence_lookback=120
)

# Save or display
fig.savefig('AAPL_divergence.png', dpi=150, bbox_inches='tight')
plt.show()
```

## CLI Command Reference

### stockcharts-plot-divergence

Generate Price/RSI divergence charts from screener results.

**Usage:**
```bash
stockcharts-plot-divergence [OPTIONS]
```

**Options:**

- `--input PATH` - Input CSV file from RSI divergence screener (default: `results/rsi_divergence.csv`)
- `--output-dir PATH` - Output directory for chart images (default: `charts/divergence/`)
- `--interval PERIOD` - Data aggregation interval: `1d`, `1wk`, `1mo` (default: `1d`)
- `--lookback PERIOD` - Historical data lookback: `1mo`, `3mo`, `6mo`, `1y`, etc. (default: `3mo`)
- `--rsi-period N` - RSI calculation period (default: `14`)
- `--swing-window N` - Window for swing point detection (default: `5`)
- `--divergence-lookback N` - Number of bars to look back for divergence detection (default: `60`)
- `--max-plots N` - Maximum number of charts to generate (default: all)

**Examples:**

```bash
# Plot all divergences with default settings
stockcharts-plot-divergence

# Plot first 20 stocks with custom lookback
stockcharts-plot-divergence --max-plots 20 --lookback 6mo

# Use weekly charts with 21-period RSI
stockcharts-plot-divergence --interval 1wk --rsi-period 21 --lookback 1y

# Process custom results file
stockcharts-plot-divergence --input my_divergences.csv --output-dir my_charts/
```

## Function Reference

### plot_price_rsi()

Create a two-panel chart with candlestick price and RSI indicator.

**Signature:**
```python
def plot_price_rsi(
    df: pd.DataFrame,
    ticker: str = "",
    rsi_period: int = 14,
    show_divergence: bool = True,
    divergence_window: int = 5,
    divergence_lookback: int = 60,
    figsize: tuple[float, float] = (14, 10),
    overbought: float = 70.0,
    oversold: float = 30.0,
) -> Figure
```

**Parameters:**

- `df` - DataFrame with OHLC data (columns: Open, High, Low, Close)
- `ticker` - Stock ticker symbol for title
- `rsi_period` - RSI calculation period (default: 14)
- `show_divergence` - If True, mark detected divergences on chart (default: True)
- `divergence_window` - Window size for swing point detection (default: 5)
- `divergence_lookback` - How many bars to look back for divergences (default: 60)
- `figsize` - Figure size (width, height) in inches (default: (14, 10))
- `overbought` - RSI overbought level (default: 70)
- `oversold` - RSI oversold level (default: 30)

**Returns:**
- `Figure` - Matplotlib Figure object

**Example:**
```python
import pandas as pd
from stockcharts.charts.divergence import plot_price_rsi

# Assume df contains OHLC data
fig = plot_price_rsi(
    df,
    ticker='MSFT',
    rsi_period=14,
    show_divergence=True,
    divergence_window=5,
    divergence_lookback=120,
    figsize=(16, 12),
    overbought=75,
    oversold=25
)

fig.savefig('MSFT_custom.png', dpi=200)
```

## Understanding the Charts

### Price Panel (Top)

The top panel shows:
- **Green candles**: Close >= Open (bullish)
- **Red candles**: Close < Open (bearish)
- **Divergence lines** (if detected):
  - **Green dashed lines with ▲ markers**: Bullish divergence
  - **Red dashed lines with ▼ markers**: Bearish divergence

### RSI Panel (Bottom)

The bottom panel displays:
- **Blue line**: RSI values (0-100)
- **Red dashed line**: Overbought level (default: 70)
- **Green dashed line**: Oversold level (default: 30)
- **Gray line**: Midpoint (50)
- **Divergence markers**: Same color-coding as price panel

## Divergence Detection

### Bullish Divergence (Potential Buy Signal)

Occurs when:
- Price makes a **lower low** (downtrend weakening)
- RSI makes a **higher low** (momentum improving)

**Interpretation**: The downtrend may be losing steam. Consider buying if:
- RSI is in oversold territory (< 30)
- Confirmed by other indicators (volume, Heiken Ashi color change)
- Proper risk management (stop-loss below swing low)

### Bearish Divergence (Potential Sell Signal)

Occurs when:
- Price makes a **higher high** (uptrend continuing)
- RSI makes a **lower high** (momentum weakening)

**Interpretation**: The uptrend may be exhausting. Consider selling if:
- RSI is in overbought territory (> 70)
- Confirmed by other indicators
- Proper risk management (stop-loss above swing high)

## Workflow Examples

### 1. High-Confidence Signal Discovery

Combine RSI divergence screening with Heiken Ashi color changes:

```bash
# Step 1: Find RSI divergences
stockcharts-rsi-divergence --type bullish --output results/bullish_div.csv

# Step 2: Filter for Heiken Ashi color changes
stockcharts-screen --color green --changed-only --input-filter results/bullish_div.csv

# Step 3: Plot the high-confidence signals
stockcharts-plot-divergence --input results/nasdaq_screen.csv --output-dir charts/signals/
```

### 2. Custom Analysis Period

Analyze longer timeframes with weekly charts:

```bash
# Step 1: Screen for weekly divergences
stockcharts-rsi-divergence --interval 1wk --period 6mo --output results/weekly_div.csv

# Step 2: Generate weekly charts
stockcharts-plot-divergence --input results/weekly_div.csv --interval 1wk --lookback 1y --output-dir charts/weekly/
```

### 3. Batch Processing with Filters

Process specific price ranges:

```bash
# Screen mid-cap stocks ($10-$100) with divergences
stockcharts-rsi-divergence --min-price 10 --max-price 100 --output results/midcap_div.csv

# Generate charts for analysis
stockcharts-plot-divergence --input results/midcap_div.csv --max-plots 50
```

## Parameter Tuning

### RSI Period

- **14 (default)**: Standard setting, good for most timeframes
- **21**: Smoother, fewer false signals, slower response
- **9**: More sensitive, catches shorter-term divergences
- **Weekly charts**: Consider 14-21
- **Daily charts**: 14 is standard
- **Intraday**: 9-14 for faster signals

### Swing Window

- **5 (default)**: Balances sensitivity and reliability
- **3**: More swing points detected, but noisier
- **7-10**: Fewer but more significant swing points

### Divergence Lookback

- **60 (default)**: Good for 3-month daily data
- **120**: Better for longer-term analysis (6 months+)
- **30-40**: For shorter-term trading
- **Rule of thumb**: At least 4x the RSI period

### Overbought/Oversold Levels

- **Standard (70/30)**: Traditional RSI thresholds
- **Aggressive (80/20)**: For stronger trends, fewer signals
- **Moderate (65/35)**: More signals, earlier entries
- **Custom by volatility**: Higher for volatile stocks

## Integration with Other Tools

### Combine with Heiken Ashi Screener

```python
# After running both screeners, find intersections
import pandas as pd

# Load results
rsi_df = pd.read_csv('results/rsi_divergence.csv')
ha_df = pd.read_csv('results/nasdaq_screen.csv')

# Find high-confidence signals
high_conf = rsi_df[rsi_df['ticker'].isin(ha_df['ticker'])]

# Plot these specific tickers
for ticker in high_conf['ticker']:
    # Custom plotting logic here
    pass
```

### Programmatic Analysis

```python
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.divergence import plot_price_rsi
from stockcharts.indicators.rsi import compute_rsi
from stockcharts.indicators.divergence import detect_divergence

# Fetch data
df = fetch_ohlc('NVDA', interval='1d', lookback='6mo')

# Add RSI
df['RSI'] = compute_rsi(df['Close'], period=14)

# Detect divergences
div_result = detect_divergence(df, window=5, lookback=60)

# Only plot if divergence found
if div_result['bullish'] or div_result['bearish']:
    print(f"Divergence detected: {div_result['last_signal']}")
    fig = plot_price_rsi(df, ticker='NVDA')
    fig.savefig(f'NVDA_{div_result["last_signal"]}.png')
```

## Troubleshooting

### No Divergences Shown on Charts

**Possible causes:**
1. Lookback period too short - increase `--divergence-lookback`
2. Swing window too large - decrease `--swing-window`
3. Not enough price swings in the data period
4. Market in strong trend (fewer divergences occur)

**Solution:**
```bash
# Try with longer lookback and smaller window
stockcharts-plot-divergence --divergence-lookback 120 --swing-window 3 --lookback 6mo
```

### Charts Look Too Crowded

**Solution:**
```bash
# Increase swing window to show only major divergences
stockcharts-plot-divergence --swing-window 7 --divergence-lookback 90
```

### Memory Issues with Large Batches

**Solution:**
```bash
# Process in smaller batches
stockcharts-plot-divergence --max-plots 50 --input results/rsi_divergence.csv
```

## Best Practices

1. **Always combine signals**: Don't trade on divergences alone
2. **Confirm with volume**: Look for volume confirmation of reversals
3. **Use stop losses**: Place stops beyond the swing point
4. **Wait for confirmation**: Let price action confirm the divergence
5. **Consider timeframe**: Higher timeframes = more reliable signals
6. **Regular review**: Update charts weekly to catch new divergences

## Performance Notes

- Chart generation takes ~1-2 seconds per ticker
- Recommended batch size: 50-100 tickers at once
- Charts are saved as PNG (150 DPI default)
- Average file size: 100-200 KB per chart

## See Also

- [RSI Divergence Guide](RSI_DIVERGENCE_GUIDE.md) - Theory and detection
- [Screener Guide](SCREENER_GUIDE.md) - Using the screeners
- [Library Guide](LIBRARY_GUIDE.md) - Programmatic usage
- [Parameter Guide](PARAMETER_GUIDE.md) - Tuning parameters
