# API Reference

This section provides detailed API documentation for the StockCharts package, automatically generated from source code docstrings.

## Core Modules

- **[Divergence Detection](divergence.md)** - RSI/Price divergence detection algorithms
- **[Pivot Detection](pivots.md)** - Swing point and EMA-derivative pivot identification
- **[RSI Indicator](rsi.md)** - Relative Strength Index calculation
- **[Screener](screener.md)** - Stock screening and filtering logic
- **[Data Fetching](data.md)** - Market data retrieval and caching
- **[Heiken Ashi Runs](heiken_runs.md)** - Run length and percentile statistics for trend maturity

## Usage

Import functions directly from their modules:

```python
from stockcharts.indicators.divergence import detect_divergence
from stockcharts.indicators.rsi import compute_rsi
from stockcharts.indicators.pivots import ema_derivative_pivots
from stockcharts.screener.rsi_divergence import screen_rsi_divergence
```

For complete usage examples, see the [Quick Reference](../quick_reference.md) and [RSI Divergence Guide](../rsi_divergence.md).
