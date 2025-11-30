# Heiken Ashi Runs

Metrics for assessing trend maturity via consecutive same-color Heiken Ashi candles.

## Overview
The run statistics module computes:
- `run_length`: Number of consecutive same-color (green or red) Heiken Ashi candles ending at the latest bar.
- `run_percentile`: Inclusive percentile rank (0–100) of `run_length` relative to the empirical distribution of all historical run lengths in the fetched dataset.

Inclusive percentile formula:
```
(count of historical runs <= current run_length) / (total runs) * 100
```
This treats ties as fully counted, emphasizing rarity of long streaks.

## Use Cases
- Identify extended moves likely near exhaustion (e.g. `run_percentile >= 90`).
- Focus on early trend phases with possible continuation (e.g. `run_percentile <= 25`).
- Filter mid-maturity setups (e.g. 40–70%) for balanced risk/reward.
- Combine with `--changed-only` to differentiate fresh flips vs. mature continuations.

## Function Reference
```python
from stockcharts.indicators.heiken_runs import compute_ha_run_stats

stats = compute_ha_run_stats(ha_df)
print(stats)
# {'run_length': 6, 'run_percentile': 92.3, 'run_color': 'green', 'total_runs': 57}
```

### `compute_ha_run_stats(ha_df) -> dict`
Parameters:
- `ha_df`: DataFrame containing Heiken Ashi candles with at least `HA_Open` and `HA_Close` columns.

Returns keys:
- `run_length` (int): Current contiguous same-color length.
- `run_percentile` (float): Maturity percentile (0–100 inclusive).
- `run_color` (str): Current run color (`'green'` or `'red'`).
- `total_runs` (int): Number of completed + current runs in sample.

### Notes
- Expand `--lookback` for more stable percentile estimates.
- Very short datasets (< ~30 bars) yield coarse distributions.
- Percentile can be identical for multiple run lengths if distribution is sparse.
- Use alongside price/volume filters for higher-quality signals.

## CLI Integration
`stockcharts-screen` adds two filters:
- `--min-run-percentile PCT` (include runs with percentile >= PCT)
- `--max-run-percentile PCT` (include runs with percentile <= PCT)

CSV output columns (added):
- `run_length`
- `run_percentile`

Example:
```
stockcharts-screen --min-run-percentile 90 --period 1d --output extended_runs.csv
stockcharts-screen --max-run-percentile 25 --period 1d --output early_runs.csv
```

## Interpretation Guidelines
| Percentile Range | Context | Typical Action |
|------------------|---------|----------------|
| 90–100 | Extended trend | Watch for exhaustion / divergences |
| 60–80 | Mature move | Monitor; tighten risk |
| 40–60 | Mid-phase | Neutral; await confirmation |
| 20–40 | Emerging | Potential continuation setups |
| 0–10  | Fresh flip | Early, higher momentum potential |

## Caveats
- Long runs can extend further; percentile is not a reversal guarantee.
- Combine with RSI divergence for higher-conviction counter-trend entries.
- Data gaps or illiquid tickers can distort run distributions—filter by volume.

## Related Modules
- Heiken Ashi construction: `stockcharts.charts.heiken_ashi`
- Screener integration: `stockcharts.screener.screener`
- RSI divergence: `stockcharts.indicators.divergence`
