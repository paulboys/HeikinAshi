# StockCharts

A Python library for screening NASDAQ stocks using Heiken Ashi candles to detect trend reversals with volume filtering.

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

### From PyPI (coming soon)
```powershell
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

After installation, you'll have two command-line tools available:

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

### Command-Line Options

#### `stockcharts-screen`
- `--color`: Filter by `red` or `green` candles (default: green)
- `--period`: Aggregation period: `1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo` (default: 1d)
- `--lookback`: Historical window: `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `max` (default: 3mo)
- `--start`, `--end`: Custom date range in YYYY-MM-DD format
- `--changed-only`: Only show stocks where color changed in latest candle
- `--min-volume`: Minimum average daily volume (e.g., 500000)
- `--output`: CSV output path (default: results/nasdaq_screen.csv)
- `--debug`: Show detailed error messages

#### `stockcharts-plot`
- `--input`: Input CSV file from screener
- `--output-dir`: Directory for chart images (default: charts/)
- `--period`: Chart timeframe (default: 1d)
- `--lookback`: Historical data window (default: 3mo)

See [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for parameter details.

## Library API

You can also use StockCharts programmatically in your Python code:

```python
from stockcharts.screener.screener import screen_nasdaq
from stockcharts.screener.nasdaq import get_nasdaq_tickers
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.heiken_ashi import heiken_ashi

# Screen for green reversals with volume filter
results = screen_nasdaq(
    color='green',
    period='1d',
    lookback='3mo',
    changed_only=True,
    min_volume=500000
)

# Get all NASDAQ tickers
tickers = get_nasdaq_tickers()
print(f"Found {len(tickers)} NASDAQ tickers")

# Fetch data and compute Heiken Ashi
data = fetch_ohlc('AAPL', period='1d', lookback='3mo')
ha_data = heiken_ashi(data)
```

## Project Structure

```
StockCharts/
├── src/stockcharts/          # Main package
│   ├── cli.py                # Command-line entry points
│   ├── charts/               # Heiken Ashi computation
│   ├── data/                 # Data fetching (yfinance)
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

- [ ] Publish to PyPI
- [ ] Add unit tests and CI/CD
- [ ] Additional technical indicators (RSI, MACD, Bollinger Bands)
- [ ] Multi-ticker comparison charts
- [ ] Backtesting framework
- [ ] Real-time streaming data support
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
