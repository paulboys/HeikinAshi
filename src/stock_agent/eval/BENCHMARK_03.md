# Benchmark 3 — do the tool descriptions move the scores?

2026-10-07. Fifteen scenarios, budgeted regime, arm B live; the four mock arms
re-run alongside as controls. Predictions were fixed in
[PREREGISTERED.md](PREREGISTERED.md) amendment 1 before the first call and are
not restated here in softer terms.

**The change under test:** one sentence added to each tool's
`jev_description` naming the condition under which that analysis is most
informative, in the register `signal.mcglone` already used. Nothing else. The
first-round `state_text` is SHA-256 identical to benchmark 2 across all
fifteen scenarios, and every mock arm reproduced its preregistered baseline
exactly.

**Verdict: P1 passed, P2 passed, P4 held, and P3 — the control that licenses
reading P1 as a mechanism — was violated.** The scores moved, they moved in
the right direction, and the pre-registered reason for not believing the
explanation fired at the same time.

## Results against the predictions

### P1 — observable-condition tools widen to ≥ 0.10 — **PASSED**

First-round score range across the fifteen scenarios:

| tool | bench 2 | bench 3 | group |
|---|---|---|---|
| `momentum.rsi_stochastic` | 0.02 | **0.19** | P1 |
| `signal.mcglone` | 0.15 | 0.17 | P4 reference, untouched |
| `volume.surge` | 0.18 | 0.12 | redundancy-driven |
| `market_regime.price` | 0.06 | **0.10** | P1 |
| `trend.heiken_runs` | 0.03 | **0.10** | P1 |
| `volatility.realised` | 0.03 | **0.10** | P1 |
| `volatility.vix` | 0.02 | 0.06 | **P3 control** |
| `pattern.rsi_divergence` | 0.02 | 0.05 | P5 asymmetry |
| `relative_strength.beta_regime` | 0.02 | 0.03 | **P3 control** |

Three of the four P1 tools land exactly on the 0.10 bar and clear it by
nothing. They first read as failures because a range is a subtraction and
`0.71 - 0.61` is `0.09999999999999998`; `policy.py` carries `_EPS` against
precisely this and the scoring script did not. The script was fixed, not the
threshold.

### P2 — volatility and momentum pair gaps reach +0.05 — **PASSED**

Harness `pivotal_score`, the same metric benchmark 2 reported:

| pair | bench 2 | bench 3 |
|---|---|---|
| momentum | +0.010 | **+0.150** |
| volatility | +0.010 | **+0.100** |
| relative strength | −0.010 | +0.010 |
| divergence | −0.010 | +0.000 |
| trend | −0.010 | −0.010 |
| volume | −0.170 | −0.110 |
| **mean** | **−0.030** | **+0.023** |

This is criterion 5's question asked again with the state untouched, and the
mean gap is positive for the first time. It is also **still below the random
arm's +0.039**, against `rules` and `cheapest` at +0.000 and the oracle at
+0.850. Positive is not the same as good.

`trend` is the instructive failure. Its score range widened to 0.10 like the
other P1 tools, yet its pair gap did not budge from −0.010. Widening across
scenarios is not the same as discriminating the planted feature, and `trend`
shows the two coming apart.

### P3 — unobservable-condition controls stay ≤ 0.05 — **VIOLATED**

`relative_strength.beta_regime` held at 0.03. `volatility.vix` went to 0.06.
The amendment is unambiguous about what that means:

> P3 fails (the unobservable-condition tools move too): the effect is an
> artefact of longer, hedged descriptions. P1 would then mean nothing.

So the mechanism claim does not stand on this run. What the data also shows,
and what cannot be used to rescue it, is a gradient: the strict control — the
one whose condition requires comparing against a benchmark index that appears
nowhere in the state — moved +0.01, while the P1 tools moved +0.04 to +0.17.
`volatility.vix` sits between them, and on re-reading it is a leaky control:
its clause asks whether "the whole market may be under strain", and a
twenty-eight percent drawdown is weak evidence about that. Treating it as
equivalent to the beta control was a design error in the amendment, made
before the data and discovered after it.

That is a hypothesis for a cleaner test, not a result. The honest statement is
that this run cannot separate condition-matching from a prompt artefact.

### P4 — `signal.mcglone` stable — **HELD**

Range 0.17 against 0.15, drawdown correlation −0.754 against −0.788. Its
description was byte-identical to benchmark 2's, confirmed against the
recorded request bodies. Some drift, not enough to swamp P1's +0.07 to +0.17.

### P5 — divergence asymmetry — **as declared**

`pattern.rsi_divergence` gap went −0.010 to +0.000. Its condition needs RSI,
which does not exist in the state until momentum has run. Declared in advance
as not a prediction.

## The result that matters more than the predictions

**The routing did not become more decisive.** Every score fell and spread —
the top candidate's median dropped 0.790 to 0.740 — but the gap between the
top two candidates in a round is **unchanged**:

| | bench 2 | bench 3 |
|---|---|---|
| median top1 − top2 margin | 0.030 | **0.030** |
| largest margin seen | 0.050 | 0.090 |
| rounds reaching `margin_min` = 0.10 | 0/30 | **0/27** |
| bands | 30 `act_tied` | 27 `act_tied` |

`act_clear` remains unreachable and every scoring round still co-runs two
tools. The descriptions widened the spread *across scenarios* without widening
it *between competitors inside a round*, and routing is decided only by the
latter. Criterion 3 still fails on cost: tool calls against `rules`
`+1.000 [+0.533, +1.533]`, worse than benchmark 1's `+0.733`.

Coverage rose 0.68 to 0.71, nDCG 0.65 to 0.67, forbidden hits fell 0.33 to
0.27, and three scenarios stopped a round early — all small, none with an
interval excluding zero against `rules`. Pivotal reach stayed 4/7.

## A harness defect this run exposed

The report put arm B at **14.73** mean decision calls against 2.00 in
benchmark 2. That number is wrong. `harness.py` read `getattr(decider,
"calls", 0)` — the client's cumulative counter — and a live `JevClient` is
built once in `cli.py` and shared across every scenario, so each row reported
the running total. Mock arms are rebuilt per scenario and were never affected,
which is what made the inflated figure look plausible.

The cumulative sums in scenario order are 2, 4, 6, 8, 10, 12, 14, 15, 17, 18,
19, 21, 23, 25, 27; their mean is 14.73 exactly. **The run cost 27 calls, not
221**, and arm B's true mean is **1.80** — fewer than benchmark 2's 2.00,
because three scenarios now stop a round earlier. Fixed by taking the
per-scenario delta. `tool_calls` was always computed from the run history and
is unaffected, so every cost comparison resting on it still stands.

## Standing conclusion

> **Traces lost.** This run's fifteen jev traces were overwritten on
> 2026-10-08 by benchmark 4's second run, invoked with the same
> `--trace-dir`. The figures below cannot be re-derived from traces; they
> survive here and in the baselines hardcoded in
> `scripts/bench03_predictions.py`. `run_benchmark` now refuses to write
> into a directory that already holds traces.
>
> **Superseded by [BENCHMARK_04.md](BENCHMARK_04.md)** on the question of
> what limits the routing: not the state, not the tool descriptions, but the
> truth condition of the question being asked.


Adding a usefulness condition to a tool's description moves its scores, by
a lot in two cases, and turns the criterion 5 metric positive for the first
time. Whether that is the model matching a named condition against the state,
or longer and more hedged prompt text loosening the scores generally, **this
run cannot say** — the control written to settle it was not clean enough.

What it does settle is narrower and unwelcome: the defect that keeps arm B
expensive is not in the state and not in the tool descriptions. Thirty rounds
in benchmark 2 and twenty-seven here, every one of them `act_tied`, with an
unchanged median margin of 0.030 against a 0.10 requirement. Nine independent
questions whose honest answers are nearly identical cannot produce a ranking,
and no amount of prompt text appears to change that. The next experiment is
the comparative question.
