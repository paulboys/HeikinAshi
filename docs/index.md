# StockCharts Documentation

Welcome to the official documentation site for the StockCharts technical screening toolkit.

## Quick Navigation
- **Overview**: High-level architecture and purpose
- **Heiken Ashi Screener**: Color-based trend scan
- **RSI Divergence Screener**: Momentum disagreement detection
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
stockcharts-screen --color green --interval 1d
stockcharts-rsi-divergence --type bullish --min-price 10
stockcharts-plot-divergence --ticker NVDA --period 6mo
```

## Key Concepts
- Heiken Ashi: Smoothed candle representation for trend clarity.
- RSI Divergence: Price vs RSI swing mismatch signaling potential reversals.
- Precomputed Indices: Guarantee chart markers align with detected divergences.
- Tolerance: RSI difference threshold (0.5) to prevent noise.

## Contributing
Open issues or pull requests for feature requests, bug fixes, or doc improvements.

## Links
- Source Code: https://github.com/paulboys/HeikinAshi
- PyPI: https://pypi.org/project/stockcharts/

## License
MIT License. See repository root `LICENSE` file.
