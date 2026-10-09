# First live run — 2026-10-06

The first calls to the real decision endpoint, made after
[PREREGISTERED.md](PREREGISTERED.md) was fixed and the metrics were validated
against an oracle and a random floor. Purpose: confirm the live wire format,
measure determinism and cost, and record anything that changes how the
benchmark should be read. **Not** a benchmark result — arm B has not yet been
run across the scenario set.

Model requested `jev-1.13.0`; `model_served` was `jev-1.13.0` on every call.

## The wire format, now documented by a real response

| | |
|---|---|
| Endpoint | `https://api.typesafe.ai/v1/systemone` |
| Answer map location | **`answers`** — one of the five wrappers probed, now confirmed |
| HTTP status | 200 on every call, one attempt, no retries |
| Answers missing or malformed | **none**, across every call |
| Usage reported | `input_tokens`, `output_tokens` |

One request carries the whole round: 9 usefulness nouls, `stop_enough`,
`stop_conflict`, `conviction` (score) and the order-balanced shadow Choice
pair — **14 questions, 811 characters of state, ~0.2 s**.

## Latency and cost

| | |
|---|---|
| Latency, 13 calls | min 0.143 s, median 0.210 s, max 0.398 s |
| Input tokens | 2 219–3 839 per round, falling as the menu shrinks |
| Output tokens | 225–512 per round |

Latency is flat in question count, as the earlier measurements predicted:
14 questions cost about what one would. The batched design is therefore both
the unbiased one and the cheap one.

## Determinism

Five identical requests, same state and same question set:

| question | five answers | sd |
|---|---|---|
| `price_history.ohlc` | 0.92, 0.92, 0.91, 0.92, 0.92 | 0.0040 |
| `momentum.rsi_stochastic` | 0.89, 0.89, 0.90, 0.89, 0.90 | 0.0049 |
| `relative_strength.beta_regime` | 0.85, 0.86, 0.86, 0.85, 0.85 | 0.0049 |
| `market_regime.price` | 0.85, 0.85, 0.87, 0.86, 0.85 | 0.0080 |
| `events.insider` | 0.79, 0.77, 0.77, 0.78, 0.77 | 0.0080 |
| `pattern.rsi_divergence` | 0.80, 0.80, 0.82, 0.81, 0.82 | 0.0089 |
| `stop_enough` | 0.02 × 5 | 0.0000 |

Near-deterministic: ±0.01 jitter, and `stop_enough` perfectly stable. Input
tokens were identical on all five, confirming the body did not vary.

## The finding that matters for reading the benchmark

**The usefulness nouls barely separate the top candidates.** Two live runs,
one on a verified synthetic uptrend and one on NVDA's real history:

*Synthetic uptrend*

| round | candidates | highest | lowest | spread | top-two margin |
|---|---|---|---|---|---|
| 1 | 9 | 0.82 | 0.69 | 0.13 | **0.040** |
| 2 | 7 | 0.77 | 0.60 | 0.17 | **0.010** |
| 3 | 5 | 0.75 | 0.37 | 0.38 | **0.020** |
| 4 | 3 | 0.68 | 0.36 | 0.32 | 0.110 |

*NVDA, 504 bars to 2026-10-05*

| round | candidates | highest | lowest | spread | top-two margin |
|---|---|---|---|---|---|
| 1 | 11 | 0.82 | 0.68 | 0.14 | **0.010** |
| 2 | 9 | 0.76 | 0.64 | 0.12 | **0.000** |
| 3 | 7 | 0.75 | 0.45 | 0.30 | **0.020** |
| 4 | 5 | 0.72 | 0.44 | 0.28 | **0.000** |

The overall spread widens as the menu shrinks, but **the top two are nearly
tied in every round of both runs** — and on real data two rounds were *exact*
ties. Seven of eight margins fall below `margin_min = 0.10`, so the policy
took its `act_tied` branch and co-ran the top pair almost every time.

Worth noting on the real run: `events.insider` was ranked last or
near-last in all four rounds (0.68, 0.68, 0.67, 0.66). That is the most
expensive analysis in the registry by a wide margin, and the model
consistently declined it. One run is not evidence of judgement, but it is at
least not evidence against it.

Two consequences, and they pull in opposite directions:

1. **The ranking is unstable exactly where it is tightest.** A top-two margin
   of 0.010 — or 0.000 — against an answer sd of ~0.008 means the argmax is
   not reliably reproducible in those rounds. Anything that acted on the
   argmax alone would be acting on noise.
2. **The policy already absorbs this.** `act_tied` runs *both* of a tied
   pair rather than picking, so an unstable ordering inside the tie band
   costs nothing and the instability never reaches an action. This was chosen
   before the measurement, on the grounds that co-running is cheaper than
   another round trip; it turns out to be the load-bearing decision in the
   whole policy.

It also sharpens what arm B has to demonstrate. With margins this tight,
coverage differences will come from the *band crossings*, not from fine
ordering — and `pair_preference` (criterion 5) becomes the metric most likely
to show whether the scores track evidence at all.

## The order bias did not reproduce

The shadow Choice pair is asked every round and never actuated, precisely so
that the option-order bias motivating the nouls design is measured rather
than assumed. On these states:

- **0 of 4 rounds picked the first option.**
- **3 of 4 rounds agreed with the noul ranking.**

The bias measured in the earlier Latin work did not appear on financial
states with `jev-1.13.0`. The nouls-over-Choice design was therefore
defensible but, on this evidence, **not necessary** — a Choice would likely
have routed similarly. The shadow pair earned its cost by establishing that
for roughly nothing, and it stays, because one run on one state is not enough
to retire the concern.

## Behaviour of the stop and conflict signals

Across the four rounds of the live run, as evidence accumulated:

| round | `stop_enough` | `stop_conflict` | `conviction` |
|---|---|---|---|
| 1 | 0.10 | 0.19 | 1 / 4 |
| 2 | 0.20 | 0.54 | 2 / 4 |
| 3 | 0.25 | 0.61 | 2 / 4 |
| 4 | 0.34 | 0.78 | 2 / 4 |

`stop_enough` rises monotonically, which is the right direction. `conflict`
also rises, reaching 0.78 — above `conflict_veto = 0.60`. Had the model asked
to stop in round 4 it would have been vetoed once, which is the state that
rule exists for. Whether the rise reflects genuine contradiction in the
evidence or just more evidence to disagree with is not something one run can
answer, and criterion 4 is what will settle whether `stop_enough` carries
information at all.

## Three defects found by running live

All three had survived every mock run, which is the argument for doing this
at all.

1. **`--set trace_dir=...` left a plain string where a `Path` was needed**,
   so the first path join raised `TypeError` — after the analysis had been
   paid for. `_coerce` handled bool, int and float but fell through to the
   raw string for everything else. Fixed and pinned by a test.
2. **`model_served` was captured on the response but never written to the
   trace.** A silent substitution upstream would have left no record, and a
   benchmark keyed on the served model would have been keyed on nothing.
   Fixed and pinned by a test.
3. **A single networked tool could hang the whole run, unboundedly.** The
   first NVDA attempt was killed by hand after twelve minutes inside
   `macro.snapshot`. The underlying cause turned out to be a request header
   (see below), but the agent having no bound on a blocking tool was a
   separate defect in its own right.

   This one is a design gap, not a slip. Every budget in `BudgetConfig`
   counts something — iterations, tool calls, decision requests, network
   calls — and every one is tested *between* rounds. None of them can end a
   tool that is still blocking, so the one failure mode that needed a
   time-based bound was the one with no time-based bound.

   Fixed with `max_network_seconds` (default 45 s), applied in `_execute` to
   tools that declare `cost.network`. The re-run hit it exactly as intended:
   `macro.snapshot` was abandoned at 45.02 s, the failure was recorded, the
   tool was disabled for the rest of the run, and the analysis finished with
   its other eight measurements in 48.6 s total.

   Two deliberate limits on the fix. The deadline applies only to networked
   tools: a computing tool cannot block, and it may write an artifact a later
   analysis reads, so running it on a worker thread would introduce a race
   for no benefit. And a thread cannot be killed, so an abandoned fetch runs
   on as a daemon until the process exits; its result is discarded.

## Cost estimates were wrong, and they feed a benchmark arm

`ToolSpec.cost.est_seconds` is not decoration: the `cheapest` arm orders by
it and the policy breaks ties toward the cheap. Three were wrong enough to
matter, two of them only visible on real data.

| analysis | was | now | why |
|---|---|---|---|
| `trend.heiken_runs` | 0.02 s | **1.3 s** | Ranks the current run against every run the ticker ever made, so cost tracks how much history exists, not how much was requested. 0.02 s on 400 synthetic bars, 1.29 s on NVDA. |
| `macro.snapshot` | 8 s | **18 s** | First raised to 45 s from a run that hit the deadline, then corrected once the deadline turned out to be hiding a bug rather than measuring a cost. 17.9 s cold, 3.8 s warm. |
| `events.insider` | 3 s / 3 calls | **120 s / 200 calls** | One request per filing, no cap. A floor, not a measurement. |

`events.insider` also had its filing window narrowed. With the library
default of a year for holdings, plus the recent window and twice the filing
lag, it spans about 545 days — and fetches every filing in it one at a time.
The agent now asks for 120 days, which is the difference between a tool that
answers and one that does not return.

## Why the macro snapshot stalled: a header, not a feed

The twelve-minute hang had an unglamorous cause, and I got it wrong twice
before measuring it properly. Recorded in full because the wrong answers were
each plausible and each would have led somewhere expensive.

**First guess: the insider feed.** It issues one request per filing with no
cap, which is a real latency risk on a large company. But the re-run showed
the stall was in `macro.snapshot`, and the insider analysis had been ranked
last in every round and never ran.

**Second guess: FRED throttling the keyless endpoint.** Timing the snapshot's
components seemed to confirm it — Treasury 0.1 s, auctions 0.7 s, SOFR 1.3 s,
repo 1.6 s, and a single FRED series taking 63.6 s before timing out. From
that I concluded the tool was non-functional until the client learned to use
an API key. **That conclusion was wrong.**

A probe script fetched the same series from the same keyless endpoint in
**0.15 s**. So the endpoint was fine and something about the client's request
was not. Isolating the difference:

| request | result |
|---|---|
| client User-Agent + `Accept: */*` | **timeout at 25 s** |
| probe User-Agent + `Accept: */*` | **timeout at 25 s** |
| client User-Agent, no `Accept` | 200 in 0.2 s |
| probe User-Agent, no `Accept` | 200 in 0.2 s |
| no headers at all | 200 in 0.1 s |

Not the User-Agent — **the `Accept` header**. FRED's `fredgraph.csv` accepts
the connection and then never responds when one is present. Any value:

| `Accept` | two attempts |
|---|---|
| `*/*` | timeout, timeout |
| `text/csv` | disconnected, disconnected |
| `text/csv, */*` | timeout, disconnected |
| *(omitted)* | **200 in 0.2 s, 200 in 0.1 s** |

Eight of eight consistent. `client.py` sent `Accept: */*` on every request,
so each FRED series burned three retries at 20 s before being recorded as an
error — about 63 s per series, eleven series, which is the twelve minutes.

**The fix is to omit the header.** Semantically identical under HTTP, and
verified safe on the shared code path: Treasury, FiscalData and both NY Fed
endpoints return **byte-identical** responses with and without it.

| | before | after |
|---|---|---|
| `fetch_series("T10YIE")` | 63.0 s, `RemoteDisconnected` | **0.63 s, 498 rows** |
| `build_snapshot()` | never completed | **17.9 s, 0 errors, 9 rows** |
| `macro.snapshot` tool | abandoned at the 45 s deadline | **3.8 s warm, succeeds** |

So the macro analysis went from permanently unusable to working, and the
agent's registry now carries a measured 18 s rather than the 45 s I had
written down from the failure.

### What this says about the FRED API key

**The key was not the fix and is not needed.** With the header removed, the
keyless endpoint serves the full eleven-series watchlist in about 4.5 s, and
is in fact *faster* than the documented API (0.41 s against 0.64 s per series
on a like-for-like probe). Both routes returned identical values for all
eleven.

A key remains defensible on other grounds, and the choice is worth making
deliberately rather than by default:

- `fredgraph.csv` is the endpoint behind FRED's graphing front end, not a
  documented API. It carries no stability guarantee, no published rate limit,
  and it just demonstrated it will silently hang on an ordinary header.
- `api.stlouisfed.org` is versioned and documented, allows 120 requests a
  minute, and returns proper error codes — an unregistered key gives
  `HTTP 400: "The value for variable api_key is not registered"` rather than
  a hang.
- Against that: it is slower here, it needs a second parse path for JSON, and
  it makes a free account a prerequisite for anyone running the dashboard.

The honest recommendation is to support a key as an **optional, preferred**
route with the keyless one as fallback, so the dashboard keeps working with
no account while anyone who wants the supported endpoint can have it. That is
a robustness improvement, not a fix, and nothing is currently broken without
it.

### What this says about the deadline

The deadline did not become pointless once the bug was fixed. It is what
turned an unbounded hang into a 45-second loss and a recorded failure, and it
is what will contain the next feed that misbehaves. But it also masked the
bug: a tool that fails identically every time looks like an expensive tool,
which is exactly how a 45-second cost estimate ended up in the registry. The
lesson is that a repeated timeout is a reason to investigate, not a
measurement to record.

## Safety

- The key never appears in the trace (checked directly against the loaded
  value, not by pattern).
- No orders, no accounts, no money moved. The agent has no such capability
  and the report says so on every run.
- Frames from the live run were recorded to disk, so this exact analysis can
  be reproduced offline without re-fetching prices that will be revised.
- The abandoned `macro.snapshot` fetch was left to finish in the background
  rather than interrupted mid-request, so nothing was half-written.
- The FRED key probe never prints the key, and redaction was verified with a
  deliberately invalid key before the real one existed. This matters because
  FRED takes the key as a URL query parameter, so it can otherwise reach
  tracebacks, logs and HTTP error bodies.

## What this does not establish

Arm B has not been benchmarked. Nothing here says whether the routing beats a
decision tree — only that the apparatus works, the answers are stable enough
to measure, and the cost is small. The comparison is the next run, and the
criteria for it were fixed before this one.
