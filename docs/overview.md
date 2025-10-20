# StockCharts Overview

## Purpose
StockCharts is a Python library and CLI toolkit for screening and visualizing technical setups (Heiken Ashi trends, RSI price divergences) across NASDAQ equities using reproducible programmatic workflows.

## Core Capabilities
- Heiken Ashi candle color screener (bullish/bearish trend snapshot)
- RSI price divergence screener (potential reversal detection)
- Chart generation (price + RSI with divergence markers, Heiken Ashi visualization)
- Batch data retrieval via `yfinance`
- Filtering by price, volume, divergence type, candle color
- Precomputed indices to guarantee chart-plot alignment

## High-Level Architecture
```
stockcharts/
  data/         # Data acquisition (yfinance wrappers)
  indicators/   # Indicator + divergence logic (RSI, divergence detection)
  screener/     # Screeners (Heiken Ashi, RSI divergence)
  charts/       # Plotting utilities (price/RSI, Heiken Ashi)
  cli.py        # Unified CLI entry points
```

## Installation
```
pip install -e .
```
(or add to requirements and `pip install -r requirements.txt`)

## CLI Commands
- `stockcharts-screen` (Heiken Ashi color screener)
- `stockcharts-rsi-divergence` (RSI divergence screener)
- `stockcharts-plot` (generic price/indicator plot)
- `stockcharts-plot-divergence` (price + RSI divergence visualization)

See `docs/screener.md` and `docs/rsi_divergence.md` for detailed usage.

## Quick Reference
Common tasks:
```
stockcharts-screen --color green --interval 1d
stockcharts-rsi-divergence --type bullish --min-price 10 --period 6mo
stockcharts-plot-divergence --ticker AAPL --period 6mo --interval 1d
```
More shortcuts in `docs/quick_reference.md`.

## Distribution & Packaging Notes
- Project uses `pyproject.toml` (PEP 621) for build metadata.
- Entry points expose CLI commands.
- Versioning follows semantic increments (feature additions: minor; fixes: patch).
- Internal modules avoid heavy dependencies (core: pandas, numpy, matplotlib, yfinance).

## Design Principles
- Deterministic screening (consistent output for same parameters/time)
- Readable, dataclass-based result objects
- Minimal, explicit parameters (price, volume, lookback, period)
- Separation of concerns (fetch vs analyze vs visualize)

## Roadmap Snapshot
See `docs/roadmap.md` for detailed upcoming enhancements.

## When to Use This Library
Use StockCharts when you need fast, scriptable screening plus immediate chart validation—especially for workflow automation or nightly scans.
