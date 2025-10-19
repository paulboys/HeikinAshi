# StockCharts

[![CI](https://github.com/paulboys/HeikinAshi/actions/workflows/ci.yml/badge.svg)](https://github.com/paulboys/HeikinAshi/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/stockcharts.svg)](https://pypi.org/project/stockcharts/)
[![Python versions](https://img.shields.io/pypi/pyversions/stockcharts.svg)](https://pypi.org/project/stockcharts/)
[![Downloads](https://static.pepy.tech/badge/stockcharts)](https://pepy.tech/project/stockcharts)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/paulboys/HeikinAshi/blob/main/LICENSE)

A Python library for screening NASDAQ stocks using Heiken Ashi candles and RSI divergence to detect trend reversals with volume and price filtering.

## Features

### � NASDAQ Screener
- **Full NASDAQ Coverage**: Automatically fetches all 5,120+ NASDAQ tickers from official FTP source
- **Heiken Ashi Analysis**: Detects red-to-green and green-to-red candle color changes
- **Volume Filtering**: Filter by average daily volume to focus on liquid, tradeable stocks
- **Flexible Timeframes**: Support for intraday (1m-1h), daily, weekly, and monthly charts
- **Custom Date Ranges**: Screen historical data with specific start/end dates
- **CSV Export**: Save screening results for further analysis

### 📊 Chart Generation
- Generate Heiken Ashi candlestick charts from screening results
- Support for multiple timeframes: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo
- High-quality PNG output for technical analysis

### 🎯 Trading Styles Supported
- **Day Trading**: 1m-1h periods, high volume (2M+ shares/day)
- **Swing Trading**: Daily charts, moderate volume (500K-1M shares/day)
- **Position Trading**: Weekly/monthly charts, lower volume acceptable

## Installation

### From PyPI
```bash
pip install stockcharts
```

### From Source
```powershell
# Clone the repository
git clone https://github.com/paulboys/HeikinAshi.git
cd HeikinAshi

# Create conda environment
conda create -n stockcharts python=3.12 -y
conda activate stockcharts

# Install in editable mode
pip install -e .
```

## Quick Start

After installation, you'll have three command-line tools available:

### 1. `stockcharts-screen` - Heiken Ashi Color Screening
### 1. `stockcharts-screen` - Heiken Ashi Color Screening
### 2. `stockcharts-plot` - Chart Generation
### 3. `stockcharts-rsi-divergence` - RSI Divergence Screening

## Usage

### 1. Screen for Trend Reversals

**Find green reversals (red→green) for swing trading:**
```powershell
stockcharts-screen --color green --changed-only --min-volume 500000
```

**Day trading setup (1-hour charts with high volume):**
```powershell
stockcharts-screen --color green --period 1h --lookback 1mo --min-volume 2000000 --changed-only
```

**Weekly analysis over 6 months:**
```powershell
stockcharts-screen --color green --period 1wk --lookback 6mo --changed-only
```

**Screen specific date range:**
```powershell
stockcharts-screen --color red --start 2024-01-01 --end 2024-12-31
```

### 2. Generate Charts from Results

**Plot all screened stocks:**
```powershell
stockcharts-plot
```

**Plot from specific CSV:**
```powershell
stockcharts-plot --input results/green_reversals.csv --output-dir my_charts/
```

### 3. Screen for RSI Divergences

**Find bullish divergences (potential buy signals):**
```powershell
stockcharts-rsi-divergence --type bullish --min-price 10
```

**Find bearish divergences (potential sell signals):**
```powershell
stockcharts-rsi-divergence --type bearish --min-price 10 --max-price 100
```

**Custom RSI parameters:**
```powershell
stockcharts-rsi-divergence --rsi-period 21 --period 6mo
```

### Command-Line Options

#### `stockcharts-screen` (Heiken Ashi Screening)
- `--color`: Filter by `red` or `green` candles (default: green)
- `--period`: Aggregation period: `1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo` (default: 1d)
- `--lookback`: Historical window: `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `max` (default: 3mo)
- `--start`, `--end`: Custom date range in YYYY-MM-DD format
- `--changed-only`: Only show stocks where color changed in latest candle
- `--min-volume`: Minimum average daily volume (e.g., 500000)
- `--min-price`: Minimum stock price (e.g., 5.0 or 10.0)
- `--output`: CSV output path (default: results/nasdaq_screen.csv)
- `--debug`: Show detailed error messages

#### `stockcharts-plot` (Chart Generation)
- `--input`: Input CSV file from screener
- `--output-dir`: Directory for chart images (default: charts/)
- `--period`: Chart timeframe (default: 1d)
- `--lookback`: Historical data window (default: 3mo)

#### `stockcharts-rsi-divergence` (RSI Divergence Screening)
- `--type`: Divergence type: `bullish`, `bearish`, or `all` (default: all)
- `--period`: Data lookback: `1mo`, `3mo`, `6mo`, `1y`, etc. (default: 3mo)
- `--rsi-period`: RSI calculation period (default: 14)
- `--min-price`: Minimum stock price filter
- `--max-price`: Maximum stock price filter
- `--swing-window`: Window for swing point detection (default: 5)
- `--lookback`: Bars to analyze for divergence (default: 60)
- `--output`: CSV output path (default: results/rsi_divergence.csv)

See [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for parameter details.

## Library API

You can also use StockCharts programmatically in your Python code:

```python
from stockcharts.screener.screener import screen_nasdaq
from stockcharts.screener.rsi_divergence import screen_rsi_divergence
from stockcharts.screener.nasdaq import get_nasdaq_tickers
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.indicators.rsi import compute_rsi
from stockcharts.indicators.divergence import detect_divergence

# Screen for green reversals with volume filter
results = screen_nasdaq(
    color='green',
    period='1d',
    lookback='3mo',
    changed_only=True,
    min_volume=500000
)

# Screen for RSI bullish divergences
rsi_results = screen_rsi_divergence(
    divergence_type='bullish',
    min_price=10.0,
    period='6mo'
)

# Get all NASDAQ tickers
tickers = get_nasdaq_tickers()
print(f"Found {len(tickers)} NASDAQ tickers")

# Fetch data and compute Heiken Ashi
data = fetch_ohlc('AAPL', period='1d', lookback='3mo')
ha_data = heiken_ashi(data)

# Calculate RSI and detect divergences
data['RSI'] = compute_rsi(data['Close'], period=14)
divergence = detect_divergence(data)
```

## Project Structure

```
StockCharts/
├── src/stockcharts/          # Main package
│   ├── cli.py                # Command-line entry points
│   ├── charts/               # Heiken Ashi computation
│   ├── data/                 # Data fetching (yfinance)
│   ├── indicators/           # Technical indicators (RSI, divergence)
│   └── screener/             # NASDAQ screening logic
├── scripts/                  # Legacy CLI scripts
├── tests/                    # Unit tests
├── requirements.txt          # Dependencies
└── pyproject.toml            # Package configuration
```

## Requirements

- Python 3.9+
- yfinance >= 0.2.38
- pandas >= 2.0.0
- matplotlib >= 3.7.0
- numpy >= 1.24.0

## Output Examples

### Screener CSV Output
```csv
ticker,color,ha_open,ha_close,last_date,period,color_changed,avg_volume
AAPL,green,225.34,227.89,2024-01-15,1d,True,58234567
MSFT,green,402.15,405.67,2024-01-15,1d,True,25678901
NVDA,green,520.88,528.45,2024-01-15,1d,True,45123890
```

### Chart Output
Charts include:
- Green candles for bullish moves (HA_Close >= HA_Open)
- Red candles for bearish moves (HA_Close < HA_Open)
- Full wicks showing HA_High and HA_Low
- Date labels on x-axis
- Automatic scaling based on price range

## Documentation

- **[LIBRARY_GUIDE.md](LIBRARY_GUIDE.md)**: Comprehensive usage guide with examples
- **[RSI_DIVERGENCE_GUIDE.md](RSI_DIVERGENCE_GUIDE.md)**: RSI divergence screening guide
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)**: Parameter quick reference
- **[VOLUME_FILTERING_GUIDE.md](VOLUME_FILTERING_GUIDE.md)**: Volume filtering strategies
- **[TRADING_STYLE_GUIDE.md](TRADING_STYLE_GUIDE.md)**: Recommendations by trading style
- **[DISTRIBUTION.md](DISTRIBUTION.md)**: Build and distribution guide (for maintainers)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Roadmap

- [x] Publish to PyPI
- [x] Add unit tests and CI/CD
- [x] RSI divergence detection (bullish/bearish price vs RSI divergences)
- [ ] Additional technical indicators (MACD, Bollinger Bands, Stochastic)
- [ ] Multi-ticker comparison charts
- [ ] Backtesting framework
- [ ] Real-time data integration (requires API like Alpaca/Polygon - yfinance is EOD only)
- [ ] Alert/notification system

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- **yfinance**: Yahoo Finance data API
- **pandas**: Data manipulation and analysis
- **matplotlib**: Chart generation
- **NASDAQ**: Official ticker data via FTP

## Support

If you encounter any issues or have questions:
- Open an issue: https://github.com/paulboys/HeikinAshi/issues
- Check the documentation in this repository

---

**Happy Trading! 📈**
