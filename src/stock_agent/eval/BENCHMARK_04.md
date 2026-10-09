# Benchmark 4 — the comparative routing question, twice

2026-10-07 and 2026-10-08. Fifteen scenarios, budgeted regime, arm B live,
the four mock arms alongside as controls. **Run twice on identical code**,
which turned out to matter. Predictions were fixed in
[PREREGISTERED.md](PREREGISTERED.md) amendment 2 before the first call.

**The change under test:** routing moved off the absolute usefulness noul
("would this analysis add information") onto a comparative one ("is this the
best use of the next step"). Both are asked in every request; only the
comparative map routes. Nothing else changed — not the state, not the tool
descriptions, not the policy thresholds, not the scenarios.

**Verdict: the question works and the policy cannot act on it.** The ranking
is the best this project has measured and the cost is the lowest, but four of
five predictions failed, and they failed for one reason: the comparative
probabilities live on a different numeric scale than the thresholds that read
them.

## Results, both runs

| | run 1 | run 2 | `rules` |
|---|---|---|---|
| coverage | 0.43 | **0.57** | 0.57 |
| precision | 0.25 | **0.29** | 0.20 |
| nDCG | 0.74 | **0.76** | 0.66 |
| forbidden hits | 0.00 | 0.00 | 0.00 |
| tools run | 2.27 | 2.33 | 4.27 |
| decision calls | 2.20 | 2.20 | 2.00 |

Paired against `rules`, 95% bootstrap:

| metric | run 1 | run 2 |
|---|---|---|
| coverage | −0.143 [−0.571, +0.286] | +0.000 [−0.429, +0.429] |
| precision | +0.050 [−0.098, +0.179] | +0.086 [−0.040, +0.190] |
| nDCG | +0.087 [−0.014, +0.242] | **+0.106 [+0.008, +0.256]** |
| tool calls | **−2.000 [−2.333, −1.667]** | **−1.933 [−2.267, −1.600]** |

## Preregistered criterion 3 passes, for the first time

Criterion 3 required matching `rules` on coverage at no greater tool cost. It
failed on cost in benchmark 1 (`+0.733`) and again in benchmark 3 (`+1.000`).

In run 2 coverage is `+0.000 [−0.429, +0.429]` — a match — and tool calls are
`−1.933 [−2.267, −1.600]`, significantly **fewer**. Arm B now reaches the
rule tree's coverage using roughly half the analyses.

**And in run 2 nDCG beats `rules` with the interval excluding zero**,
`+0.106 [+0.008, +0.256]`. That is the first time any arm has beaten the
hand-built tree on a quality metric at significance. In run 1 the same
comparison was `+0.087 [−0.014, +0.242]` — the same direction, not
significant. One of the two runs carries it, which is worth stating plainly
rather than quoting only the better one.

## The predictions

**Prediction 1 — decisiveness — FAILED, half met.** The margin requirement
is now satisfied: median top-two gap 0.110 in run 2 and 0.090 in run 1,
against 0.030 across both earlier benchmarks and a 0.10 requirement. But the
confident branch fired **2 of 33 rounds** in both runs, against the half
required.

**Prediction 2 — coherence — FAILED, improved.** The top candidate's share of
the probability mass rose to 0.198 and 0.209, from 0.134, against a 0.111
indifference floor and a 0.30 requirement. The median probability sum fell
from 5.61 to about 2.17, so the answers are far closer to a partition than
before without being one.

**Prediction 3 — is the winner the right one — VIOLATED.** Two of its three
parts passed handsomely: nDCG 0.745 and 0.764 against 0.67 required, and mean
pair gap +0.122 and +0.115 against +0.023. The third failed: the decisive
analysis ran in **2 of 7** scenarios in run 1 and **3 of 7** in run 2,
against 4 required, down from 4 of 7 in benchmark 3.

This is the important failure, and it is not a ranking failure. Per-pair gaps
in run 2:

| pair | gap |
|---|---|
| momentum | +0.230 |
| volume | +0.210 |
| trend | +0.160 |
| volatility | +0.140 |
| divergence | −0.020 |
| relative strength | −0.030 |

Four of six pairs are now strongly positive, including `trend` and `volume`,
which never moved before. The model is identifying the right analysis and the
policy is stopping before it runs.

**Prediction 4 — cost — PASSED.** Covered above.

**Prediction 5 — contamination — one of nine violated.** The absolute nouls
share the request and reproduced benchmark 3 within ±0.02 for eight of nine
tools. `trend.heiken_runs` drifted 0.03. The two framings can therefore share
a request, with that one caveat recorded.

## Why the policy throttles a signal it is reading correctly

The band distribution is the whole story:

| | run 1 | run 2 |
|---|---|---|
| `consider` | 14 | 17 |
| `stop_no_useful_tool` | 14 | 13 |
| `act_clear` | 2 | 2 |
| `indecisive` | 3 | 1 |
| median `p_top1` | 0.41 | 0.42 |
| rounds with `p_top1` ≥ 0.65 | 2/33 | 2/33 |
| rounds with `p_top1` < 0.40 | 14/33 | 13/33 |

`act_threshold` is 0.65 and `consider_threshold` is 0.40. The comparative
probabilities sit around 0.42 with a maximum of 0.67, because *"this is the
best of nine"* is a far weaker claim to assert than *"this would help"*,
which sat near 0.74. So `act_clear` is effectively unreachable, and about
forty percent of rounds fall under the floor and halt.

Holding the thresholds fixed was the right call for isolating one variable,
and this is what it cost: the new signal is being read through bands
calibrated for the old one.

There is also a category error underneath the arithmetic. The `consider`
floor exists to answer *is anything worth running at all*. The comparative
question cannot answer that — it only answers *which one*. A low "best of
field" probability means the model is unsure which analysis wins, not that
none is worth running, and `stop_no_useful_tool` firing thirteen times is
that confusion made operational. The absolute map still answers the
*whether*, and it is already being asked in the same request.

## What degraded

**The stop signal.** `stop_enough` discrimination fell from benchmark 1's
AUC 0.845 [0.707, 0.966] to 0.750 [0.583, 0.906] in run 1 and 0.689
[0.461, 0.900] in run 2 — run 2's interval crosses 0.5, so it no longer
discriminates there. This is arm B's one unambiguous win and it is now in
question.

It is also confounded. The label is "every expected analysis had already run,
so stopping would have lost nothing", and with only 2.3 analyses running per
scenario that is true in just **3 of 33** rounds. The AUC rests on three
positives. Running fewer tools starves the label that scores stopping, so the
drop cannot be attributed to the new question on this evidence. It needs
re-measuring once coverage recovers.

## Benchmark 3's traces were destroyed

Run 2 was invoked with `--trace-dir runs/bench_03/budgeted`, overwriting the
fifteen jev traces from benchmark 3 with comparative-question traces. `runs/`
is not committed, so nothing could be recovered.

What survives: [BENCHMARK_03.md](BENCHMARK_03.md) and the baselines hardcoded
in `scripts/bench04_predictions.py`. What is lost: the ability to re-derive or
audit benchmark 3's figures. `bench_01` and `bench_02` are intact.

`run_benchmark` now refuses to write into a directory that already holds
traces unless `--overwrite-traces` is passed, and refuses before any arm runs,
so a repeat costs nothing.

## Standing conclusion

The comparative question is the right question. It produced the best ranking
quality (nDCG 0.76, significantly better than the rule tree), the best
evidence-sensitivity (mean pair gap +0.115 with four of six pairs strongly
positive), the lowest cost (half the rule tree's tool calls), and zero
forbidden analyses — all from one changed proposition, with the state and the
tool descriptions untouched.

It also halved coverage relative to what those rankings should have produced,
because the thresholds reading it were built for a different scale and for a
different question. Amendment 3 addresses the gate, not the question.

Two runs on identical code gave coverage 0.43 and 0.57 and nDCG significance
on one side of the line and not the other, so single-run differences of that
size in earlier benchmarks should not have been read as firmly as they were.
Replicates are cheap here — 27 calls — and from now on the headline numbers
should come from two.
