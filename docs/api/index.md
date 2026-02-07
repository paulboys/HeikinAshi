# API Reference

This section provides detailed API documentation for the StockCharts package, automatically generated from source code docstrings.

## Core Modules

- **[Divergence Detection](divergence.md)** - RSI/Price divergence detection algorithms
- **[Pivot Detection](pivots.md)** - Swing point and EMA-derivative pivot identification
- **[RSI Indicator](rsi.md)** - Relative Strength Index calculation
- **[Beta & Relative Strength](beta.md)** - Rolling beta and market regime detection
- **[Screener](screener.md)** - Heiken Ashi stock screening and filtering logic
- **[Beta Regime Screener](beta_regime.md)** - Risk-on/risk-off regime screening
- **[Data Fetching](data.md)** - Market data retrieval and caching
- **[Heiken Ashi Runs](heiken_runs.md)** - Run length and percentile statistics for trend maturity

## Usage

Import functions directly from their modules:

```python
from stockcharts.indicators.divergence import detect_divergence
from stockcharts.indicators.rsi import compute_rsi
from stockcharts.indicators.pivots import ema_derivative_pivots
from stockcharts.indicators.beta import compute_rolling_beta, analyze_beta_regime
from stockcharts.screener.rsi_divergence import screen_rsi_divergence
from stockcharts.screener.beta_regime import screen_beta_regime
```

For complete usage examples, see the [Quick Reference](../quick_reference.md), [RSI Divergence Guide](../rsi_divergence.md), and [Beta Regime Guide](../beta_regime.md).
