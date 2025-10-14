# StockCharts

Generate Heiken Ashi candlestick charts and screen NASDAQ stocks for bullish/bearish patterns.

## Features

### 📊 Heiken Ashi Charting
- Fetch OHLC price data for any ticker via yfinance
- Compute Heiken Ashi candles
- Generate date-formatted PNG charts with customizable intervals (daily, weekly, monthly)

### 🔍 NASDAQ Screener
- Screen 90+ major NASDAQ stocks for green (bullish) or red (bearish) Heiken Ashi patterns
- Filter by timeframe: daily, weekly, monthly
- Export results to CSV for further analysis
- Built-in rate limiting and error handling

## Installation

### Create Environment (Conda)
```powershell
conda create -n stockcharts python=3.12 -y
conda activate stockcharts
pip install -r requirements.txt
```

### Or with virtualenv
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Install Package (Editable)
```powershell
pip install -e .
```

## Usage

### Generate Heiken Ashi Charts

Basic usage:
```powershell
python scripts\plot_heiken_ashi.py --ticker AAPL
```

With date range:
```powershell
python scripts\plot_heiken_ashi.py --ticker AAPL --start 2024-01-01 --end 2024-12-31 --output charts\aapl.png
```

Weekly interval:
```powershell
python scripts\plot_heiken_ashi.py --ticker MSFT --interval 1wk --output charts\msft_weekly.png
```

### Screen NASDAQ Stocks

Find bullish (green) stocks:
```powershell
python scripts\screen_nasdaq.py --color green --interval 1d
```

Find bearish (red) stocks on weekly timeframe:
```powershell
python scripts\screen_nasdaq.py --color red --interval 1wk
```

Export all results to CSV:
```powershell
python scripts\screen_nasdaq.py --color all --output results\screen.csv
```

Quick test with limited tickers:
```powershell
python scripts\screen_nasdaq.py --color green --limit 20
```

See [SCREENER_GUIDE.md](SCREENER_GUIDE.md) for detailed screener documentation.

## Project Structure

```
StockCharts/
├── src/stockcharts/          # Main package
│   ├── charts/               # Heiken Ashi computation
│   ├── data/                 # Data fetching (yfinance)
│   └── screener/             # NASDAQ screening module
├── scripts/                  # CLI utilities
│   ├── plot_heiken_ashi.py   # Chart generator
│   └── screen_nasdaq.py      # Stock screener
├── tests/                    # Unit tests
├── requirements.txt          # Dependencies
└── pyproject.toml            # Project config

```

## Requirements

- Python 3.9+
- yfinance >= 0.2.38
- pandas >= 2.0.0
- matplotlib >= 3.7.0

## Examples

### Chart Output
Charts include:
- Date-formatted x-axis (not numeric indices)
- Green candles for bullish moves (HA_Close >= HA_Open)
- Red candles for bearish moves
- Automatic width scaling based on interval

### Screener Output
```
Ticker     Color    HA_Open      HA_Close     Last Date    Interval
======================================================================
AVGO       green    338.72       353.09       2025-10-13   1d
GOOG       green    242.65       242.85       2025-10-13   1d
NFLX       green    1217.72      1219.58      2025-10-13   1d
======================================================================
Total: 3 tickers with green candles
```

## Roadmap (Future Ideas)
- Real-time streaming data
- Additional technical indicators (RSI, MACD, Bollinger Bands)
- Multi-ticker comparison charts
- Web UI or dashboard
- Backtesting framework
- Alert/notification system

## License
MIT
