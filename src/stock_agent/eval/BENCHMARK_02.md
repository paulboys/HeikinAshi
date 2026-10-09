# Benchmark 2 — does a richer state make the routing read evidence?

2026-10-06, immediately after [BENCHMARK_01.md](BENCHMARK_01.md). Same fifteen
scenarios, same five arms, same budgeted regime, 30 live decision calls. The
only change is what the state contains.

**The question:** benchmark 1's criterion 5 came out flat — arm B scored the
pivotal analysis no higher on the half where the feature was planted. Was that
because the routing ignores the state, or because the feature was not *in* the
state?

**The answer: the feature was not in the state, the routing does read it, and
criterion 5 was measuring the wrong thing.**

## What was added

Before, the only thing the decision model knew about the data came from one
line: last close, median volume, a 20-bar range, a 63-bar return, bar count.
A planted sixfold volume spike over five bars left **no trace at all** in it,
because a 60-bar median absorbs five bars. The two halves of the volume pair
differed by `median volume 2,101,300` against `2,071,933`.

Six coarse hints were added to `summarize_frame`, rounded to one decimal so
they signal rather than settle: a five-bar return, how many of the last ten
closes were up, where the last close sits in its 20-bar range, drawdown from
the window high, recent realised movement against the window average, and
recent volume against the sixty bars before it. The state went from 804 to
1049 characters.

All six minimal pairs became distinguishable in the state. They were not
before.

## Result

| | thin state | rich state |
|---|---|---|
| **pair gap** | **+0.000** | **−0.030** |
| preferred / ties | 1 / 3 | **2 / 0** |
| coverage | 0.68 | 0.61 |
| pivotal reached | 5/7 | 4/7 |
| nDCG | 0.65 | 0.63 |
| forbidden hits | 0.33 | 0.40 |

The gap moved off zero. It moved **negative**, and the three exact ties
disappeared — the scores now respond to the state, which they demonstrably
did not before.

### Per pair, and where it comes from

| pair | thin: pres / abs / gap | rich: pres / abs / gap |
|---|---|---|
| trend | 0.76 / 0.77 / −0.01 | 0.73 / 0.74 / −0.01 |
| divergence | 0.76 / 0.76 / **+0.00** | 0.73 / 0.74 / −0.01 |
| **volume** | 0.74 / 0.74 / **+0.00** | **0.42 / 0.59 / −0.17** |
| volatility | 0.78 / 0.78 / **+0.00** | 0.78 / 0.77 / +0.01 |
| momentum | 0.81 / 0.82 / −0.01 | 0.80 / 0.79 / +0.01 |
| relative strength | 0.77 / 0.75 / +0.02 | 0.76 / 0.77 / −0.01 |

Almost all of it is one pair. Told *"last 5 bars traded 6.5x the volume of the
60 before them"*, arm B dropped its score for the volume analysis from **0.74
to 0.42** — and scored it 0.59 on the half where volume was ordinary at 1.1x.
A single added line moved one score by 0.32.

The other five pairs moved by ±0.01, because their hints do not duplicate what
their pivotal analysis produces. Only the volume hint was a near-exact
restatement of the volume tool's own output.

## Why this invalidates criterion 5

The usefulness question asks for the probability that running an analysis
*would add information*, and its `false` criterion reads, verbatim:

> "...would be redundant, irrelevant to the objective, or **would restate
> something the existing measurements already settle**."

Once the state contains the volume ratio, running the volume analysis to learn
the volume ratio restates something already settled. **Arm B gave the correct
answer to the question it was asked, and the benchmark scored it as a
failure.**

Criterion 5 equated "noticed the planted feature" with "wanted the analysis
more". Those are the same thing only for a feature the state does *not*
already quantify. For a feature it does, a router that notices should want the
analysis **less** — and that is what happened.

So the metric cannot distinguish "ignores the state" from "reads the state and
correctly judges the analysis redundant". It returned +0.000 in the first case
and −0.17 in the second, and neither number means what the criterion claimed.

**Criterion 5 is withdrawn as a test of evidence-reading.** What it did
establish, across both runs together, is sharper than what it was designed
for: arm B's scores are flat when the state is uninformative and move sharply
when it is, which is the behaviour of something reading the state.

## The design question this exposes

Not "does the routing work" but **where the line falls between a state hint
and a tool**.

A hint that fully duplicates a tool's output makes the tool redundant, and the
honest response is to remove the tool rather than to penalise a router for
declining it. `volume.surge` is now close to that: the state says 6.5x, and
the tool says ratio 6.52, classified "sharp surge". What the tool still adds
is the classification and the baseline comparison — thin value for a 0.02 s
analysis, but not nothing.

Three ways out, none yet tested:

1. **Coarsen the hint to a category** — "volume unusual" rather than "6.5x" —
   so the tool still contributes the figure. This is the one I would try, and
   it is the only one that would let a repaired criterion 5 come out positive.
2. **Drop `volume.surge`** and treat volume as answered at bootstrap. Honest,
   and shrinks the registry by one.
3. **Leave it.** Accept that the state answers volume and that the router is
   right to decline the tool, and stop measuring a pair whose pivotal analysis
   is redundant.

## What did not change

Coverage fell 0.68 to 0.61 and pivotal reach 5/7 to 4/7, but **this is not a
degradation**. The single difference is `divergence_present` flipping from
reached to missed, on a pivotal score that moved 0.76 to 0.73. Benchmark 1
measured top-two margins of 0.00–0.04 and answer jitter of ±0.008, so a
0.03 move at the top of the ranking is inside the noise. `volume_surge` was
missed in **both** runs.

Every comparison against the other arms is unchanged within its interval:
still decisively ahead of random, still ahead of cheapest-first on nDCG, still
indistinguishable from the rule tree on coverage while using significantly
more tool calls.

All 30 calls: `model_served` `jev-1.13.0`, `wrapper_key` `answers`, zero
errors, no key in any trace. Traces archived under `runs/bench_02/`.

## Standing conclusion

> **Qualified by [BENCHMARK_03.md](BENCHMARK_03.md).** "Arm B does read the
> state" is established below for *redundancy* — noticing that a measurement
> it already has makes an analysis moot. It is not established for
> *relevance*. Re-reading these traces showed that across the fifteen
> scenarios the state carries drawdowns from +0.0% to -28.6% and a realised
> volatility ratio from 0.5x to 2.3x, while `volatility.realised` scored
> 0.75-0.78 throughout: a 4.6-fold swing in the quantity that tool measures,
> answered with a 0.03 spread. The +-0.01 movements reported above for the
> five non-volume pairs are at the +-0.008 answer-jitter floor and are
> evidence of nothing either way. Benchmark 3 tested whether the tool
> descriptions, rather than the state, were the limiting factor.


Benchmark 1's summary — "a good prior with a working stop signal, not a router
that reads the state" — was **half wrong**, and the wrong half was mine. Arm B
does read the state. It could not act on evidence that was not there, and the
one metric testing for it was built so that reading the state correctly scored
as failing to.

What stands from benchmark 1: arm B beats both floors, matches the rule tree
at higher tool cost, and has a stop signal with AUC 0.845 where the tree's
carries no information at all. What falls: the claim that its scores do not
respond to the state.
