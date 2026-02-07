# StockCharts Documentation

Welcome to the official documentation site for the StockCharts technical screening toolkit.

## Quick Navigation
- **Overview**: High-level architecture and purpose
- **Heiken Ashi Screener**: Color-based trend scan
- **RSI Divergence Screener**: Momentum disagreement detection
- **Beta Regime Screener**: Risk-on/risk-off market regime detection
- **Parameters**: All configurable flags
- **Volume Filtering**: Improve signal quality
- **Trading Styles**: Applying outputs to strategies
- **Quick Reference**: Command cheat sheet
- **Roadmap**: Planned enhancements

## Installation
```bash
pip install stockcharts
```
Development:
```bash
git clone https://github.com/paulboys/HeikinAshi.git
cd HeikinAshi
pip install -e .
```

## CLI Summary
```bash
stockcharts-screen --color green --period 1d
stockcharts-screen --min-run-percentile 90 --period 1d    # Extended runs
stockcharts-rsi-divergence --type bullish --min-price 10
stockcharts-plot-divergence --ticker NVDA --period 6mo
stockcharts-beta-regime --regime risk-on                  # Beta regime scan
python scripts/sector_regime.py                           # McGlone sector analysis
```

## Key Concepts
- Heiken Ashi: Smoothed candle representation for trend clarity.
- Run Statistics: `run_length` (current contiguous same-color count) and `run_percentile` (historical maturity gauge, 0–100 inclusive).
- RSI Divergence: Price vs RSI swing mismatch signaling potential reversals.
- Beta Regime: Relative strength vs benchmark (SPY) to detect risk-on/risk-off conditions.
- McGlone Contrarian: 3-criteria buy system (risk-off + VIX spike + market correction).
- Precomputed Indices: Guarantee chart markers align with detected divergences.
- Tolerance: RSI difference threshold (0.5) to prevent noise.

## Contributing
Open issues or pull requests for feature requests, bug fixes, or doc improvements.

## Links
- Source Code: https://github.com/paulboys/HeikinAshi
- PyPI: https://pypi.org/project/stockcharts/

## API Reference
Auto-generated API docs are available under the API section of the navigation.
Direct link: https://paulboys.github.io/HeikinAshi/api/

## License
MIT License. See repository root `LICENSE` file.
