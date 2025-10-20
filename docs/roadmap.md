# Roadmap & Next Steps

## Near-Term
- Average volume filter (20-day) instead of single-bar volume.
- Percentage-based RSI divergence tolerance.
- Chart overlay for Heiken Ashi + divergence combined.

## Mid-Term
- Multi-timeframe divergence aggregation (daily + weekly alignment).
- Configurable ticker universe via external YAML/JSON.
- Caching layer for faster repeated scans.

## Long-Term
- Live watchlist regeneration (scheduled task integration).
- Web dashboard (FastAPI + lightweight frontend) for interactive filtering.
- Additional indicators (MACD divergence, Stochastics).

## Technical Debt
- Centralize parameter validation across CLI commands.
- Improve error reporting on failed yfinance fetches.
- Expand unit tests for divergence edge cases.

## Research Ideas
- Statistical reliability study: Divergence outcome probabilities.
- Volume divergence vs price/RSI interaction.
- Multi-factor scoring (price structure + divergence strength + volume trend).

## Completed (Historical)
- Heiken Ashi Screener
- RSI Divergence Screener
- Precomputed divergence indices for charts
- Volume filter parameter
- RSI tolerance patch to remove false positives
