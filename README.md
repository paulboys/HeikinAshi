# StockCharts

[![CI](https://github.com/paulboys/HeikinAshi/actions/workflows/ci.yml/badge.svg)](https://github.com/paulboys/HeikinAshi/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/paulboys/HeikinAshi/branch/main/graph/badge.svg)](https://codecov.io/gh/paulboys/HeikinAshi)
[![Docs](https://img.shields.io/website?url=https%3A%2F%2Fpaulboys.github.io%2FHeikinAshi%2F&label=docs)](https://paulboys.github.io/HeikinAshi/)

[![PyPI version](https://img.shields.io/pypi/v/stockcharts.svg)](https://pypi.org/project/stockcharts/)
[![Python versions](https://img.shields.io/pypi/pyversions/stockcharts.svg)](https://pypi.org/project/stockcharts/)
[![Downloads](https://static.pepy.tech/badge/stockcharts)](https://pepy.tech/project/stockcharts)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/paulboys/HeikinAshi/blob/main/LICENSE)

A Python library for screening NASDAQ stocks using Heiken Ashi candles and RSI divergence to detect trend reversals with volume and price filtering.

## Current Version
The latest released version is **0.6.0**. You can verify in Python:
```python
import stockcharts
print(stockcharts.__version__)
```
PyPI badge above always reflects the newest published version.

## Features

### 🧪 NASDAQ Screener
- **Full NASDAQ Coverage**: Automatically fetches all 5,120+ NASDAQ tickers from official FTP source
- **Heiken Ashi Analysis**: Detects red-to-green and green-to-red candle color changes
- **Run Statistics**: Adds `run_length` (consecutive same-color candles) and `run_percentile` (historical maturity rank 0–100) with percentile filters for extended or early trend detection
- **Volume Filtering**: Filter by average daily volume to focus on liquid, tradeable stocks
- **Flexible Timeframes**: Support for intraday (1m-1h), daily, weekly, and monthly charts
- **Custom Date Ranges**: Screen historical data with specific start/end dates
- **CSV Export**: Save screening results for further analysis

### 📊 Chart Generation
- **Heiken Ashi Charts**: Generate candlestick charts from screening results
- **Price/RSI Divergence Charts**: Visualize price action with RSI indicator and marked divergences
- Support for multiple timeframes: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo
- High-quality PNG output for technical analysis
- Automatic divergence detection and highlighting on charts

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

After installation, you'll have four command-line tools available:

### 1. `stockcharts-screen` - Heiken Ashi Color Screening
### 2. `stockcharts-plot` - Heiken Ashi Chart Generation
### 3. `stockcharts-rsi-divergence` - RSI Divergence Screening
### 4. `stockcharts-plot-divergence` - Price/RSI Divergence Charts

## Usage

### 1. Screen for Trend Reversals

**Find green reversals (red→green) for swing trading:**
```powershell
stockcharts-screen --color green --changed-only --min-volume 500000
```
**Find extended (mature) runs (top decile 90%+):**
```powershell
stockcharts-screen --min-run-percentile 90 --period 1d
```

**Find short/early runs (bottom quartile ≤25%):**
```powershell
stockcharts-screen --max-run-percentile 25 --period 1d
```

**Filter mid-maturity runs (40–70% percentile range):**
```powershell
stockcharts-screen --min-run-percentile 40 --max-run-percentile 70 --period 1d
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

### 4. Generate Divergence Charts

**Plot divergences from screener results:**
```powershell
stockcharts-plot-divergence
```

## Documentation

Comprehensive, consolidated documentation lives in the `docs/` directory:

| Topic | File |
|-------|------|
| Project Overview & Architecture | `docs/overview.md` |
| Heiken Ashi Screener Guide | `docs/screener.md` |
| RSI Divergence Screener | `docs/rsi_divergence.md` |
| Parameters & Configuration | `docs/parameters.md` |
| Volume Filtering | `docs/volume.md` |
| Trading Style Guidance | `docs/trading_styles.md` |
| Quick Reference Commands | `docs/quick_reference.md` |
| Roadmap & Next Steps | `docs/roadmap.md` |
| Legacy Mapping | `docs/legacy.md` |

All documentation is consolidated under `docs/`. Legacy root markdown files have been removed.

See also: [CHANGELOG.md](CHANGELOG.md) for release history.

## Hosted Documentation

An interactive, searchable documentation site is published via MkDocs + GitHub Pages.

### Local Preview
```powershell
pip install -r requirements-docs.txt
mkdocs serve
# Visit http://127.0.0.1:8000
```

### Manual Build
```powershell
mkdocs build --strict
# Output generated in ./site/
```

### Deployment (CI Automated)
Docs are automatically built and deployed when you push changes to `docs/`, `mkdocs.yml`, or `requirements-docs.txt` on `main`.

Workflow file: `.github/workflows/docs.yml` using `peaceiris/actions-gh-pages`.

To trigger manually:
```powershell
gh workflow run Deploy Documentation
```

### Site URL
https://paulboys.github.io/HeikinAshi/

If the page is not yet enabled, activate GitHub Pages in repository settings pointing to the `gh-pages` branch.

**Custom analysis with longer lookback:**
```powershell
stockcharts-plot-divergence --input results/rsi_all.csv --lookback 6mo --output-dir charts/analysis/
```

**Limit number of charts and customize RSI:**
```powershell
stockcharts-plot-divergence --max-plots 20 --rsi-period 21
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
- `--min-run-percentile`: Include only tickers with run_percentile ≥ value (0–100)
- `--max-run-percentile`: Include only tickers with run_percentile ≤ value (0–100)
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

#### `stockcharts-plot-divergence` (Divergence Chart Generation)
- `--input`: Input CSV file from RSI divergence screener
- `--output-dir`: Directory for chart images (default: charts/divergence/)
- `--interval`: Data aggregation interval: `1d`, `1wk`, `1mo` (default: 1d)
- `--lookback`: Historical data window (default: 3mo)
- `--rsi-period`: RSI calculation period (default: 14)
- `--swing-window`: Window for swing point detection (default: 5)
- `--divergence-lookback`: Bars to look back for divergence (default: 60)
- `--max-plots`: Maximum number of charts to generate (default: all)

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

# Inspect run statistics for each result
for r in results:
    print(r.ticker, r.run_length, r.run_percentile)

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
ticker,color,ha_open,ha_close,last_date,period,color_changed,avg_volume,run_length,run_percentile
AAPL,green,225.34,227.89,2024-01-15,1d,True,58_234_567,4,78.6
MSFT,green,402.15,405.67,2024-01-15,1d,True,25_678_901,6,92.3
NVDA,green,520.88,528.45,2024-01-15,1d,True,45_123_890,2,24.1
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

## Disclaimer

This project is provided for educational and informational purposes only and does not constitute financial, investment, trading, legal, tax, or other professional advice. Outputs (including screens, indicators, charts, divergences) may contain errors, omissions, delays, or false signals. Trading and investing involve risk of loss, including principal. Past performance or detected patterns do not guarantee future results. Validate all insights independently before acting.

By using this software you accept full responsibility for any decisions and agree to indemnify the author against claims arising from its use. For personalized advice consult a licensed financial professional. See `DISCLAIMER.md` for full details.

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
