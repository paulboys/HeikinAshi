# Next Steps / Quality Notes

## Current MVP
- Fetch daily/weekly/monthly OHLC via yfinance
- Compute Heiken Ashi values
- Plot simple Heiken Ashi candlesticks to PNG via CLI
- Basic unit test for computation logic

## Suggested Improvements
1. Add proper time scaling on x-axis (dates instead of index counter)
2. Add option to show standard candlesticks alongside HA
3. Integrate logging instead of print
4. Add exception handling & user-friendly error messages in CLI
5. Package console script entry point via pyproject (e.g., `stockcharts-ha` command)
6. Add CI workflow (GitHub Actions) for lint + test
7. Improve test coverage (edge cases: single row, missing columns, gaps)
8. Implement caching mechanism for fetched data
9. Support intraday intervals (1h, 15m) with rate-limit awareness
10. Add color theming & style config

## Code Quality
- Consider adding type hints for public functions (already partly used)
- Add Ruff rule sets for formatting or integrate black/ruff combined

## Documentation
- Expand README with explanation of Heiken Ashi methodology and example output image

## Licensing
- Replace placeholder name/email in pyproject & LICENSE with actual values
