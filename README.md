# Macroscope

[![CI](https://github.com/paulboys/Macroscope/actions/workflows/ci.yml/badge.svg)](https://github.com/paulboys/Macroscope/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/paulboys/Macroscope/branch/main/graph/badge.svg)](https://codecov.io/gh/paulboys/Macroscope)
[![Docs](https://img.shields.io/website?url=https%3A%2F%2Fpaulboys.github.io%2FMacroscope%2F&label=docs)](https://paulboys.github.io/Macroscope/)

[![PyPI version](https://img.shields.io/pypi/v/stockcharts.svg)](https://pypi.org/project/stockcharts/)
[![Python versions](https://img.shields.io/pypi/pyversions/stockcharts.svg)](https://pypi.org/project/stockcharts/)
[![Downloads](https://static.pepy.tech/badge/stockcharts)](https://pepy.tech/project/stockcharts)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/paulboys/Macroscope/blob/main/LICENSE)

Quantitative analysis of broad market data. Macroscope measures a whole
cross-section rather than a single name: breadth statistics across every
NASDAQ listing, Treasury yields and macro stress indicators, relative
strength and beta against a benchmark, sector rotation, and statistical
labelling of market regimes. Every measurement is a deterministic function of
price or rates history, so a result can be recomputed from its inputs and
audited.

The published Python package is named `stockcharts`, which predates the
project's broader scope; the import path is unchanged.

## Current Version

The latest released version is **0.6.1**. You can verify in Python:

```python
import stockcharts
print(stockcharts.__version__)
```

The PyPI badge above always reflects the newest published version.

## What's here

### Cross-sectional screening

- **Full NASDAQ coverage** — fetches all 5,120+ listings from the official FTP source
- **Heiken Ashi state and run statistics** — colour transitions, plus `run_length` (consecutive same-colour bars) and `run_percentile` (where the current run sits in its own history, 0–100), so a run can be described as early or extended relative to the series rather than by eye
- **RSI divergence detection** — price and RSI disagreeing across swing points, in either direction
- **RSI percentile ranking** — current RSI against its own historical distribution instead of fixed 30/70 thresholds
- **Liquidity and price filters** — restrict the cross-section to names whose series are less dominated by microstructure noise
- **Insider transaction screening** — SEC Form 4 flows by ticker or across a universe
- **Cross-asset correlation** — pairwise correlation of daily returns across a watchlist (script, see `scripts/`)
- **CSV export** for every screen, so results feed downstream analysis

### Macro and rates context

- **Treasury yield curve** — nominal and real series, breakevens, term premium and expected short rate
- **Macro stress watchlist** — a snapshot of indicators with thresholds, tracking which are becoming concerning
- **Historical backfill** with a local cache, so series are reproducible offline

### Regimes and relative strength

- **Beta regime** — relative strength against any benchmark, classified risk-on or risk-off by its position against a moving average, with rolling beta and a beta percentile rank
- **Sector regime** — a contrarian sector-rotation reading
- **Regime labelling** — bull, bear and sideways segments fitted to a price series by greedy Gaussian segmentation, rather than assigned by a fixed rule. Labels are fitted retrospectively over the whole series, so the most recent segment is the least stable: adding bars can move or remove the final change point. Descriptive, not predictive
- **Auto-adjusting windows** — weekly aggregation rescales the moving-average period (200d → 40w) so the lookback stays comparable

### Charts and dashboards

- Static Heiken Ashi, divergence and beta-regime charts (Matplotlib, PNG)
- Interactive TradingView-style charts with drawing tools, volume profile and stochastic subplot (Plotly)
- Two Dash applications: one for the screener, one for the macro and rates view
- Aggregation from 1m to 1mo

### Data layer

- A local Parquet cache with incremental extension, freshness checks and a background warmer, so repeated analysis does not re-fetch
- Point-in-time fetches, so a measurement can be reconstructed as of a past date

### Research agent (experimental)

`src/stock_agent/` is a research agent that routes between these analyses
using a specialised decision model, with every number still computed in
Python. It ships with a pre-registered benchmark: see
[`src/stock_agent/eval/PREREGISTERED.md`](src/stock_agent/eval/PREREGISTERED.md)
for the methodology and the `BENCHMARK_*.md` files for results. It is a
study of routing quality, not a trading system.

## Installation

### From PyPI

```bash
pip install stockcharts
```

### From source

```powershell
git clone https://github.com/paulboys/Macroscope.git
cd Macroscope

conda create -n stockcharts python=3.12 -y
conda activate stockcharts

pip install -e .
```

## Command-line tools

| Command | Purpose |
|---------|---------|
| `stockcharts-screen` | Heiken Ashi state and run-percentile screening |
| `stockcharts-plot` | Heiken Ashi charts from screen results |
| `stockcharts-rsi-divergence` | RSI divergence screening |
| `stockcharts-plot-divergence` | Price and RSI divergence charts |
| `stockcharts-beta-regime` | Relative strength and beta regime screening |
| `stockcharts-plot-beta` | Relative strength charts with regime zones |
| `stockcharts-regime` | Label bull, bear and sideways regimes on a series |
| `stockcharts-yields` | Treasury yields and the macro stress watchlist |
| `stockcharts-yields-app` | Dash dashboard for rates and macro |
| `stockcharts-app` | Dash dashboard for the screener |
| `stockcharts-cache` | Manage the local OHLC Parquet cache |
| `stock-agent` | The experimental research agent |

Each command accepts `--help`, which is the authoritative list of its options.

## Usage

### Cross-sectional screening

**Names whose Heiken Ashi state changed on the latest bar:**
```powershell
stockcharts-screen --color green --changed-only --min-volume 500000
```

**Extended runs — the top decile of each series' own run-length history:**
```powershell
stockcharts-screen --min-run-percentile 90 --period 1d
```

**Early runs — the bottom quartile:**
```powershell
stockcharts-screen --max-run-percentile 25 --period 1d
```

**A mid-maturity band, for comparing against the tails:**
```powershell
stockcharts-screen --min-run-percentile 40 --max-run-percentile 70 --period 1d
```

**Hourly aggregation, restricted to the most liquid names:**
```powershell
stockcharts-screen --color green --period 1h --lookback 1mo --min-volume 2000000 --changed-only
```

**Weekly aggregation over six months:**
```powershell
stockcharts-screen --color green --period 1wk --lookback 6mo --changed-only
```

**A fixed historical window, for reproducing a past measurement:**
```powershell
stockcharts-screen --color red --start 2024-01-01 --end 2024-12-31
```

### RSI divergence

```powershell
stockcharts-rsi-divergence --type bullish --min-price 10
stockcharts-rsi-divergence --type bearish --min-price 10 --max-price 100
stockcharts-rsi-divergence --rsi-period 21 --period 6mo
```

### Relative strength and regimes

**Names outperforming SPY, classified risk-on:**
```powershell
stockcharts-beta-regime --regime risk-on --min-volume 500000
```

**Against a different benchmark, on weekly bars:**
```powershell
stockcharts-beta-regime --benchmark QQQ --interval 1wk
```

**Label bull, bear and sideways segments on one series:**
```powershell
stockcharts-regime AAPL --lookback 5y
```

### Rates and macro

```powershell
stockcharts-yields
stockcharts-yields-app
```

### Charts

```powershell
stockcharts-plot
stockcharts-plot --input results/green_changes.csv --output-dir my_charts/
stockcharts-plot-divergence --max-plots 20 --rsi-period 21
stockcharts-plot-beta AAPL --benchmark QQQ
```

### Choosing an aggregation period

The period is a modelling choice, not a style. Shorter bars resolve faster
structure at the cost of more noise and a shorter usable history; longer bars
do the reverse.

| Period | Resolves | Costs |
|--------|----------|-------|
| `1m`–`1h` | Intraday structure | Noise dominates; history is limited and liquidity-sensitive |
| `1d` | Multi-week structure | The default compromise |
| `1wk`, `1mo` | Multi-month and multi-year structure | Few observations; slow to register change |

Indicator windows should be rescaled with the period rather than carried
across unchanged — `stockcharts-beta-regime` does this automatically for
weekly bars.

## Library API

```python
from stockcharts.screener.screener import screen_nasdaq
from stockcharts.screener.rsi_divergence import screen_rsi_divergence
from stockcharts.screener.nasdaq import get_nasdaq_tickers
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.indicators.rsi import compute_rsi
from stockcharts.indicators.divergence import detect_divergence

# Cross-section of fresh Heiken Ashi colour changes, liquidity-filtered
results = screen_nasdaq(
    color="green",
    period="1d",
    lookback="3mo",
    changed_only=True,
    min_volume=500000,
)

# Run statistics put each result in the context of its own history
for r in results:
    print(r.ticker, r.run_length, r.run_percentile)

rsi_results = screen_rsi_divergence(
    divergence_type="bullish",
    min_price=10.0,
    period="6mo",
)

tickers = get_nasdaq_tickers()
print(f"{len(tickers)} NASDAQ listings")

data = fetch_ohlc("AAPL", period="1d", lookback="3mo")
ha_data = heiken_ashi(data)

data["RSI"] = compute_rsi(data["Close"], period=14)
divergence = detect_divergence(data)
```

The macro and regime modules follow the same shape:

```python
from stockcharts.macro.snapshot import build_snapshot, evaluate_watchlist
from stockcharts.indicators.segmentation import detect_regimes
from stockcharts.indicators.beta import analyze_beta_regime, compute_rolling_beta
```

## Documentation

Documentation lives in `docs/` and is published as a searchable site.

| Topic | File |
|-------|------|
| Project overview and architecture | [`docs/overview.md`](docs/overview.md) |
| Heiken Ashi screener | [`docs/screener.md`](docs/screener.md) |
| RSI divergence screener | [`docs/rsi_divergence.md`](docs/rsi_divergence.md) |
| Beta regime | [`docs/beta_regime.md`](docs/beta_regime.md) |
| Treasury yields and macro | [`docs/treasury_yields.md`](docs/treasury_yields.md) |
| Parameters and configuration | [`docs/parameters.md`](docs/parameters.md) |
| Liquidity filtering | [`docs/volume.md`](docs/volume.md) |
| Quick reference | [`docs/quick_reference.md`](docs/quick_reference.md) |
| API reference | [`docs/api/index.md`](docs/api/index.md) |
| Roadmap | [`docs/roadmap.md`](docs/roadmap.md) |
| Contributing | [`docs/contributing.md`](docs/contributing.md) |

See [CHANGELOG.md](CHANGELOG.md) for release history.

### Hosted documentation

Published via MkDocs and GitHub Pages: https://paulboys.github.io/Macroscope/

```powershell
pip install -r requirements-docs.txt
mkdocs serve          # http://127.0.0.1:8000
mkdocs build --strict # output in ./site/
```

Docs are rebuilt and deployed automatically when `docs/`, `mkdocs.yml` or
`requirements-docs.txt` change on `main`
(`.github/workflows/docs.yml`).

## Project structure

```
Macroscope/
├── src/stockcharts/          # Analysis library
│   ├── cli.py                # Command-line entry points
│   ├── app.py                # Dash screener dashboard
│   ├── macro_app.py          # Dash rates and macro dashboard
│   ├── charts/               # Heiken Ashi, interactive, yields, spans
│   ├── data/                 # Fetching, Parquet cache, background warmer
│   ├── indicators/           # RSI, divergence, pivots, beta, segmentation
│   ├── macro/                # Rates series, snapshot, thresholds, backfill
│   └── screener/             # Cross-sectional screens
├── src/stock_agent/          # Experimental research agent and its benchmark
├── scripts/                  # Analysis and plotting scripts
├── tests/                    # Unit and integration tests
└── pyproject.toml            # Package configuration
```

## Requirements

- Python 3.11+
- yfinance >= 0.2.38, pandas >= 2.0.0, numpy >= 1.24.0
- matplotlib >= 3.7.0, plotly >= 5.18.0, dash >= 2.14.0
- pyarrow >= 14.0.0, diskcache >= 5.6.0 (caching)
- psutil >= 5.9.0, multiprocess >= 0.70.0 (parallel screening)
- aeon >= 1.6.0, < 2.0 (regime segmentation)

## Output examples

### Screen results

```csv
ticker,color,ha_open,ha_close,last_date,period,color_changed,avg_volume,run_length,run_percentile
AAPL,green,225.34,227.89,2024-01-15,1d,True,58_234_567,4,78.6
MSFT,green,402.15,405.67,2024-01-15,1d,True,25_678_901,6,92.3
NVDA,green,520.88,528.45,2024-01-15,1d,True,45_123_890,2,24.1
```

### Charts

- Green bars where `HA_Close >= HA_Open`, red where below
- Full wicks from `HA_High` and `HA_Low`
- Detected divergences marked on both price and RSI panels
- Regime zones shaded behind the series

## Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-change`)
3. Commit your changes
4. Push the branch
5. Open a pull request

CI runs `ruff`, `mypy`, `pydocstyle`, the test suite with coverage, and a
strict docs build. See [`docs/contributing.md`](docs/contributing.md).

## Roadmap

- [x] Publish to PyPI
- [x] Unit tests and CI
- [x] RSI divergence detection
- [x] Treasury yields and macro stress watchlist
- [x] Regime segmentation and beta percentile ranking
- [x] Local Parquet cache with incremental extension
- [ ] Additional indicators (MACD, Bollinger Bands)
- [ ] Multi-series comparison charts
- [ ] Wider macro series coverage
- [ ] Intraday data source (yfinance is end-of-day for most history)

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This project is provided for educational and informational purposes only and
does not constitute financial, investment, legal, tax or other professional
advice. Outputs — screens, indicators, charts, divergences, regime labels and
macro readings — may contain errors, omissions, delays or false signals.
Investing involves risk of loss, including principal. Past performance and
detected patterns do not guarantee future results. Validate all findings
independently before acting on them.

By using this software you accept full responsibility for any decisions and
agree to indemnify the author against claims arising from its use. For
personalised advice, consult a licensed financial professional. See
[`DISCLAIMER.md`](DISCLAIMER.md) for full details.

## Acknowledgments

- **yfinance** — Yahoo Finance data access
- **pandas**, **numpy** — data manipulation and numerics
- **matplotlib**, **plotly**, **dash** — charting and dashboards
- **aeon** — time-series segmentation
- **NASDAQ** — official listing data via FTP

## Support

- Open an issue: https://github.com/paulboys/Macroscope/issues
- Browse the documentation: https://paulboys.github.io/Macroscope/
