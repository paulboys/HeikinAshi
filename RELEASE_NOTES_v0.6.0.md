# Release v0.6.0 (2025-11-30)

## Summary
This release introduces Heiken Ashi run statistics to contextualize trend maturity and adds percentile-based CLI filters. Documentation has been standardized on `--period` for aggregation (deprecating previous `--interval` usages except in the divergence plot command, which is annotated for migration). A headless-safe matplotlib backend fallback improves reliability in CI and server environments.

## Highlights
- Run statistics (`run_length`, `run_percentile`) now included in screener outputs and programmatic results.
- Percentile filters (`--min-run-percentile`, `--max-run-percentile`) enable targeting extended or early trend phases.
- Documentation overhaul: consistent terminology (`--period` / `--lookback`), new API page `heiken_runs.md`.
- Headless plotting stability: automatic fallback to `Agg` backend when Tk is unavailable.

## Added
- Screener CSV columns: `run_length`, `run_percentile`.
- CLI flags:
  - `--min-run-percentile PCT` (keep runs with percentile ≥ PCT)
  - `--max-run-percentile PCT` (keep runs with percentile ≤ PCT)
- API docs page: `docs/api/heiken_runs.md`.
- Interpretation guidelines for percentile ranges (extended vs emerging moves).

## Changed
- Standardized aggregation flag to `--period` across docs and examples.
- README extended with run percentile usage examples and updated CSV sample.
- `trading_styles.md` corrected (proper separation of `--period` vs `--lookback`).
- Matplotlib backend fallback logic added for divergence chart rendering in headless environments.

## Deprecated / Transitional
- `--interval` remains only in `stockcharts-plot-divergence` (annotated in docs). Will migrate to `--period` in a future release; no functional change yet.

## Upgrade Notes
1. Replace any historical usage of `--interval` with `--period` (except `stockcharts-plot-divergence`).
2. Update automation scripts to parse new `run_length` and `run_percentile` columns.
3. For more stable percentile statistics, consider increasing `--lookback` (e.g. `6mo` or `1y`).
4. Combine run filters with `--changed-only` to distinguish fresh flips from extended continuations.

## Examples
Extended (mature) runs:
```powershell
stockcharts-screen --min-run-percentile 90 --period 1d --output extended_runs.csv
```
Early/emerging runs:
```powershell
stockcharts-screen --max-run-percentile 25 --period 1d --output early_runs.csv
```
Mid-phase runs (balanced):
```powershell
stockcharts-screen --min-run-percentile 40 --max-run-percentile 70 --period 1d
```
Programmatic access:
```python
from stockcharts.screener.screener import screen_nasdaq
results = screen_nasdaq(color_filter="green", period="1d", lookback="3mo")
for r in results:
    print(r.ticker, r.run_length, r.run_percentile)
```

## Headless Environments
The divergence plotting module now auto-detects unavailable Tk backends and applies `matplotlib.use("Agg")` fallback to prevent runtime errors in CI or remote servers.

## Testing & Quality
- Full test suite: 168 passed (1 benign figure warning).
- Lint (ruff) and type checks (mypy) clean post changes.

## Looking Ahead
- Planned migration of `stockcharts-plot-divergence` to use `--period`.
- Potential MACD divergence and average volume (20-day) filters (tracked in roadmap).

## Changelog Reference
See `CHANGELOG.md` for structured semantic entries and comparison links.

---
Release authored automatically via dev branch workflow.
