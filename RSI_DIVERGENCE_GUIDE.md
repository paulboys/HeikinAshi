# RSI Divergence Screening Guide

## What is RSI Divergence?

RSI (Relative Strength Index) divergence occurs when the price action and the RSI indicator move in opposite directions, suggesting a potential trend reversal. This is a powerful technical analysis tool used by traders like Gareth Soloway to identify high-probability entry and exit points.

### Types of Divergence

#### 1. Bullish Divergence (Potential Buy Signal)
- **Price Action**: Makes a lower low
- **RSI**: Makes a higher low
- **Interpretation**: The downtrend is losing momentum; potential reversal to the upside
- **Strategy**: Look for buying opportunities when confirmed with other indicators

#### 2. Bearish Divergence (Potential Sell Signal)
- **Price Action**: Makes a higher high
- **RSI**: Makes a lower high
- **Interpretation**: The uptrend is losing momentum; potential reversal to the downside
- **Strategy**: Consider taking profits or shorting when confirmed

## How the Screener Works

The RSI divergence screener:

1. **Fetches OHLC data** for all NASDAQ stocks (or a custom list)
2. **Calculates RSI** using exponential weighted moving average (14-period default)
3. **Identifies swing points** (local highs and lows) in both price and RSI
4. **Detects divergences** by comparing recent swing points:
   - Bullish: Price lower low + RSI higher low
   - Bearish: Price higher high + RSI lower high
5. **Filters results** by divergence type, price range, etc.
6. **Saves to CSV** with detailed information about each divergence

## Command-Line Usage

### Basic Commands

```bash
# Screen for all divergences (bullish and bearish)
stockcharts-rsi-divergence

# Find only bullish divergences (potential buy signals)
stockcharts-rsi-divergence --type bullish

# Find only bearish divergences (potential sell signals)
stockcharts-rsi-divergence --type bearish
```

### Price Filtering

```bash
# Filter out penny stocks (minimum $5)
stockcharts-rsi-divergence --min-price 5

# Look for mid-cap stocks ($10-$100)
stockcharts-rsi-divergence --min-price 10 --max-price 100

# Focus on higher-priced stocks
stockcharts-rsi-divergence --min-price 50
```

### Customizing RSI Parameters

```bash
# Use 21-period RSI instead of default 14
stockcharts-rsi-divergence --rsi-period 21

# Use 9-period RSI for more sensitive signals
stockcharts-rsi-divergence --rsi-period 9

# Look back 6 months instead of 3
stockcharts-rsi-divergence --period 6mo

# Adjust swing point detection window
stockcharts-rsi-divergence --swing-window 7
```

### Output Options

```bash
# Save to custom location
stockcharts-rsi-divergence --output my_divergences.csv

# Save bullish signals to specific file
stockcharts-rsi-divergence --type bullish --output bullish_setups.csv
```

### Complete Examples

```bash
# Swing trading setup: Bullish divergences on quality stocks
stockcharts-rsi-divergence --type bullish --min-price 10 --period 6mo --output results/swing_trades.csv

# Day trading setup: All divergences, any price, short lookback
stockcharts-rsi-divergence --period 1mo --rsi-period 9

# Conservative approach: Bearish signals on expensive stocks
stockcharts-rsi-divergence --type bearish --min-price 100 --period 1y

# Aggressive approach: 21-period RSI, longer lookback
stockcharts-rsi-divergence --rsi-period 21 --lookback 90 --period 1y
```

## Python API Usage

### Import the Module

```python
from stockcharts.screener.rsi_divergence import screen_rsi_divergence, save_results_to_csv
```

### Basic Screening

```python
# Screen all NASDAQ stocks for bullish divergences
results = screen_rsi_divergence(
    divergence_type='bullish',
    min_price=10.0,
    period='6mo'
)

# Display results
for r in results:
    print(f"{r.ticker}: ${r.close_price:.2f} | RSI: {r.rsi:.2f}")
    print(f"  {r.details}")
```

### Advanced Filtering

```python
# Custom ticker list
my_tickers = [('AAPL', 'Apple Inc.'), ('MSFT', 'Microsoft'), ('GOOGL', 'Alphabet')]

results = screen_rsi_divergence(
    tickers=my_tickers,
    period='3mo',
    rsi_period=14,
    divergence_type='all',
    min_price=50.0,
    max_price=500.0,
    swing_window=5,
    lookback=60
)
```

### Saving Results

```python
# Save to CSV
save_results_to_csv(results, 'my_divergences.csv')

# Or manually create DataFrame
import pandas as pd

df = pd.DataFrame([{
    'Ticker': r.ticker,
    'Company': r.company_name,
    'Price': r.close_price,
    'RSI': r.rsi,
    'Type': r.divergence_type,
    'Details': r.details
} for r in results])

df.to_csv('output.csv', index=False)
```

## Understanding the Results

### CSV Output Columns

| Column | Description |
|--------|-------------|
| **Ticker** | Stock symbol |
| **Company** | Company name |
| **Price** | Current closing price |
| **RSI** | Current RSI value (0-100) |
| **Divergence Type** | 'bullish', 'bearish', or 'bullish & bearish' |
| **Bullish** | True/False - Bullish divergence detected |
| **Bearish** | True/False - Bearish divergence detected |
| **Details** | Detailed description of the divergence |

### Interpreting Details

Example bullish divergence details:
```
BULLISH: Price: 45.30 → 42.15 (lower low) | RSI: 28.50 → 32.40 (higher low)
```

This means:
- First swing low: Price $45.30, RSI 28.50
- Second swing low: Price $42.15 (lower), RSI 32.40 (higher)
- **Interpretation**: Despite price making new lows, RSI is strengthening → potential reversal

Example bearish divergence details:
```
BEARISH: Price: 150.20 → 155.80 (higher high) | RSI: 72.30 → 68.50 (lower high)
```

This means:
- First swing high: Price $150.20, RSI 72.30
- Second swing high: Price $155.80 (higher), RSI 68.50 (lower)
- **Interpretation**: Price making new highs but RSI weakening → potential reversal

## Trading Strategies

### Gareth Soloway Confirmation Strategy

1. **Identify divergence** using this screener
2. **Wait for confirmation**: Look for price action signals
   - Bullish: Reversal candle pattern (hammer, engulfing)
   - Bearish: Distribution pattern (shooting star, dark cloud)
3. **Check volume**: Confirm with increasing volume on reversal
4. **Set stop loss**: Below recent swing low (bullish) or above swing high (bearish)
5. **Target**: Previous high/low or key resistance/support levels

### Swing Trading Workflow

```bash
# 1. Screen for bullish divergences
stockcharts-rsi-divergence --type bullish --min-price 10 --output bullish.csv

# 2. Review CSV file, select candidates

# 3. Plot Heiken Ashi charts for visual confirmation
# (Manual step: Check if Heiken Ashi also showing reversal)

# 4. Monitor for entry signals over next few days
```

### Day Trading Workflow

```bash
# 1. Short-period screening (1-hour or 15-minute charts)
# Note: Use custom Python code for intraday periods

# 2. Look for quick reversals
stockcharts-rsi-divergence --period 1mo --rsi-period 9 --lookback 20

# 3. Trade with tight stops
```

### High-Confidence Signal Workflow (RSI + Heiken Ashi)

The most powerful setups occur when **both** RSI divergence and Heiken Ashi color change align:

```bash
# Step 1: Find bullish RSI divergences (potential reversal candidates)
stockcharts-rsi-divergence --type bullish --min-price 10 --output results/bullish_div.csv

# Step 2: Screen ONLY those tickers for fresh green Heiken Ashi candles
stockcharts-screen --color green --changed-only --input-filter results/bullish_div.csv --output results/high_confidence.csv

# Result: Stocks showing BOTH signals = highest probability reversal setups
```

**Why this works:**
- RSI divergence identifies **potential** reversal (momentum weakening)
- HA color flip confirms **actual** price reversal (trend change starting)
- Together = early entry with confirmation

**Alternative: Find currently green (not necessarily changed):**
```bash
# Useful if you want divergence stocks that are already in uptrend
stockcharts-screen --color green --input-filter results/bullish_div.csv --output results/div_plus_green.csv
```

## Technical Details

### RSI Calculation

RSI = 100 - (100 / (1 + RS))

where RS = Average Gain / Average Loss

The screener uses **exponential weighted moving average** (EWM) for smoother RSI:
```python
avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
```

### Swing Point Detection

A swing high is detected when a price point is higher than N bars before and after it.
A swing low is detected when a price point is lower than N bars before and after it.

Default window: 5 bars (configurable with `--swing-window`)

### Divergence Matching

The screener matches price swing points with RSI swing points within a time window:
- Finds last two price highs/lows
- Finds corresponding RSI highs/lows within ±(2 × swing_window) bars
- Compares slopes to detect divergence

## Parameters Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--type` | `all` | Divergence type: `bullish`, `bearish`, or `all` |
| `--period` | `3mo` | Data lookback: `1mo`, `3mo`, `6mo`, `1y`, etc. |
| `--rsi-period` | `14` | RSI calculation period (typical: 9, 14, 21) |
| `--min-price` | None | Minimum stock price filter |
| `--max-price` | None | Maximum stock price filter |
| `--swing-window` | `5` | Bars to compare for swing points |
| `--lookback` | `60` | Recent bars to analyze for divergence |
| `--output` | `results/rsi_divergence.csv` | Output CSV path |

## Tips and Best Practices

### 1. Divergence Confirmation
- Don't trade divergence alone
- Wait for price action confirmation
- Use with other indicators (volume, MACD, Heiken Ashi)

### 2. False Signals
- Divergences can fail, especially in strong trends
- Use stop losses
- Look for multiple timeframe confirmation

### 3. Time Frames
- Longer timeframes (weekly/monthly) = stronger signals
- Shorter timeframes (daily/hourly) = more frequent but weaker signals
- Match timeframe to your trading style

### 4. RSI Levels
- Bullish divergence most powerful when RSI < 30 (oversold)
- Bearish divergence most powerful when RSI > 70 (overbought)
- Filter results manually for extreme RSI levels

### 5. Combining with Heiken Ashi
```bash
# Method 1: Use input-filter for automatic intersection
# 1. Find bullish divergences
stockcharts-rsi-divergence --type bullish --min-price 10 --output bullish_div.csv

# 2. Screen those stocks for green HA candles that just changed
stockcharts-screen --color green --changed-only --input-filter bullish_div.csv --output combined_signals.csv

# Result: Stocks with BOTH bullish RSI divergence AND fresh green HA candle (high-confidence setups)

# Method 2: Manual comparison
# 1. Find divergences
stockcharts-rsi-divergence --type bullish --output bullish.csv

# 2. Screen all stocks for Heiken Ashi reversals
stockcharts-screen --color green --changed-only --output green_ha.csv

# 3. Manually compare ticker lists in both CSV files
```

## Troubleshooting

### No Results Found
- Try increasing `--period` (more historical data)
- Decrease `--swing-window` (more sensitive swing detection)
- Increase `--lookback` (more bars to analyze)
- Remove price filters temporarily

### Too Many Results
- Add price filters (`--min-price`, `--max-price`)
- Specify divergence type (`--type bullish` or `--type bearish`)
- Increase `--swing-window` (less sensitive)

### Slow Performance
- Screening all ~5,120 NASDAQ stocks can take 10-30 minutes
- Use price filters to reduce stocks scanned
- Run during off-market hours

## Related Resources

- **SCREENER_GUIDE.md**: Heiken Ashi color screening
- **TRADING_STYLE_GUIDE.md**: Day trading vs swing trading strategies
- **VOLUME_FILTERING_GUIDE.md**: Using volume for confirmation
- **PARAMETER_GUIDE.md**: Detailed parameter explanations

## Example Results Interpretation

### Scenario 1: Clear Bullish Signal
```csv
Ticker,Price,RSI,Type,Details
XYZ,25.40,35.20,bullish,"BULLISH: Price: 28.50 → 25.40 (lower low) | RSI: 29.10 → 35.20 (higher low)"
```

**Analysis**: Strong bullish divergence. Price dropped from $28.50 to $25.40, but RSI improved from 29.10 to 35.20. Sellers losing control.

**Action**: Watch for reversal candle pattern. If confirmed, consider entry around $25-26 with stop below $25.

### Scenario 2: Bearish Warning
```csv
Ticker,Price,RSI,Type,Details
ABC,180.50,65.30,bearish,"BEARISH: Price: 175.20 → 180.50 (higher high) | RSI: 71.80 → 65.30 (lower high)"
```

**Analysis**: Bearish divergence. Price making new highs ($180.50) but RSI declining (71.80 → 65.30). Buyers weakening.

**Action**: If holding, consider taking profits. If shorting, wait for confirmation below key support.

### Scenario 3: Double Divergence
```csv
Ticker,Price,RSI,Type,Details
DEF,50.25,55.10,bullish & bearish,"BULLISH: Price: 48.90 → 47.20 (lower low) | RSI: 30.50 → 38.20 (higher low) | BEARISH: Price: 52.10 → 53.50 (higher high) | RSI: 68.20 → 64.30 (lower high)"
```

**Analysis**: Mixed signals. Both bullish and bearish divergences present. Potentially choppy/ranging market.

**Action**: Wait for clearer direction. Avoid trading until one signal dominates.

## Updates and Contributions

This module is part of the `stockcharts` package. For updates, bug reports, or feature requests:

- GitHub: https://github.com/paulboys/HeikinAshi
- PyPI: https://pypi.org/project/stockcharts/

Version: 0.3.0
