# Timeframes and Detector Sensitivity

Two parameters set the scale of every measurement in this library, and a
third group sets how readily a detector fires. Choosing them is a modelling
decision: each one trades resolution against noise and against the number of
observations available.

## Aggregation period (`--period`)

The bar interval: `1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo`.

| Period | Resolves | Costs |
|--------|----------|-------|
| `1m`–`1h` | Intraday structure | Noise dominates; history is short and sensitive to liquidity |
| `1d` | Multi-week structure | The default compromise |
| `1wk` | Multi-month structure | Few observations per year |
| `1mo` | Multi-year structure | Slow to register change |

Indicator windows are expressed in bars, so they do not carry across periods
unchanged. A 200-bar moving average is roughly ten months of daily data and
roughly four years of weekly data. `stockcharts-beta-regime` rescales
automatically for weekly bars (200d → 40w); elsewhere the rescaling is yours
to make.

## Lookback window (`--lookback`)

How much history is fetched: `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`,
`ytd`, `max`.

The lookback has to be long enough to contain the indicator window several
times over, or a statistic is being computed on too few observations to mean
anything. A run percentile, for instance, ranks the current run against the
history in the window — on three months of daily bars there may be only a
handful of prior runs to rank against.

## Explicit date range (`--start` / `--end`)

Use an explicit range to reconstruct a measurement as of a past date. This is
the reproducible form: a lookback is relative to today and so returns
different data tomorrow.

Validity rules:

- `--lookback` cannot be combined with `--start` / `--end`.
- When neither is given, a default lookback is used (`1y` for most commands).

## Multi-scale analysis

Measuring the same cross-section at two periods separates persistent
structure from short-lived structure. What survives both scales is the more
robust finding.

```bash
# Multi-month structure
stockcharts-screen --color green --changed-only --period 1wk --lookback 1y

# Multi-week structure
stockcharts-screen --color green --changed-only --period 1d --lookback 3mo
```

Intersecting the two result sets is a cheap robustness check, not a
confirmation: agreement across scales says the structure is not an artefact
of one bar size, nothing more.

## Detector sensitivity

The swing window and RSI period govern how readily a divergence is detected.
They trade false positives against false negatives, and there is no setting
that avoids both.

| Setting | Effect |
|---------|--------|
| Swing window 7, RSI period 21 | Smoother; fewer detections, later |
| Swing window 5, RSI period 14 | Default |
| Swing window 3, RSI period 9 | Noisier; more detections, earlier |

Pivot span behaves the same way — see
[Pivot Detection](api/pivots.md#span-selection).

A lower setting is appropriate for generating a candidate set to examine; a
higher one for characterising structure that has already been established.
Reporting results from several settings without saying which was chosen in
advance is how a detector is made to appear more accurate than it is.

## Interpreting a detection

A divergence is a statement about two series disagreeing over a window. It is
descriptive, not predictive, and it is worth recording alongside:

- **Magnitude** — how large the RSI difference is between the swing points
- **Price context** — where the detection sits relative to the recent range
- **Volume behaviour** — whether participation expanded or contracted
- **Cross-sectional alignment** — how many other names and the index show the
  same thing at the same time

The last of these is what this library is built for. A detection that fires
across a third of the cross-section at once is a market-level observation;
the same detection on one name is close to noise.

## Reproducibility

Name output files for the parameters that produced them, so a result can be
traced back to its inputs:

```bash
stockcharts-screen --color green --changed-only --period 1d --lookback 3mo \
  --output results/ha_green_1d_3mo.csv
```

For a measurement that must be reconstructible exactly, prefer `--start` /
`--end` over `--lookback`.
