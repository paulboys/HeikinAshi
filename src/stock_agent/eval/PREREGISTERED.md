# Preregistration

This file fixes what the benchmark measures, what counts as success, and what
counts as failure — **before the decision model is called even once**. It is
written against mock arms only. Nothing here may be revised after a live run;
changes go in a dated amendment section at the bottom, with a reason.

The point is not to make the decision model look good. A result showing the
routing adds nothing is a successful experiment.

## The question

Can a specialised decision model (Jev / TypeSafe "System One") route among
deterministic financial-analysis tools better, faster or more cheaply than a
hand-built decision tree?

The model never computes anything. It answers only *"which analysis is useful
next"* and *"is this enough to stop"*. Python computes every number.

## Arms

All four arms share the registry, the as-of chokepoint, the policy, the
guards and the trace. **They differ in exactly one thing: how usefulness is
scored.** Every arm's answers pass through the same `policy.decide`, so no
difference in outcome can come from one arm getting a different loop.

| Arm | What it is |
|---|---|
| **A `rules`** | A decision tree built from this repository's own domain logic. |
| **A′ `cheapest`** | Cheapest applicable analysis first, never stops early. A floor. |
| **R `random`** | Seeded uniform scores. The other floor. |
| **B `jev`** | The decision model. |
| — `oracle` | Told each scenario's expectations. **Not a competitor**; it exists to validate the metrics. |

**Arm A is deliberately given more information than arm B.** It reads the
numeric state through `observe()`; the model sees only the rendered text. A
handicapped baseline would make the hypothesis easy to confirm and the result
worthless, so the asymmetry runs against the hypothesis on purpose.

## Scenarios

Fifteen: six minimal pairs (twelve) plus three controls. Within a pair, both
halves share a base series and differ in **one** planted feature, so the only
defensible difference in routing is the one analysis measuring that feature.

| Pair | Feature planted | Pivotal analysis |
|---|---|---|
| `trend` | nine green Heiken Ashi candles | `trend.heiken_runs` |
| `divergence` | lower price low against a higher RSI low | `pattern.rsi_divergence` |
| `volume` | final five bars at 6× volume | `volume.surge` |
| `volatility` | last fifty bars turn sharply volatile | `volatility.realised` |
| `momentum` | five bars at −3%, driving RSI to 21 | `momentum.rsi_stochastic` |
| `relative_strength` | decline against an advancing benchmark | `relative_strength.beta_regime` |

Controls: `short_history` (40 bars, most analyses gated out), `featureless`
(nothing planted), `several_features` (divergence, volume surge and
volatility spike together).

**Labels are routing expectations, never market truths.** A scenario asserts
"an analysis that never looked at volume overlooked information that is
present", never "this stock will go up". No scenario asserts a price
direction, and nothing here is a claim about returns.

**Every planted feature is verified against the production detector before
use** (`scenarios.verify_all`). This is not ceremony: a base series was found
to fire a bearish divergence by chance, which would have made a scenario
labelled "no divergence" silently wrong and both arms identically mistaken.
A benchmark whose features do not fire measures nothing.

## Two regimes

Run under both, because they answer different questions.

- **`free`** — nothing capped. Any arm that runs every applicable analysis
  covers every expectation, so **coverage is uninformative here** and the
  real metrics are precision, nDCG, forbidden hits, redundancy and cost.
- **`budgeted`** — `max_tool_calls = 4`, tight enough that no arm can run
  everything. Coverage has to be earned by choosing. **This is the headline
  regime.**

## Metrics

Routing, per run, against the scenario's declared expectations:

- **`required_coverage`** — fraction of expected analyses run. *Undefined
  (NaN) and excluded from averages when a scenario expects nothing.*
- **`precision`** — fraction of analyses run that were expected. Same
  exclusion.
- **`pivotal_found`** — whether the one analysis the scenario turns on ran.
  The single most informative field for a minimal pair.
- **`forbidden_hits`** — count of analyses the scenario marks as wasted.
- **`steps_to_coverage`** — decision rounds before coverage completed.
- **`redundant_calls`** — executions beyond one per distinct analysis.
- **`nDCG@k`** — over the full probability vector, per round, on the menu
  actually offered. *Rounds with nothing relevant on the menu are excluded.*
  The only metric that notices an arm ranking the right analysis second.
- **`pair_preference`** — for each minimal pair, did the arm score the
  pivotal analysis *higher on the half where the feature is actually
  planted*? Reported as the mean present-minus-absent gap. This is the
  strictest test the scenario set supports: it cannot be satisfied by running
  everything, nor by a prior that happens to favour a cheap analysis. The
  mean gap is the headline; the win rate is noisy at six pairs.

Cost: decision-model calls, latency, tool calls, network calls, wall time.

Comparisons use a **paired bootstrap** (2000 resamples, seed 7) on B − A,
paired because the arms face identical scenarios.

Calibration ports the arithmetic from the Latin work's `jev_calibration.py`
unchanged — Mann-Whitney AUC with ties at 0.5, `boot_auc(n=2000, seed=7)`,
Brier against a base-rate forecaster plus skill score, ten reliability bins,
ECE — so numbers are comparable across the two projects. Applied to the
usefulness nouls **and** to `stop_enough`, where the label is "every expected
analysis had already run, so stopping would have lost nothing" — the only
definition under which sufficiency has a knowable answer.

### Metric validation (passed before any live call)

Required: the oracle arm scores near-perfect and random near chance in the
budgeted regime. Thresholds `oracle_coverage ≥ 0.90`, `random_coverage ≤
0.75`. Measured:

| | coverage | nDCG | pair gap |
|---|---|---|---|
| `oracle` | **1.00** | **0.96** | **+0.85** |
| `random` | **0.21** | **0.46** | **+0.04** |

The metrics can therefore distinguish good routing from bad. Reaching this
required fixing three defects that had made them nearly blind:

1. **Coverage and nDCG were averaged over the nine scenarios that expect
   nothing**, where both are undefined. That handed every arm a free perfect
   score, putting random at 0.82 coverage and the oracle at 0.25 nDCG. Both
   are now NaN there and excluded from averages.
2. **nDCG was scored on rounds whose menu held nothing relevant**, counting
   them zero and pulling every arm toward the same middling number.
3. **The random arm was seeded once for the whole benchmark**, so the
   generator handed out the same draw at the same call position in every
   scenario — including both halves of a minimal pair, which made it register
   "no preference" through determinism rather than chance. It is now seeded
   per scenario (`seed ^ crc32(name)`), which both keeps it reproducible and
   makes it a real floor: its coverage fell from 0.61 to 0.21.

## Mock-arm baseline

Recorded here so a live result cannot be compared against a moved target.

**`free`**

| arm | cov | prec | nDCG | forbidden | tools run | calls | pair gap |
|---|---|---|---|---|---|---|---|
| `rules` | 1.00 | 0.17 | 0.71 | 0.00 | 8.53 | 6.27 | +0.000 |
| `cheapest` | 1.00 | 0.16 | 0.57 | 0.80 | 9.67 | 3.87 | +0.000 |
| `random` | 0.36 | 0.09 | 0.54 | 0.47 | 5.60 | 3.33 | −0.119 |
| `oracle` | 1.00 | 0.57 | 0.96 | 0.00 | 1.73 | 1.53 | +0.850 |

**`budgeted`**

| arm | cov | prec | nDCG | forbidden | tools run | calls | pair gap |
|---|---|---|---|---|---|---|---|
| `rules` | 0.57 | 0.20 | 0.66 | 0.00 | 4.27 | 2.00 | +0.000 |
| `cheapest` | 0.57 | 0.14 | 0.47 | 0.00 | 5.87 | 1.00 | +0.000 |
| `random` | 0.21 | 0.06 | 0.46 | 0.33 | 4.33 | 1.87 | +0.039 |
| `oracle` | 1.00 | 0.57 | 0.96 | 0.00 | 1.73 | 1.47 | +0.850 |

### The finding that shapes what arm B has to beat

**Both deterministic baselines score the pivotal analyses with no reference
to the data at all.** Their pair gap is exactly 0.000 across all six pairs,
and scoring them by hand confirms it: `rules` gives `volume.surge` 0.72
whether volume surged sixfold or not, and `trend.heiken_runs` 0.88 whether
the run is 23 candles or one. Arm A routes by a fixed priority ordering, not
by reading evidence. Arm A′ routes by cost, which cannot depend on data by
construction.

This is not a flaw in arm A — a priority ordering is what a decision tree
is — but it does locate precisely where a decision model could earn its
keep. **If arm B scores an analysis higher when the thing it measures is
actually present, it is doing something no baseline here does.** It is also
the one metric a lucky prior cannot fake.

## What would confirm the hypothesis

Committed in advance. In the **budgeted** regime, arm B must:

1. **Beat random** on `required_coverage`, paired-bootstrap 95% interval on
   B − R excluding zero. *If this fails the hypothesis is dead* — the routing
   is not routing.
2. **Beat `cheapest`** on `required_coverage` or `nDCG`, interval excluding
   zero. *If this fails the routing adds nothing* over ordering by cost, and
   arm B degrades to A′.
3. **Match or beat `rules`** on `required_coverage` with no more than
   `rules`' tool calls. Beating A is the interesting result; matching A at
   lower cost is also a result.

And, independently:

4. `stop_enough` must **discriminate**: AUC bootstrap interval entirely above
   0.5. If it does not, `stop_threshold = 0.70` is indefensible and stopping
   must move wholly into Python.
5. **`pair_preference` mean gap must be positive**, against +0.000 for both
   deterministic baselines and +0.04 for random. This is the claim worth the
   most: it is direct evidence that routing responds to evidence rather than
   to a fixed ordering. A gap at or below zero means arm B is a priority list
   with a bill attached, whatever its coverage.

## What would refute it

Any of: B at or below R on coverage; B indistinguishable from A′; B needing
materially more calls than A for the same coverage; or nouls so miscalibrated
that only their ranking carries signal — in which case the honest conclusion
is that the agent is A′ with extra steps and a bill.

## Known limitations, stated in advance

1. **`market_regime.price` can never be "required".** `detect_regimes`
   segments *any* series: a steady advance with constant drift still yields
   bull, sideways and bear segments, because the segmenter finds distribution
   shifts rather than trend changes. A "regime change present vs absent"
   minimal pair is therefore **not constructible**, and the planned sixth
   pair was replaced with the momentum pair. The analysis appears only in
   `forbidden`, where its nine-second cost makes it the clearest example of
   wasted work. **This penalises choosing it**, which is a declared cost
   judgement, not evidence the analysis is useless.
2. **Synthetic data only.** Scenarios come from seeded GBM. A model that
   routes well on synthetic series may not on real ones.
3. **Nine of fifteen scenarios expect nothing**, so coverage and precision
   average over six. The intervals are correspondingly wide and are reported,
   not hidden.
4. **`macro.snapshot` and `events.insider` never run** in the benchmark: both
   reach the network outside the price provider and are withheld on synthetic
   data. Two of twelve analyses are therefore untested by it.
5. **Determinism of the decision model is unverified** until Phase 5 repeats
   one request five times.
6. **Arm A is one person's decision tree.** A better one may exist. It is
   checked against being a straw man (it avoids every forbidden analysis and
   beats both floors on nDCG), but it is not optimal.

## Amendments

### 2026-10-07 — amendment 1: usefulness conditions in the tool descriptions

**Reason.** Benchmark 2 established that arm B's scores respond to the state
only where the state restates a tool's own output. Re-reading the
`bench_02` traces located a second, narrower channel that had been there all
along and was not designed in.

At the first decision round, across the fifteen scenarios, each tool's score
range is:

| tool | score range | description names a usefulness condition? |
|---|---|---|
| `volume.surge` | 0.18 | no — moves because the state restates its output |
| **`signal.mcglone`** | **0.15** | **yes** — "most informative when the market is already under stress" |
| `market_regime.price` | 0.06 | partly — "bull, bear and sideways stretches" |
| `trend.heiken_runs` | 0.03 | no |
| `volatility.realised` | 0.03 | no |
| `momentum.rsi_stochastic` | 0.02 | no |
| `pattern.rsi_divergence` | 0.02 | no |
| `relative_strength.beta_regime` | 0.02 | no |
| `volatility.vix` | 0.02 | no |

`signal.mcglone` is the only tool whose score both varies materially and is
not explained by redundancy. Its score tracks drawdown at **r = −0.79**
(−0.80 excluding `short_history`), monotonically, 0.62 at no drawdown to 0.74
at −28.6%. It is also the only description that tells the model *what
condition makes the analysis worth running*. Every other description says
what the tool computes and never when it matters.

The state itself is not the limiting factor. Across the fifteen scenarios it
carries 14 distinct drawdowns spanning +0.0% to −28.6%, 14 distinct 63-bar
returns spanning +29.9% to −15.3%, and a realised-volatility ratio spanning
0.5x to 2.3x. `volatility.realised` scored 0.75–0.78 across that entire
4.6-fold swing in the quantity it measures.

**The change.** One sentence added to `jev_description` for every tool except
`signal.mcglone`, naming the condition under which that analysis is most
informative, in the same register as `signal.mcglone`'s existing clause.
**Nothing else changes** — not the state, not `summarize_frame`, not the
question templates, not the policy thresholds, not the scenarios. The
`market_regime.price` hindsight caveat is retained unaltered.

**Cost.** Fifteen scenarios, budgeted regime, arm B only: 30 decision calls,
the same as benchmark 2.

#### Predictions, recorded before the first call

**P1 - DO THE DESCRIPTIONS WIDEN THE SCORES?** (primary) For the four tools
whose named condition is *observable in the state* — `trend.heiken_runs`,
`momentum.rsi_stochastic`, `volatility.realised`, `market_regime.price` — the
first-round score range across the fifteen scenarios rises from 0.02–0.06 to
**≥ 0.10**, moving toward `signal.mcglone`'s 0.15.

**P2 - DOES THE RIGHT HALF SCORE HIGHER?** The `pair_preference` gap for the
**volatility** and **momentum** pairs reaches **≥ +0.05**. Both currently sit
at +0.01, inside the ±0.008 answer jitter measured in benchmark 1. This is
criterion 5's question asked again, with the state untouched.

**P3 - THE ARTIFACT CONTROL: do tools whose condition is absent from the state
stay flat?** (the negative control, and the one that makes this a test)
`relative_strength.beta_regime` and `volatility.vix` receive clauses whose
conditions reference the benchmark index and the broad market. **Neither
appears anywhere in the state.** Their ranges must stay **≤ 0.05**. If they
rise as much as P1's tools, then adding any conditional sentence inflates score
variance — a prompt-length or hedging artefact — and the result is *not*
evidence of condition-matching against the state. P1 passing while P3 also
rises refutes the mechanism, not just the magnitude.

**P4 - STABILITY: does the one untouched tool drift?** `signal.mcglone` is
untouched. Its range should stay ≈0.15 and its drawdown correlation ≈−0.79. A
drift here means run-to-run variation large enough to swamp P1 and the
comparison is void.

**P5 - DECLARED ASYMMETRY** (recorded, never a prediction).
`pattern.rsi_divergence`'s condition — price making an extreme that momentum
did not confirm — is not evaluable at the first round, because RSI does not
exist in the state until `momentum.rsi_stochastic` has run. Its pair gap is
**not** expected to move, and a flat result there is not evidence against P1.

#### What would refute the hypothesis

- **P1 fails** (ranges stay ≤0.05): tool framing is not a control surface,
  and the flatness lives in the question's form — a proposition whose truth
  value the data does not change — rather than in how the tools are
  described. The next experiment is then the comparative question, not more
  prompt text.
- **P3 fails** (the unobservable-condition tools move too): the effect is an
  artefact of longer, hedged descriptions. P1 would then mean nothing.
- **P4 fails**: the measurement is too noisy to carry either conclusion.

#### Declared validity threat

The clauses were written by me with full knowledge of the scenario set, which
is experimenter leakage and has to be stated rather than managed quietly.
Three things constrain it:

1. **Both halves of a minimal pair receive an identical description.** No
   clause can indicate which half the model is looking at, so a pair gap can
   move only if the clause is combined with the numbers in the state. This is
   what makes P2 a real test rather than a relabelling.
2. **No clause names a state field, a number, or a threshold.** Each names a
   market condition in plain terms, as `signal.mcglone`'s already does.
3. **P3 exists precisely because I wrote the clauses.** Two of them name
   conditions I know to be invisible in the state. If the effect were coming
   from me rather than from the model, those two would move with the rest.

A positive result supports the narrow claim that *a description naming a
usefulness condition raises a tool's coupling to the state*. It does not
support the claim that arm B routes well without such hints, and must not be
reported as such.

### 2026-10-07 — amendment 2: a comparative routing question

**Reason.** Benchmark 3 widened the per-tool score ranges and turned the
criterion 5 pair gap positive, and changed the routing not at all. Across
both live runs, every scoring round landed in `act_tied`:

| | bench 2 | bench 3 |
|---|---|---|
| scoring rounds | 30 | 27 |
| median top1 − top2 margin | 0.030 | 0.030 |
| rounds reaching `margin_min` = 0.10 | 0/30 | 0/27 |
| rounds in `act_clear` | 0 | 0 |

`act_clear` has never fired. Fifty-seven rounds of evidence say the policy
cannot separate the top two candidates, so it co-runs both, and that is where
arm B's standing cost failure against `rules` comes from.

The diagnosis is in the question's truth condition, not in the state or the
tool text. `usefulness_question` asks whether an analysis *would add
information not already implied* by what has been measured. At the first
round, with only the bootstrap run, that proposition is true for every
candidate — so near-identical probabilities are **correct answers**, and no
amount of state detail or description text can spread them. Two prior
experiments changing the inputs confirm it; this one changes the proposition.

A coherence measure makes the same point. Under a genuine "which single one
is best" reading, the winner should take a large share of the probability
mass. Measured:

| | bench 2 | bench 3 | uniform floor |
|---|---|---|---|
| top candidate's share of total usefulness | 0.156 | 0.134 | 0.111 |

Benchmark 3 moved it *toward* uniform.

**The change.** A second noul per candidate, comparative and single-condition,
asked alongside the existing absolute one and routed on in its place:

> *instructions:* `{_CTX}` The analysis under consideration is `"{title}"`:
> `{description}` Exactly one analysis under NOT YET MEASURED is the best use
> of the next step. Return the probability that it is this one.
>
> *true:* No other analysis under NOT YET MEASURED would sharpen the
> conclusion about `{objective}` more than `"{title}"` would.
>
> *false:* At least one other analysis under NOT YET MEASURED would sharpen
> the conclusion about `{objective}` more than `"{title}"` would.

This proposition is true for at most one candidate, so a flat answer across
nine candidates is now *incoherent* rather than correct. It carries no option
list, so it inherits the independent-noul design's immunity to option-order
bias — which benchmark 2's shadow Choice measured at 30/30 order-stable
anyway.

**Asked alongside, not instead.** Latency barely grows with question count
(`questions.py` property 2), so keeping the absolute noul costs almost
nothing and buys a within-request paired comparison of the two framings on
byte-identical state. That removes run-to-run drift, which was not negligible:
`signal.mcglone`'s untouched range moved 0.15 to 0.17 between benchmarks 2
and 3.

**Change points.** `jev/questions.py` (add the question and include it in
`build_question_set`); `loop.py:239-247` (parse a second map into `parsed`);
`loop.py:413` (pass the comparative map to `policy.decide`). **Unchanged:**
the state and `summarize_frame`, every tool description, `policy.decide` and
all its thresholds, `stop_enough`, `stop_conflict`, `conviction`, and the
scenarios. Budget and current-leaning framing are deliberately deferred to a
later amendment; confounding two interventions is the mistake amendment 1
made with its control.

**Cost.** The request grows from 14 questions to 23 in the first round. Two
calls per scenario as before gives 27–30 calls. If `act_clear` fires and one
tool runs per round instead of two, more rounds are needed to spend the
four-call budget: worst case about four rounds per scenario, **60 calls**.
Stated as a range because amendment 1's estimate was quoted as a point.

#### Predictions, recorded before the first call

**C1 - DECISIVENESS: does it separate the top two candidates?** (primary) On
the comparative map, the median top1 − top2 margin is **≥ 0.10**, against 0.030
in both prior runs, and `act_clear` fires in **at least half** of scoring
rounds, against 0 of 57.

**C2 - COHERENCE: does one candidate own the probability mass?** The top
candidate's share of the total comparative probability is **≥ 0.30**, against
0.156 and 0.134 measured on the absolute map and a 0.111 uniform floor.

**C3 - IS THE WINNER THE RIGHT ONE?** (the safeguard that licenses C1) A wider
margin is worthless if the winner is arbitrary, and a confidently arbitrary
ranking is *worse* than today's tie, because the policy would act on it.
Against benchmark 3, all three must hold: **nDCG ≥ 0.67**, **pivotal reach ≥
4/7**, **mean pair gap ≥ +0.023**. C1 passing while any of these falls is the
signature of manufactured confidence and the result is a revert, not a win.

**C4 - COST: no more tool calls than the rule tree?** (the criterion arm B has
never passed) Tool calls against `rules`: the 95% paired-bootstrap interval on
B − A **includes or falls below zero**, against `+1.000 [+0.533, +1.533]` in
benchmark 3 and `+0.733` in benchmark 1. This is preregistered criterion 3,
failed twice on cost.

**C5 - CONTAMINATION: did sharing one request move the old question's
answers?** The absolute nouls share the request and must reproduce benchmark 3
**within ±0.02 per tool**. The design assumes each question is evaluated in
isolation against the same state; if the absolute answers shift when nine
comparative questions join the request, that assumption is false and **both
runs are confounded**, C1 included.

**Recorded, not predicted.** `stop_enough` AUC (0.845 [0.707, 0.966] at
benchmark 1) — its question is untouched, but a larger request could degrade
it, and the stop signal is arm B's one unambiguous win. Also the agreement
rate between the comparative top-1 and the shadow Choice's averaged pick:
benchmark 2 had the Choice agreeing with the absolute top-1 only 16 of 30
times, so they are not the same signal.

#### What would refute the hypothesis

- **C1 fails.** Comparative framing does not help either, and the remaining
  explanation is the probability compression measured in benchmark 1
  (ECE 0.663, Brier skill −6.10). The conclusion would be that *routing on a
  probability* is the thing to abandon, in favour of the Choice — which
  benchmark 2's shadow instrumentation shows is decisive and 30/30
  order-stable, though also state-blind, picking identically in 15 of 15
  first rounds.
- **C3 fails while C1 passes.** The framing manufactures an arbitrary
  ranking. Revert, and record that a tie was the more honest output.
- **C5 fails.** The two framings cannot share a request. Redesign as two
  requests and accept the latency, or alternate framings across runs and lose
  the pairing.

#### Declared validity threats

1. **The clauses and the question wording are mine, written knowing the
   scenario set.** The structural protection is unchanged from amendment 1:
   both halves of a minimal pair receive identical questions, so nothing in
   the wording can indicate which half is in front of the model. The
   comparative clause names no state field, number or threshold.
2. **C3 is intrinsic, which is the lesson of amendment 1.** Its P3 control
   depended on my judgement that a condition was unobservable in the state,
   and `volatility.vix` turned out to be leaky, which cost that run its
   mechanism claim. C3 instead scores against the scenarios' declared labels,
   so it does not depend on my judgement at all.
3. **A comparative noul is still a probability.** If the model's compression
   is unconditional, C1 may fail for reasons that have nothing to do with
   framing. C2 is the direct measure of that, and its failure alongside C1
   points at compression rather than at the question.

#### Implementation note, 2026-10-07 — change points the amendment missed

Written after implementing and before the first call. The amendment listed
three change points; four more were needed, and two of them would have
silently invalidated predictions.

1. **`eval/baseline_rules.py` and `eval/mock_jev.py`** synthesise answers by
   question-identifier prefix, so every mock arm had to answer the new
   question or receive an empty routing map and stop immediately. They return
   **the same number for both framings**, which is what keeps them controls.
   The first attempt scored each framing with a separate call, and the
   `random` arm's coverage moved from the preregistered **0.21 to 0.43** —
   its score is a draw from a seeded generator, so asking twice both consumed
   extra draws and routed the run on values other than the ones recorded.
   Scoring once per tool and reusing restored all four mock arms to their
   preregistered baselines exactly.
2. **`eval/harness.py` `calibration_items`** read `parsed["usefulness"]` for
   nDCG, the pivotal score and the calibration items. Left alone it would
   have scored the question the policy no longer consults, which would have
   made **C3 measure the wrong map** — and C3 is the prediction that licenses
   C1. It now reads whichever map the run routed on.
3. **`replay.py`** re-decided from `parsed["usefulness"]` and would have
   reported divergence against its own reading on every new trace.
4. **`tests/unit/test_agent_jev.py`** asserted the request carries
   `3 + 3 + 2` questions for three candidates. Now `3 + 3 + 3 + 2`.

Traces written before this amendment carry no `routing` key, and every reader
falls back to `usefulness` when it is absent. Verified: benchmark 2 and 3
re-score to their published mean pair gaps of **−0.030** and **+0.023**, and
the four mock arms reproduce the preregistered budgeted table exactly
(`rules` 0.57/0.20/0.66/4.27/2.00, `cheapest` 0.57/0.14/0.47/5.87/1.00,
`random` 0.21/0.06/0.46/4.33/1.87, `oracle` 1.00/0.57/0.96/1.73/1.47).
`bench --validate` still separates oracle from random.

The scoring script is `scripts/bench04_predictions.py`, written before the
first call. Run against benchmark 3 it reproduces that run's numbers and
returns C1 FAIL, C2 FAIL, C3 HOLDS, C4 FAIL, C5 clean — the pre-treatment
reading, which is what calibrates the thresholds against real data rather
than invented ones.

### 2026-10-08 — amendment 3: gate on the absolute map, rank on the comparative one

**Reason.** Benchmark 4 produced this project's best ranking quality (nDCG
0.76, beating the rule tree at significance), its best evidence-sensitivity
(mean pair gap +0.115, four of six pairs strongly positive), its lowest cost
(half the rule tree's tool calls) and zero forbidden analyses — and halved the
coverage those rankings should have delivered. Four of five predictions
failed, all for one reason.

| | run 1 | run 2 | threshold it meets |
|---|---|---|---|
| comparative top score, median | 0.41 | 0.42 | — |
| comparative top score, max | 0.68 | 0.67 | `act_threshold` 0.65 |
| rounds reaching `act_clear` | 2/33 | 2/33 | — |
| rounds halting on `stop_no_useful_tool` | 14/33 | 13/33 | `consider_threshold` 0.40 |

The comparative probabilities sit near 0.42 because *"this is the best of
nine"* is a far weaker claim to assert than *"this would help"*, which sat
near 0.74. Holding the thresholds fixed was correct for isolating one
variable, and this is the bill: `act_clear` is effectively unreachable and
about forty percent of rounds halt before the pivotal analysis runs.

**But the fix is not a threshold tweak, because there is a category error
underneath the arithmetic.** The `consider` floor and
`stop_no_useful_tool` exist to answer *is anything here worth running*. The
comparative question cannot answer that; it answers only *which one wins*. A
low "best of field" score means the model is unsure which analysis is best,
not that none is worth running — and thirteen spurious halts are that
confusion made operational.

The absolute question does answer the *whether*, it is already asked in the
same request, and it is decisive about it. Measured across both runs:

| | run 1 | run 2 |
|---|---|---|
| absolute top score, median | 0.75 | 0.74 |
| absolute top score, minimum | 0.66 | 0.67 |
| rounds where it falls below the 0.40 floor | **0/33** | **0/33** |

**The change.** Each map is read for the question it can answer:

* **Rank and act** on the comparative map. `act_clear` when its top score is
  **≥ 0.50** — more likely than not to be the best of the field — and the
  top-two margin is ≥ `margin_min`, which stays at 0.10.
* **Gate** on the absolute map. The `consider` floor and
  `stop_no_useful_tool` read it at `consider_threshold`, unchanged at 0.40.
* Stopping on sufficiency, the conflict veto, `min_tools_before_stop` and
  `max_corun` are untouched.

0.50 is not fitted. It is the one semantically privileged point on a
"probability this is the best one" scale: the point at which a candidate is
more likely than not to be the right choice. `margin_min` and
`consider_threshold` keep the values they have had since benchmark 1.

**Change points.** `policy.py` `decide` takes the ranking map and the gate map
separately; `config.py` gains `rank_act_threshold = 0.50`; `loop.py` passes
both maps and selects which act threshold applies. **Unchanged:** the state,
`summarize_frame`, every tool description, both question templates, the
scenarios, and every other policy threshold.

**The subtlety that could invalidate the controls.** The mock arms answer both
questions with the same number, because they have one scoring function and no
comparative judgement to make. Their scores are on the *absolute* scale, so
applying a 0.50 act threshold to them would make `act_clear` fire far more
often and move all four preregistered baselines. The act threshold is
therefore a property of the question answered, not of the policy: an arm whose
ranking map came from the comparative question is read at 0.50, and an arm
routing on the absolute map keeps 0.65. **The mock arms must reproduce the
preregistered budgeted table exactly, and that is a release gate, not a
prediction.**

**Cost.** Two replicates, because benchmark 4's two runs on identical code
gave coverage 0.43 and 0.57 and put nDCG significance on opposite sides of the
line. About 27 calls each if behaviour resembles benchmark 4, more if
`act_clear` runs one tool per round and more rounds are needed to spend the
four-call budget. **54 to 120 calls.**

#### Predictions, recorded before the first call

**E1 - DOES COVERAGE RECOVER?** (primary) Mean `required_coverage` **≥ 0.57**,
the rule tree's level, with the paired interval against `rules` not lying
wholly below zero. Benchmark 4 gave 0.43 and 0.57.

**E2 - DOES THE RIGHT ANALYSIS NOW RUN?** Pivotal reach **≥ 5/7**. Benchmark
4 gave 2/7 and 3/7, and benchmark 3 gave 4/7. Asking for 5 is asking for an
advance on everything measured so far, and it is the point of the change: the
rankings already identify the right analysis, with pair gaps of +0.14 to
+0.23 on four pairs, and only the gate stopped it running.

**E3 - IS THE COST WIN KEPT?** The paired interval on tool calls against
`rules` has an **upper bound at or below zero**. Benchmark 4 gave
−2.000 [−2.333, −1.667] and −1.933 [−2.267, −1.600]. This is the prediction
most likely to fail, and the one that matters most: if coverage can only be
bought back by running as many analyses as the rule tree, then benchmark 4's
cheapness was early stopping rather than better choosing, and the comparative
question's apparent cost win was an artefact of the broken gate.

**E4 - IS THE RANKING QUALITY KEPT?** nDCG **≥ 0.74**, the lower of benchmark
4's two runs. A gate change should not touch the ranking; if nDCG falls, the
two maps are interacting in a way this design does not model.

**E5 - DOES THE STOP SIGNAL COME BACK?** `stop_enough` AUC interval entirely
above 0.5, on **at least 8 positive labels**. Benchmark 1 measured 0.845
[0.707, 0.966]; benchmark 4 measured 0.750 [0.583, 0.906] and 0.689
[0.461, 0.900], the second crossing 0.5. That drop is confounded — the label
is "every expected analysis had already run", which was true in only 3 of 33
rounds once the agent stopped early — so this is a re-measurement under
recovered coverage, not a test of the new gate. Preregistered criterion 4
rests on it.

#### Implementation verification, not predictions

Read off benchmark 4's distributions, so these confirm the change does what
the arithmetic says and are **not** evidence for it:

* `act_clear` fires in roughly 10 to 16 of 33 rounds (12 and 13 rounds had a
  comparative top score ≥ 0.50).
* `stop_no_useful_tool` fires **zero** times (the absolute top never fell
  below 0.40 in 66 rounds).
* All four mock arms reproduce the preregistered budgeted table exactly.

#### Pre-run verification, 2026-10-08 (recorded before the first call)

Amendment 3's implementation was checked by re-deciding benchmark 4's
*recorded* answers under the new policy, which costs nothing. Both verification
items hit:

| band | run 1 was | run 1 now | run 2 was | run 2 now |
|---|---|---|---|---|
| `act_clear` | 2 | **11** | 2 | **12** |
| `act_tied` | 0 | 1 | 0 | 1 |
| `consider` | 14 | 5 | 17 | 7 |
| `indecisive` | 3 | **16** | 1 | **13** |
| `stop_no_useful_tool` | 14 | **0** | 13 | **0** |

`act_clear` lands in the predicted 10-16 band and `stop_no_useful_tool` is
eliminated, as the absolute map never falling below 0.40 implies.

**A risk this exposes, stated before the run rather than after it.**
`indecisive` rises to 13-16 rounds, because a round can clear the gate while
the top two comparative scores sit closer than `margin_min`. That band runs
the cheapest viable candidate and increments a streak, and
`indecision_limit = 2` turns two consecutive indecisive rounds into
`stop_repeated_indecision`. So coverage may still be capped, by a different
branch than the one amendment 3 fixes. The replay above cannot show this,
because it re-decides each round from a zero streak.

**No threshold is being changed in response.** Raising `indecision_limit`
after seeing this would be fitting the policy to the data, which is what this
file exists to prevent. If E1 fails with `stop_repeated_indecision` as the
dominant exit, that is the finding, and the streak limit becomes the subject
of amendment 4 with its own prediction.

#### What would refute the hypothesis

- **E1 fails.** The gate was not the binding constraint, and something else
  suppresses coverage. The next place to look is `max_corun` and the
  four-call budget rather than the questions.
- **E3 fails while E1 passes.** Coverage was bought with tool calls, so the
  comparative question's cost advantage was the broken gate stopping early
  and not better selection. The honest conclusion would be that benchmark 4
  overstated the win, and criterion 3's first pass should be withdrawn.
- **E2 fails while E1 passes.** It runs more analyses without running the
  right ones, so the pair gaps were not actionable and the ranking quality
  was flattering the arm.
- **E4 fails.** The split has side effects this design did not anticipate.

#### Declared validity threats

1. **The 0.50 threshold was chosen after seeing two runs' score
   distributions.** I knew before fixing it that it would fire in about a
   third of rounds. Three things constrain the damage: 0.50 is the only
   semantically privileged point on this scale rather than a value picked to
   maximise anything; the other two thresholds are unchanged from benchmark
   1; and the substantive predictions are on downstream outcomes — coverage,
   pivotal reach, cost, nDCG, the stop signal — that the threshold does not
   set directly. The `act_clear` fraction, which it *does* set, is listed as
   implementation verification rather than evidence.
2. **Two things change at once in a sense.** The gate moves to a different
   map *and* the act threshold moves. They cannot be separated by this run,
   so a failure cannot be attributed to one of them. I am accepting that
   because the category error makes the map split correct regardless of
   outcome: reading "which one wins" as "is anything worth running" is wrong
   whatever the benchmark says.
3. **Benchmark 3's traces are gone**, overwritten by benchmark 4's second
   run, so its figures can no longer be re-derived. The comparisons above
   against benchmark 3 come from [BENCHMARK_03.md](BENCHMARK_03.md) and from
   baselines hardcoded in `scripts/bench03_predictions.py`. `run_benchmark`
   now refuses to write into a directory already holding traces.

### 2026-10-08 — amendment 4: the margin test does not apply to a comparative ranking

**Benchmark 5's result first, since this amendment is a response to it.** Two
replicates, amendment 3's policy, no code changed between them.

| | run a | run b | `rules` |
|---|---|---|---|
| `required_coverage` | 0.679 | 0.536 | 0.571 |
| paired vs `rules` | +0.107 [−0.321, +0.500] | −0.036 [−0.536, +0.429] | — |
| pivotal reach | 5/7 | 4/7 | — |
| nDCG | 0.796 | 0.767 | 0.657 |
| paired vs `rules` | **+0.139 [+0.036, +0.282]** | **+0.109 [+0.005, +0.262]** | — |
| `tools_run` | 3.87 | 4.07 | 4.27 |
| paired `tool_calls` | −0.267 [−1.067, +0.600] | −0.067 [−0.867, +0.800] | — |
| `forbidden_hits` | 0.00 | 0.00 | 0.00 |
| mean pair gap | +0.117 | +0.122 | — |

Verdicts: **E1** pass then fail. **E2** pass then fail. **E3** fail both.
**E4** pass both. **E5** fail both, on 4 positive labels against the 8 it
required. The four mock arms reproduced the budgeted table exactly in both
runs, so the release gate held.

**Amendment 3 therefore carried one of its five predictions.** The gate fix
did eliminate `stop_no_useful_tool` exactly as predicted — 14 and 13 halts
became 0 — and it did not recover coverage reliably. E3's refutation clause
applies as written: benchmark 4's cost win was the broken gate stopping
early, `tools_run` went 2.33 to 3.87/4.07 once the gate was fixed, and the
−1.933 claim is withdrawn. Preregistered criterion 3 is now a draw rather
than a pass, since coverage is indistinguishable from `rules` in both runs.

The surviving result is the ranking. nDCG beat the hand-built decision tree
at significance in both replicates, and the pair gap held at +0.117/+0.122.

**The two replicates are not noisy; they differ by one scenario.** Every
scenario exited for the same reason after the same number of tool calls in
both runs, with one exception: `extended_run` went from coverage 1.00 on 4
calls to 0.00 on 7. One scenario of the seven that carry required analyses is
worth 0.143 of mean coverage, and 0.679 − 0.536 = 0.143. So E1's pass/fail
turned on a single scenario, and **E1 as specified cannot resolve 0.54 from
0.68.** That is a limitation of the metric's power, recorded here rather than
used to reinterpret the result: by the bar as written, E1 failed.

**Reason.** The pre-run note to amendment 3 committed in advance that "if E1
fails with `stop_repeated_indecision` as the dominant exit, that is the
finding, and the streak limit becomes the subject of amendment 4 with its own
prediction." That condition is met unambiguously, and identically in both
runs:

| band | run a | run b |
|---|---|---|
| `act_clear` | 11 | 10 |
| `act_tied` | 1 | 1 |
| `consider` | 6 | 7 |
| `indecisive` | **14** | **14** |
| `stop_repeated_indecision` | **8** | **8** |
| exits on `repeated_indecision` | **8/15** | **8/15** |
| exits on `tool_call_cap` | 7/15 | 7/15 |

The gate never fell below its floor in either run (minimum absolute top score
0.67 against `consider_threshold` 0.40), so every round that does not clear
the act band enters the grey band, and there the only remaining test is the
margin. **The margin test alone routes 22 of 40 rounds and ends 8 of the 15
runs**, at 2 or 3 of the 4 permitted tool calls.

**The margin test is not a well-defined test on this map, for two reasons.**

1. *The proposition already encodes exclusivity.* `margin_min` exists because
   two **absolute** scores can both be high and both be true — two analyses
   can each add information, which is what `act_tied` is for and why it
   co-runs them. Two comparative scores cannot both mean "this is the best of
   the field". Once `p1 >= 0.50` says a candidate is more likely than not the
   right choice, a gap to the runner-up adds no information the proposition
   did not already carry.
2. *The map is not normalised, so the gap has no fixed scale.* Measured over
   all 80 decision rounds, the comparative scores sum to 2.07 and 2.08
   median, not to 1.0, and the sum rises with the size of the field: 1.91 and
   1.92 at seven candidates, 2.49 and 2.50 at nine. This is structural rather
   than a model error. `jev/questions.py` records that each question is
   evaluated in isolation against the same state, so no call can see what the
   others scored and none can normalise. A fixed 0.10 gap therefore means
   something different at four candidates than at nine, and the median
   observed gap of 0.080 and 0.070 is what a spread-out unnormalised field
   looks like rather than evidence of indecision.

**Why one scenario could flip, and why removing the margin test should make
that rarer.** The model is not deterministic, but its jitter is small and
bounded. Across the 40 rounds the two runs share, every round's comparative
answers differ, 213 of 316 per-tool scores moved, and **the largest movement
is 0.05** — far smaller than the distance from the median score to any band
edge, which is why the band counts came out within one of each other. A score
sitting *near* an edge is the exception, and that is the mechanism behind
`extended_run`: 0.05 of jitter across a threshold, worth 0.143 of the primary
metric. Removing the margin test removes the band crossing that matters most,
because `act_clear` and `consider` select identically — both run the
top-ranked analysis — so jitter across `rank_act_threshold` changes the
recorded band and nothing the agent does. What remains as a route from jitter
to outcome is a flip in the rank *order* (plausible, since the median top-two
gap of 0.07–0.08 is close to the 0.05 jitter) and the sufficiency threshold,
which is a different question on a different scale. Two replicates are still
being paid for, because order flips remain live.

**The change.** `config.py` gains `rank_margin_min = 0.0`, applied only when
routing on the comparative map, exactly as `rank_act_threshold` is applied
and for the same reason: the threshold is a property of the question
answered, not of the policy. `margin_min` stays at 0.10 for any arm routing
on the absolute map, which is every mock arm, so the baselines are untouched
by construction. With the test trivially satisfied, `act_tied` becomes
`act_clear`, and `indecisive` and `stop_repeated_indecision` become
`consider`.

**`indecision_limit` stays at 2.** The pre-run note named the streak limit as
amendment 4's subject, and this amendment deviates from that letter
deliberately. Raising the limit would be choosing a number because the data
asked for it, which the same note forbids. Removing a test that is not
defined on the scale it is applied to is a different kind of change, and it
reaches the same band from upstream. If this amendment fails, the streak
limit is still available as a separate question, with the limit still at its
original value.

**Change points.** `policy.py`: `decide` and `_select` take `margin_min`,
defaulting to `config.margin_min`, replacing its five use sites inside
`_select`. `config.py`: `rank_margin_min = 0.0`, added to the [0, 1]
validation loop. `loop.py` and `replay.py`: pass
`config.policy.rank_margin_min` when and only when routing is comparative.
**Unchanged:** the state, every tool description, both question templates,
the scenarios, `indecision_limit`, `margin_min`, `act_threshold`,
`rank_act_threshold`, `consider_threshold`, `max_corun`, and the budget.

**A second effect of the same change, stated because it is a confound.**
`indecisive` ran *the cheapest viable* candidate; `consider` runs *the
top-ranked* one. So this amendment does not only let 8 runs continue — it
changes which analysis runs in 14 of 40 rounds. That is the intended
mechanism, since nDCG 0.77 to 0.80 says the ranking is good, but a coverage
gain cannot be attributed to the extra rounds alone.

#### Implementation verification, not predictions

These are arithmetic on the recorded answers, not evidence. Removing the
margin test also removes the only path-dependent band — `indecisive`
increments a streak, `consider` resets it — so unlike amendment 3's replay,
which had to re-decide each round from a zero streak and consequently
understated `indecisive`, these figures are exact rather than estimated:

* `act_clear` **12** (run a) and **11** (run b); `act_tied` **0**.
* `consider` **28** and **29**.
* `indecisive` **0** and `stop_repeated_indecision` **0**, in both.
* No run exits on `repeated_indecision`.
* All four mock arms reproduce the preregistered budgeted table exactly
  (`rules` 0.57/0.20/0.66/4.27/2.00, `cheapest` 0.57/0.14/0.47/5.87/1.00,
  `random` 0.21/0.06/0.46/4.33/1.87, `oracle` 1.00/0.57/0.96/1.73/1.47).
  **Release gate, not a prediction.**

#### Predictions, recorded before the first call

**F1 — DOES COVERAGE CLEAR THE RULE TREE?** (primary) Mean
`required_coverage` **at or above 0.68 in both replicates** — the better of
benchmark 5's two runs, asking the weaker replicate to reach the stronger's
level, and above `rules`' 0.571 in both. Benchmark 5 gave 0.679 and 0.536.

**F1a — the named case.** `volatility_spike` reaches coverage **1.00 in both
replicates**. It is the cleanest instance of the mechanism: it currently
scores 0.00, it stopped on `repeated_indecision` at 3 of 4 permitted calls in
both runs, and its pair is the second strongest in the set at +0.17. If the
margin test is what kept its pivotal analysis from running, this scenario is
where that shows. `lagging_benchmark` is deliberately *not* named — the
`relative_strength` pair gap is −0.02, the one pair that never separated, so
its ranking is not trusted to deliver even with the rounds available.

**F2 — DOES THE RIGHT ANALYSIS RUN?** Pivotal reach **at or above 6/7 in
both**. Benchmark 5 gave 5/7 and 4/7; benchmark 4 gave 2/7 and 3/7.

**F3 — IS THE COST INCREASE BOUNDED?** Mean `tools_run` **at or below 5.87**,
which is `cheapest`'s level. **This amendment predicts the agent will get
more expensive and declares in advance what it will pay.** Eight runs that
stopped at 2 or 3 calls will now continue to the cap, the cap is checked
between rounds so overshoot is routine, and `tools_run` should rise from
about 4.0 toward 5. The paired `tool_calls` interval against `rules` is
expected to lie wholly above zero, and that is **not** a failure of this
amendment, since E3 is already withdrawn. What would be a failure is the
agent costing more than the arm that simply runs everything cheapest-first,
because then the margin test was load-bearing for cost even while being
meaningless on its scale.

**F4 — IS THE RANKING QUALITY KEPT?** nDCG **at or above 0.767 in both**, the
lower of benchmark 5's two runs, with the paired interval against `rules`
still excluding zero in at least one replicate. A band change should not
touch the ranking; if it does, the two maps interact through the selection in
a way this design does not model.

**F5 — DOES THE STOP SIGNAL BECOME MEASURABLE?** **At least 8 positive
labels**, with the `stop_enough` AUC interval entirely above 0.5. Stated
plainly: this has now failed on power three times — 3 positives in benchmark
4, 4 and 4 in benchmark 5 — because the label is "every expected analysis had
already run" and too few analyses run. It is a precondition for measuring
preregistered criterion 4 at all rather than a test of this amendment, and it
is the one prediction here that more coverage should fix as a side effect.

#### What would refute the hypothesis

- **F1 fails with `tool_call_cap` the dominant exit.** The budget and not the
  policy is binding, which is the conclusion amendment 3's own E1 clause
  already pointed at. The next amendment would be on `max_tool_calls` and
  `max_corun`, and the question templates would be settled.
- **F1 fails while every verification item hits exactly.** The extra rounds
  run the wrong analysis. nDCG would then be measuring a good *ordering*
  whose top-1 is wrong, which is a sharper and more interesting failure than
  a threshold problem, and it would point at co-running the top two rather
  than at any threshold.
- **F3 fails.** The margin test was doing real work for cost regardless of
  its semantics, and the honest position would be that an ill-defined test
  was load-bearing and needs replacing rather than deleting.
- **F4 fails.** Selection and ranking are coupled through the state: running
  the top-ranked analysis instead of the cheapest viable one changes what is
  measured, which changes the next round's ranking.

**Cost.** Two replicates, because benchmark 5 showed a single scenario moving
the primary metric by 0.143 and one replicate cannot separate that from a
real effect. Benchmark 5 used 40 decision rounds per run; eight runs
continuing further should raise that to roughly 50 to 55. **About 100 to 120
calls.**

#### Declared validity threats

1. **The band counts above were computed from benchmark 5's recorded answers
   before this amendment was written.** The change is argued from the
   proposition's semantics and from the map's non-normalisation, both of
   which would hold had the bands come out differently, and the predictions
   are on downstream outcomes the band counts do not set. But the ordering is
   what it is, and it is the same footing as amendment 3, which was also
   drafted from a replay and declared it.
2. **`rank_margin_min = 0.0` disables a test rather than retuning it.** If
   the comparative map later becomes normalised — by asking one question over
   the whole field, or by normalising in Python — a margin test becomes
   meaningful again, and this setting would have to be revisited rather than
   inherited.
3. **This amendment does not address the design-fit question it came from.**
   The comparative proposition is only decidable jointly across candidates
   while the interface answers each in isolation; that mismatch is why the map
   is unnormalised, and removing the margin test accommodates it instead of
   resolving it. The alternative — ranking by normalising the absolute map in
   Python, where every other number in this repo is computed — is a different
   experiment, and it would discard a measured and twice-replicated nDCG
   advantage, so it is deferred rather than dismissed.
