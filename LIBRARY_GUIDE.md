# StockCharts Library Guide

A comprehensive guide to using the StockCharts Python library for NASDAQ screening and Heiken Ashi analysis.

## Table of Contents
1. [Installation](#installation)
2. [Command-Line Tools](#command-line-tools)
3. [Python API](#python-api)
4. [Use Cases](#use-cases)
5. [Tips & Best Practices](#tips--best-practices)

---

## Installation

### From Source (Current)
```powershell
git clone https://github.com/paulboys/HeikinAshi.git
cd HeikinAshi
pip install -e .
```

### From PyPI (Coming Soon)
```powershell
pip install stockcharts
```

---

## Command-Line Tools

After installation, you'll have access to two CLI commands:

### 1. `stockcharts-screen` - Screen NASDAQ Stocks

Screen all 5,120+ NASDAQ tickers for Heiken Ashi color patterns.

#### Basic Usage

```powershell
# Find green reversals (red→green) on daily charts
stockcharts-screen --color green --changed-only

# Find red reversals with volume filter
stockcharts-screen --color red --changed-only --min-volume 500000
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--color` | Choice | `green` | Filter by `red` or `green` candles |
| `--period` | String | `1d` | Aggregation period: `1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo` |
| `--lookback` | String | `3mo` | Historical window: `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `max` |
| `--start` | Date | None | Start date (YYYY-MM-DD) - overrides `--lookback` |
| `--end` | Date | Today | End date (YYYY-MM-DD) |
| `--changed-only` | Flag | False | Only show stocks with recent color changes |
| `--min-volume` | Integer | 0 | Minimum average daily volume |
| `--output` | Path | `results/nasdaq_screen.csv` | Output CSV file path |
| `--debug` | Flag | False | Show detailed error messages |

#### Examples by Trading Style

**Day Trading** (1-hour charts, high volume):
```powershell
stockcharts-screen --color green --period 1h --lookback 1mo --min-volume 2000000 --changed-only
```

**Swing Trading** (daily charts, moderate volume):
```powershell
stockcharts-screen --color green --period 1d --lookback 3mo --min-volume 500000 --changed-only
```

**Position Trading** (weekly charts, 6-month window):
```powershell
stockcharts-screen --color green --period 1wk --lookback 6mo --changed-only
```

**Historical Analysis** (custom date range):
```powershell
stockcharts-screen --color red --start 2024-01-01 --end 2024-12-31
```

#### Output

Creates a CSV file with these columns:
- `ticker`: Stock symbol
- `color`: Current Heiken Ashi color (red/green)
- `ha_open`: Heiken Ashi open price
- `ha_close`: Heiken Ashi close price
- `last_date`: Most recent data date
- `period`: Aggregation period used
- `color_changed`: Boolean indicating if color changed in latest candle
- `avg_volume`: 20-period average daily volume

### 2. `stockcharts-plot` - Generate Charts

Create Heiken Ashi candlestick charts from screening results.

#### Basic Usage

```powershell
# Plot all results from default location
stockcharts-plot

# Plot from specific CSV
stockcharts-plot --input results/green_reversals.csv --output-dir my_charts/
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--input` | Path | `results/nasdaq_screen.csv` | Input CSV from screener |
| `--output-dir` | Path | `charts/` | Output directory for PNG files |
| `--period` | String | `1d` | Chart aggregation period |
| `--lookback` | String | `3mo` | Historical data window |

#### Output

Generates PNG files named `{TICKER}_{PERIOD}.png` in the output directory.

---

## Python API

Use StockCharts programmatically in your Python scripts.

### 1. Screen NASDAQ Stocks

```python
from stockcharts.screener.screener import screen_nasdaq

# Basic screening
results = screen_nasdaq(
    color='green',
    period='1d',
    lookback='3mo',
    changed_only=True,
    min_volume=500000
)

# Access results
for result in results:
    print(f"{result.ticker}: {result.color} @ {result.ha_close}")
    print(f"  Volume: {result.avg_volume:,.0f}")
    print(f"  Color changed: {result.color_changed}")
```

### 2. Get NASDAQ Tickers

```python
from stockcharts.screener.nasdaq import get_nasdaq_tickers

# Fetch all NASDAQ tickers from official FTP source
tickers = get_nasdaq_tickers()
print(f"Found {len(tickers)} NASDAQ tickers")

# Example output: ['AAPL', 'MSFT', 'GOOGL', ...]
```

### 3. Fetch OHLC Data

```python
from stockcharts.data.fetch import fetch_ohlc

# Fetch data with period and lookback
data = fetch_ohlc('AAPL', period='1d', lookback='3mo')

# Or use custom date range
data = fetch_ohlc('MSFT', period='1wk', start='2024-01-01', end='2024-12-31')

# Returns pandas DataFrame with columns: Open, High, Low, Close, Volume
```

### 4. Compute Heiken Ashi Candles

```python
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.heiken_ashi import heiken_ashi

# Fetch and convert to Heiken Ashi
data = fetch_ohlc('NVDA', period='1d', lookback='3mo')
ha_data = heiken_ashi(data)

# Access Heiken Ashi values
print(ha_data[['HA_Open', 'HA_Close', 'HA_High', 'HA_Low']].tail())

# Check current candle color
current = ha_data.iloc[-1]
color = 'green' if current['HA_Close'] >= current['HA_Open'] else 'red'
print(f"Current color: {color}")
```

### 5. Complete Example: Custom Screener

```python
from stockcharts.screener.nasdaq import get_nasdaq_tickers
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.heiken_ashi import heiken_ashi
import pandas as pd

def custom_screen(min_price=10, max_price=100, min_volume=1000000):
    """
    Custom screener with price and volume filters.
    """
    results = []
    tickers = get_nasdaq_tickers()
    
    for ticker in tickers:
        try:
            # Fetch data
            data = fetch_ohlc(ticker, period='1d', lookback='1mo')
            if data is None or data.empty:
                continue
            
            # Check price range
            current_price = data['Close'].iloc[-1]
            if not (min_price <= current_price <= max_price):
                continue
            
            # Check volume
            avg_volume = data['Volume'].tail(20).mean()
            if avg_volume < min_volume:
                continue
            
            # Compute Heiken Ashi
            ha_data = heiken_ashi(data)
            current = ha_data.iloc[-1]
            previous = ha_data.iloc[-2]
            
            # Check for green reversal
            current_green = current['HA_Close'] >= current['HA_Open']
            previous_red = previous['HA_Close'] < previous['HA_Open']
            
            if current_green and previous_red:
                results.append({
                    'ticker': ticker,
                    'price': current_price,
                    'avg_volume': int(avg_volume),
                    'ha_close': current['HA_Close']
                })
        
        except Exception:
            continue
    
    return pd.DataFrame(results)

# Run custom screener
results = custom_screen(min_price=10, max_price=100, min_volume=1000000)
print(results)
```

---

## Use Cases

### 1. Swing Trading Setup

**Goal**: Find stocks transitioning from bearish to bullish on daily charts with decent volume.

```powershell
stockcharts-screen --color green --changed-only --min-volume 500000 --period 1d --lookback 3mo
```

**Why**:
- `--changed-only`: Catches fresh reversals (red→green)
- `--min-volume 500000`: Ensures liquidity for swing trades
- `--period 1d`: Daily timeframe for 2-5 day holds
- `--lookback 3mo`: Sufficient history for trend context

### 2. Day Trading Scanner

**Goal**: High-volume stocks showing bullish momentum on 1-hour charts.

```powershell
stockcharts-screen --color green --period 1h --lookback 1mo --min-volume 2000000 --changed-only
```

**Why**:
- `--period 1h`: Intraday momentum shifts
- `--min-volume 2000000`: High liquidity for day trading
- `--lookback 1mo`: Recent patterns only
- `--changed-only`: Fresh entry signals

### 3. Position Trading Analysis

**Goal**: Weekly trends for long-term positions (weeks to months).

```powershell
stockcharts-screen --color green --period 1wk --lookback 6mo --changed-only
```

**Why**:
- `--period 1wk`: Smooths out daily noise
- `--lookback 6mo`: Captures broader market context
- Volume less critical for position trading

### 4. Backtesting Strategy

**Goal**: Test a strategy over specific historical periods.

```powershell
stockcharts-screen --color green --start 2024-01-01 --end 2024-06-30 --changed-only
```

**Why**:
- Custom date range for backtesting
- Can run multiple periods and compare results
- Export to CSV for further analysis

---

## Tips & Best Practices

### Volume Filtering Guidelines

| Trading Style | Recommended Min Volume | Reason |
|---------------|------------------------|--------|
| Day Trading | 2,000,000+ | Need tight spreads, quick fills |
| Swing Trading | 500,000 - 1,000,000 | Balance liquidity & opportunities |
| Position Trading | 100,000+ | Less critical for long holds |

### Period Selection

| Timeframe | Best For | Typical Hold Time |
|-----------|----------|-------------------|
| 1m - 15m | Scalping | Minutes to hours |
| 30m - 1h | Day trading | Hours to 1 day |
| 1d | Swing trading | Days to weeks |
| 1wk | Position trading | Weeks to months |
| 1mo | Long-term investing | Months to years |

### Lookback Window Guidelines

- **Too short**: Miss important trend context
- **Too long**: Include irrelevant historical data
- **Recommended**:
  - Day trading: 1mo (captures recent patterns)
  - Swing trading: 3mo (shows intermediate trends)
  - Position trading: 6mo-1y (captures major cycles)

### Screening Workflow

1. **Broad scan** without filters to see universe size:
   ```powershell
   stockcharts-screen --color green --period 1d
   ```

2. **Add volume filter** to narrow to tradeable stocks:
   ```powershell
   stockcharts-screen --color green --period 1d --min-volume 500000
   ```

3. **Filter for reversals** to find entry signals:
   ```powershell
   stockcharts-screen --color green --period 1d --min-volume 500000 --changed-only
   ```

4. **Generate charts** for visual confirmation:
   ```powershell
   stockcharts-plot --input results/nasdaq_screen.csv
   ```

5. **Manual review** of charts for best setups

### Performance Optimization

- Use `--debug` flag to see which tickers are failing
- Smaller `--lookback` windows process faster
- Higher `--min-volume` reduces screening time
- Consider running during off-market hours to avoid rate limits

### Integration with Other Tools

**Export to Excel**:
```python
import pandas as pd
df = pd.read_csv('results/nasdaq_screen.csv')
df.to_excel('results/nasdaq_screen.xlsx', index=False)
```

**Combine with technical indicators**:
```python
from stockcharts.data.fetch import fetch_ohlc
import pandas as pd

data = fetch_ohlc('AAPL', period='1d', lookback='3mo')

# Add RSI
delta = data['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
data['RSI'] = 100 - (100 / (1 + rs))

print(data[['Close', 'RSI']].tail())
```

---

## Troubleshooting

### "No data returned for ticker"
- Ticker may be delisted or invalid
- Try shorter `--lookback` period
- Check yfinance compatibility

### "Rate limit exceeded"
- Add delays between API calls
- Run during off-peak hours
- Consider caching results

### "Volume filter too aggressive"
- Lower `--min-volume` threshold
- Check typical volumes for your market cap range
- Remember volume varies by stock price

### "Too many/too few results"
- Adjust `--min-volume` to narrow/broaden
- Use `--changed-only` for fresher signals
- Change `--period` for different timeframes

---

## Next Steps

1. **Run your first screen**: Start with the examples above
2. **Review the charts**: Use `stockcharts-plot` to visualize results
3. **Backtest**: Use custom date ranges to test strategies
4. **Integrate**: Use the Python API in your own trading systems
5. **Customize**: Build on the library for your specific needs

For more detailed parameter explanations, see [QUICK_REFERENCE.md](QUICK_REFERENCE.md).

For volume filtering strategies, see [VOLUME_FILTERING_GUIDE.md](VOLUME_FILTERING_GUIDE.md).

For trading style recommendations, see [TRADING_STYLE_GUIDE.md](TRADING_STYLE_GUIDE.md).
