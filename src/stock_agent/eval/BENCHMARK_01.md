# Benchmark 1 — arm B across the scenario set, budgeted regime

2026-10-06. Fifteen scenarios, five arms, 75 runs, all answers from the live
decision endpoint for arm B. Criteria and metrics were fixed in
[PREREGISTERED.md](PREREGISTERED.md) before any live call and are not
restated here in softer terms.

**Verdict: three of five criteria passed. The hypothesis survives but is not
confirmed.** The routing beats both floors decisively and its stop signal
carries real information, but it did not beat an honest decision tree, it
costs significantly more tool calls, and the one metric that tests whether
its scores respond to evidence came out flat.

## Results

Means over the fifteen scenarios; coverage, precision and nDCG average over
the seven that declare expectations, since they are undefined elsewhere.

| arm | cov | prec | nDCG | forbidden | pivotal reached | tools | calls |
|---|---|---|---|---|---|---|---|
| `oracle` | 1.00 | 0.57 | 0.96 | 0.00 | **7/7** | 1.73 | 1.47 |
| **`jev`** | **0.68** | **0.23** | **0.65** | **0.33** | **5/7** | **5.00** | **2.00** |
| `rules` | 0.57 | 0.20 | 0.66 | 0.00 | 3/7 | 4.27 | 2.00 |
| `cheapest` | 0.57 | 0.14 | 0.47 | 0.00 | 3/7 | 5.87 | 1.00 |
| `random` | 0.21 | 0.06 | 0.46 | 0.33 | 1/7 | 4.33 | 1.87 |

Arm B's mean decision latency was 0.41 s per round. No run touched the
network beyond the price provider: `macro.snapshot` and `events.insider` are
withheld on synthetic data, so the benchmark cost nothing but decision calls.

## The five criteria

### 1. Beat random on coverage — **PASSED**

`+0.464` **[+0.143, +0.857]**, and on reaching the pivotal analysis
`+0.571` **[+0.143, +0.857]**, both excluding zero. The routing is routing.
This was the criterion whose failure would have killed the hypothesis
outright.

### 2. Beat cheapest-first on coverage or nDCG — **PASSED**

On nDCG, `+0.178` **[+0.079, +0.263]**. Coverage was `+0.107`
**[+0.000, +0.250]** — the lower bound sits exactly on zero, so coverage
alone would not have carried it, and nDCG is what the criterion rests on.

It also did this with **one fewer tool call** than cheapest-first
(`-1.000 [-1.000, -1.000]`), so the gain is not bought with extra work. The
routing adds something that ordering by cost does not.

### 3. Match or beat the rule-based tree at no greater cost — **FAILED on cost**

Coverage `+0.107` **[-0.321, +0.500]** — indistinguishable, so a match.
Reaching the pivotal analysis `+0.286` **[-0.286, +0.714]** — also
indistinguishable, despite 5/7 against 3/7, because seven scenarios is a
small sample for an all-or-nothing outcome.

But tool calls `+0.733` **[+0.467, +0.933]**: significantly **more** work for
the same coverage. The criterion required "no more than `rules`' tool calls",
so this fails as written.

### 4. The stop signal must discriminate — **PASSED, and this is the clearest win**

| | n | AUC | 95% interval | discriminates |
|---|---|---|---|---|
| `jev` sufficiency | 30 | **0.845** | [0.707, 0.966] | **yes** |
| `rules` sufficiency | 30 | 0.500 | [0.500, 0.500] | no |

Arm B's `stop_enough` tells the difference between a state where the expected
analyses have already run and one where they have not. The rule-based arm's
stop signal has an AUC of exactly 0.500 — no information whatsoever. This is
the one place arm B does something the baseline cannot do at all, and it
means `stop_threshold = 0.70` is defensible rather than decorative.

### 5. Scores must track the planted evidence — **WITHDRAWN**

> **Superseded by [BENCHMARK_02.md](BENCHMARK_02.md).** This criterion was
> recorded as a failure, and that reading does not hold. The planted feature
> was not visible in the state at the moment the pivotal analysis was scored —
> a sixfold volume spike over five bars leaves no trace in a sixty-bar median,
> and no amount of reading the state could reveal an RSI divergence before RSI
> had been computed. The flat result below is what a correct answer looks like
> when the evidence is absent. Benchmark 2 put the evidence in the state and
> the scores moved sharply, so the criterion was measuring the state's content,
> not the model's perception. The original numbers are kept below unaltered.

| arm | pairs | preferred | ties | mean gap |
|---|---|---|---|---|
| `oracle` | 6 | 6 | 0 | **+0.850** |
| `random` | 6 | 4 | 0 | +0.039 |
| **`jev`** | 6 | **1** | 3 | **+0.000** |
| `rules` | 6 | 0 | 6 | +0.000 |
| `cheapest` | 6 | 0 | 6 | +0.000 |

This is the strictest test the scenario set supports, and the one a lucky
prior cannot fake: within a minimal pair, does the arm score the pivotal
analysis higher on the half where the feature is actually planted?

**Arm B does not.** One of six pairs preferred, three exact ties, mean gap
zero — indistinguishable from the two deterministic baselines, whose scores
are known not to depend on the data at all.

So arm B's advantage over the floors comes from *which analyses it
generally favours*, not from reading the state in front of it. It has a
better prior, not better perception. That is a real and useful thing — a
better prior beat cost-ordering and random choice decisively — but it is not
the thing the hypothesis was most interesting for.

## Calibration

| | n | base rate | AUC | 95% interval | Brier skill | ECE |
|---|---|---|---|---|---|---|
| `jev` usefulness | 232 | 0.08 | 0.734 | [0.637, 0.826] | **−6.10** | **0.663** |
| `rules` usefulness | 232 | 0.08 | 0.719 | [0.638, 0.798] | −3.36 | 0.419 |

Arm B discriminates marginally better than the rule tree and is **far worse
calibrated** — roughly twice the expected calibration error and a much worse
Brier skill. Its probabilities cluster high regardless of the base rate,
which is exactly the set-dependent miscalibration the design anticipated.

This vindicates the decision to actuate only on the ranking and on fixed band
crossings. Anything that read these numbers as probabilities would be badly
misled; the policy never does.

## Where the two routers fail differently

They reached 5/7 and 3/7 pivotal analyses, but not the same ones:

| scenario | `jev` | `rules` |
|---|---|---|
| `divergence_present` | **yes** | no |
| `lagging_benchmark` | **yes** | no |
| `several_features` | **yes** | no |
| `momentum_oversold` | yes | yes |
| `volatility_spike` | yes | yes |
| `extended_run` | no | **yes** |
| `volume_surge` | no | no |

The rule tree finds whatever sits near the top of its fixed priority list and
runs out of budget before the rest. Arm B found the three that need more than
one step — `divergence_present` requires momentum first, and
`several_features` requires four analyses — and missed the single cheap
analysis the tree happens to run early.

That difference is not statistically significant at n=7 and should not be
read as a finding. It is a hypothesis worth a larger scenario set: that the
value of routing shows up in dependency chains rather than in single picks.

## Against it

- **`forbidden_hits` 0.33**, matching random and against 0.00 for both
  deterministic arms. Arm B ran the nine-second segmentation in a third of
  the scenarios that declare it wasteful. The rule tree never did, because it
  is explicitly told not to.
- **Significantly more tool calls than the tree** for statistically
  indistinguishable coverage.
- **Seven scenarios with expectations** is a thin sample for an
  all-or-nothing outcome; most intervals here are wide, and the ones that
  exclude zero do so because the floors are far away, not because the
  estimates are tight.

## What would change the verdict

1. **A larger scenario set.** Seven is too few to separate arm B from the
   tree. The pairs are cheap to add now that the planters self-verify.
2. **The `free` regime**, still unrun. It measures precision, redundancy and
   cost without a budget, which is where "more tool calls" either becomes a
   real cost or stops mattering.
3. **Scenarios whose pivotal analysis is not guessable from a prior.** Every
   pair here has a feature that a sensible prior might favour anyway. A pair
   where the right answer *inverts* between halves would separate perception
   from prior, and criterion 5 is currently the only thing testing that.

## Honest summary

> **Amended after [BENCHMARK_02.md](BENCHMARK_02.md).** The second sentence
> below was wrong. Arm B does read the state; it had nothing to read. See
> benchmark 2 for the evidence and for why criterion 5 was withdrawn.

Arm B is better than both floors and no better than a decision tree someone
spent an afternoon writing — while costing more tool calls and an API bill.
Its one unambiguous advantage is knowing when to stop, which the tree cannot
do at all.

~~On this evidence the agent is a good prior with a working stop signal, not a
router that reads the state.~~ Whether it is worth the dependency is a
judgement about how much the stop signal matters, and it is not a judgement
this benchmark can make.
