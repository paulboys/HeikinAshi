# Treasury Yield Tracker

Tracks the US Treasury curve and the macro stress indicators that would signal
either a disorderly unwind or a change in Fed policy. It fetches what has a
free API, accepts hand-entry for what does not, and scores every indicator
against a threshold.

## Running it

```bash
# Terminal watchlist
stockcharts-yields

# With the scenario checklists and key dates
stockcharts-yields --scenario all

# Dashboard on http://127.0.0.1:8051
stockcharts-yields-app
```

Set a descriptive user agent first. It is optional but polite, and some
endpoints rate-limit anonymous traffic harder:

```bash
export STOCKCHARTS_USER_AGENT="StockCharts (you@example.com)"
```

## What the decomposition means

A 10-year yield is roughly two things: where investors expect short rates to
average over the next decade, plus a term premium for locking money up. The
dashboard shows the split directly:

```text
10y nominal  =  expected short rate  +  term premium
10y nominal  =  10y real (TIPS)      +  breakeven inflation
```

The expected short rate is derived as `THREEFY10 - THREEFYTP10`. The fourth
chart panel plots term premium against expected short rate, because the
combination that matters is a **term premium rising while expected short rates
fall** — that is supply or fiscal concern rather than policy expectations, and
it is what `evaluate_term_premium` escalates to `alert`.

## Data sources

Every source is keyless.

| Source | Provides | Notes |
| --- | --- | --- |
| Treasury.gov XML | Nominal and real par curves, all tenors | One request returns an entire year |
| FRED CSV | Breakevens, term premium, IORB, repo | Throttles rapid loops; the client paces at 1.1s and retries |
| Treasury FiscalData | Auction cover and indirect share | Filters on `original_security_term` |
| NY Fed Markets API | SOFR, repo operation results | Fresher than the FRED mirrors |
| yfinance | Brent (`BZ=F`), S&P 500 (`^GSPC`) | Through the existing `fetch_ohlc` |

Two inputs have no free feed and are entered by hand, either in the dashboard
form or from the CLI:

```bash
stockcharts-yields --set hyperscaler_coverage=1.35 --set-date 2026-09-20
stockcharts-yields --set sp500_trailing_eps=248.10
```

Values persist to `cache/macro/manual_inputs.json` (override with
`STOCKCHARTS_MACRO_DATA`). Writes are atomic, and a corrupt file falls back to
the defaults in `stockcharts.macro.config` rather than raising.

### Two Brent series disagree

`BZ=F` (front-month futures) and FRED's `DCOILBRENTEU` (spot) can diverge
sharply during a physical supply disruption — by 15% in September 2026. The
dashboard uses the futures contract. If you are comparing against a spot
quote, expect a gap.

### Auction reopenings

A 10-year reopening is filed under a term like `9-Year 11-Month`, not
`10-Year`, so the query filters on `original_security_term`. The indirect
share is `indirect_bidder_accepted / comp_accepted`, which is the convention
quoted in market commentary; dividing by total accepted understates it by
roughly 18 points.

## Watchlist

Nine rows, each scored `ok`, `watch`, `alert` or `unknown`. The `alert` level
comes from the source analysis; the intermediate `watch` level is interpolated
to give earlier warning. **Neither is an official trigger level** — they are
one reader's judgment and live in `stockcharts/macro/config.py` to be re-tuned.

| Row | watch | alert |
| --- | --- | --- |
| 10y / 30y yields | 5.25 / 5.50, or +15bp in 5d | 5.50 / 5.75, or +25bp in 5d |
| 10y real (TIPS) | 2.90 | 3.00 |
| 10y breakeven | 2.50 | 2.60 |
| Term premium | up 10bp over 20d | up, while expected short rates fall |
| Auction results | cover 2.45x, indirect 74% | cover 2.30x, indirect 70% |
| Hyperscaler coverage | 1.5x | 1.2x |
| Brent | $110 | $120 |
| Equity risk premium | ERP under 0.25 | ERP at or below 0, with a selloff and rising yields |
| Repo stress | SOFR at the IORB ceiling, or SRF over $5bn | 5bp through, or SRF over $25bn |

Rows with more than one sub-signal take the worst, and the `Why` column names
which one fired. A missing series yields `unknown` rather than an exception, so
one throttled endpoint degrades a single row instead of blanking the table.

## Scenarios

Four paths by which the Fed might resume buying Treasuries, each with signs to
watch. Signs the dashboard can compute — repo above administered rates, heavy
facility use, yields rising on a risk-off day — are ticked automatically and
labelled `(auto)`. The rest are yours to tick, and persist alongside the manual
values.

Automatic and manual sign identifiers occupy disjoint namespaces, so a computed
tick can never overwrite one of yours.

## Caching and history

History accumulates permanently on disk, so a deep lookback is slow exactly
once. Everything lives as parquet under `cache/macro/`
(`STOCKCHARTS_MACRO_CACHE` overrides the location).

That directory is deliberately a *subdirectory*: the OHLC cache warmer globs
`*.parquet` non-recursively, so macro series are never mistaken for yfinance
tickers and re-fetched.

### How it accumulates

Two different rules, because the two sources paginate differently:

- **Treasury curves** are fetched one calendar year per request. A completed
  year can never change, so it is cached indefinitely; only the current year is
  ever re-fetched. Selecting a longer lookback pulls the extra years once.
- **FRED series** accumulate into a single file per series. A companion
  `.meta.json` records the earliest start ever requested, so the client knows
  whether the cache already reaches back far enough. When it does and the data
  is merely stale, only the recent tail is downloaded (with a ten-day overlap to
  absorb revisions) and merged into the stored history.

Tracking the *requested* start rather than the earliest observation matters: a
start date landing on a weekend never matches an observation, and series such as
`IORB` simply begin later than a deep window. Inferring coverage from the data
would make both look permanently incomplete and re-download everything on every
refresh.

### Backfilling

To pay the cost deliberately rather than on a slow first dashboard load:

```bash
stockcharts-yields --backfill 10     # ten years, with progress
```

Re-running retries only what is missing. Afterwards the dashboard reads from
disk, and the lookback selector goes out to 20Y.

Inspect what is stored with `stockcharts.macro.backfill.cache_summary()`.
