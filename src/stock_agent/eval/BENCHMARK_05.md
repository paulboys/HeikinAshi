# Benchmark 5 — the two-map policy, twice

2026-10-08. Fifteen scenarios, budgeted regime, arm B live, the four mock
arms alongside as controls. Run twice on identical code, as amendment 3
required. Predictions were fixed in [PREREGISTERED.md](PREREGISTERED.md)
amendment 3 before the first call, together with a pre-run note recording one
risk the change would expose.

**The change under test:** each of the two questions asked in every request
is now read for what it can answer. The comparative map *ranks* and drives
the act band at `rank_act_threshold` 0.50; the absolute map *gates* at
`consider_threshold` 0.40. Nothing else changed — not the state, not the tool
descriptions, not either question template, not the scenarios, not any other
threshold.

**Verdict: one of five predictions carried, and the gate was not the binding
constraint.** The gate fix did precisely what the arithmetic said it would —
the 14 and 13 spurious halts of benchmark 4 became zero in both runs — and
coverage still did not reliably clear the rule tree. The risk recorded before
the run is what intervened, and it was the dominant exit in both replicates.

The durable result is the ranking. For the first time it beat the hand-built
decision tree at significance in **both** runs.

## Results, both runs

| | run a | run b | `rules` |
|---|---|---|---|
| coverage | **0.679** | 0.536 | 0.571 |
| precision | **0.29** | 0.26 | 0.20 |
| nDCG | **0.796** | 0.767 | 0.657 |
| forbidden hits | 0.00 | 0.00 | 0.00 |
| redundant calls | 0.13 | 0.13 | 0.00 |
| tools run | 3.87 | 4.07 | 4.27 |
| decision calls | 2.67 | 2.73 | 2.00 |

Paired against `rules`, 95% bootstrap:

| metric | run a | run b |
|---|---|---|
| coverage | +0.107 [−0.321, +0.500] | −0.036 [−0.536, +0.429] |
| precision | +0.094 [−0.053, +0.245] | +0.059 [−0.105, +0.226] |
| nDCG | **+0.139 [+0.036, +0.282]** | **+0.109 [+0.005, +0.262]** |
| tool calls | −0.267 [−1.067, +0.600] | −0.067 [−0.867, +0.800] |

All four mock arms reproduced the preregistered budgeted table exactly in
both runs — `rules` 0.57/0.20/0.66/4.27/2.00, `cheapest`
0.57/0.14/0.47/5.87/1.00, `random` 0.21/0.06/0.46/4.33/1.87, `oracle`
1.00/0.57/0.96/1.73/1.47. Amendment 3 made that a release gate rather than a
prediction, because applying the comparative act threshold to arms scoring on
the absolute scale would have moved all four baselines. The gate held.

The `redundant_calls` 0.13 is **not** a re-run. It is two *failed* executions
in `short_history`, identical in both replicates —
`relative_strength.beta_regime` ("no usable history for the benchmark SPY")
and then `signal.mcglone` ("missing inputs: relative strength"). The metric
is `tool_calls − distinct_ok`, so a failure counts. `cheapest` has shown the
same 0.13 in every benchmark; arm B now reaches those two calls because it
runs more analyses. No analysis ran twice.

## The predictions

**E1 — does coverage recover? PASSED then FAILED.** Required mean coverage
≥ 0.57, the rule tree's level. Run a gave 0.679, run b gave 0.536. Benchmark
4 gave 0.43 and 0.57.

**E2 — does the right analysis now run? PASSED then FAILED.** Required
pivotal reach ≥ 5/7, an advance on everything measured. Run a gave exactly
5/7 — the best this project has recorded — and run b gave 4/7. Benchmark 4
gave 2/7 and 3/7; benchmark 3 gave 4/7.

**E3 — is the cost win kept? FAILED in both.** The prediction required the
paired tool-call interval's **upper** bound at or below zero. Run a gave
−0.267 [−1.067, +0.600] and run b −0.067 [−0.867, +0.800]. Amendment 3 named
this the prediction most likely to fail and the one that mattered most, and
its refutation clause applies as written: tools run went 2.33 in benchmark 4
to 3.87 and 4.07 here, so **benchmark 4's cost advantage was the broken gate
stopping early, not better selection.** The `−1.933 [−2.267, −1.600]` claim
is withdrawn.

Preregistered criterion 3 — match `rules` on coverage at no greater tool cost
— is consequently a **draw rather than a pass**. Coverage is indistinguishable
from the rule tree in both runs and tool calls are indistinguishable in both,
with a mean of slightly fewer. Benchmark 4's first pass of criterion 3 should
be read as withdrawn along with the cost figure that produced it.

**E4 — is the ranking quality kept? PASSED in both.** Required nDCG ≥ 0.74.
Run a gave 0.796 and run b 0.767, both the best measured in this project, and
both beat `rules` with the paired interval excluding zero. Benchmark 4
carried that comparison in only one of its two runs; here it carries in both.

Mean pair gap held at +0.117 and +0.122, against benchmark 4's +0.122 and
+0.115. Per pair:

| pair | run a | run b |
|---|---|---|
| momentum | +0.220 | +0.240 |
| volume | +0.210 | +0.210 |
| volatility | +0.160 | +0.170 |
| trend | +0.140 | +0.110 |
| divergence | +0.000 | +0.020 |
| relative strength | −0.030 | −0.020 |

Four of six pairs are strongly positive in both runs, and the two that are
not are the same two. A gate change was not expected to touch the ranking,
and it did not.

**E5 — does the stop signal come back? FAILED in both, on power.** Required
the `stop_enough` AUC interval entirely above 0.5 on at least 8 positive
labels. Run a gave AUC 0.795 [0.635, 0.927] and run b 0.712 [0.493, 0.889],
whose interval crosses. Both rest on **4 positives**.

The label is "every expected analysis had already run, so stopping would have
lost nothing", which requires analyses to have run. At about 4 tools per
scenario it is true in 4 of 40 rounds. This has now failed on power three
times — 3 positives in benchmark 4, 4 and 4 here — so preregistered criterion
4 still cannot be measured. It is a precondition, not a result.

## Implementation verification: both items hit

Read off benchmark 4's distributions in advance, so these confirm the change
does what the arithmetic says and are not evidence for it.

| band | b4 run 1 | b4 run 2 | b5 run a | b5 run b |
|---|---|---|---|---|
| `act_clear` | 2 | 2 | **11** | **10** |
| `act_tied` | 0 | 0 | 1 | 1 |
| `consider` | 14 | 17 | 6 | 7 |
| `indecisive` | 3 | 1 | **14** | **14** |
| `stop_repeated_indecision` | 0 | 0 | **8** | **8** |
| `stop_no_useful_tool` | 14 | 13 | **0** | **0** |

`act_clear` landed in the predicted 10–16 band, and `stop_no_useful_tool` was
eliminated, as the absolute map never falling below 0.40 implied. The minimum
absolute top score was 0.67 in both runs, against a 0.40 floor, across all 80
decision rounds.

## The risk recorded before the run is what capped coverage

Amendment 3's pre-run note said:

> `indecisive` rises to 13-16 rounds, because a round can clear the gate
> while the top two comparative scores sit closer than `margin_min`. That
> band runs the cheapest viable candidate and increments a streak, and
> `indecision_limit = 2` turns two consecutive indecisive rounds into
> `stop_repeated_indecision`. So coverage may still be capped, by a different
> branch than the one amendment 3 fixes.

That is what happened, identically in both runs:

| | run a | run b |
|---|---|---|
| exits on `repeated_indecision` | **8/15** | **8/15** |
| exits on `tool_call_cap` | 7/15 | 7/15 |
| median top-two comparative margin | 0.080 | 0.070 |

`margin_min` is 0.10. Because the gate never fell below its floor, every
round that does not clear the act band enters the grey band, where the margin
is the only remaining test. **It routes 22 of 40 rounds and ends 8 of the 15
runs**, at 2 or 3 of the 4 permitted tool calls. The eight runs that stopped
early are the same eight scenarios in both replicates, stopping after the
same number of calls.

No threshold was changed in response, as the note committed. Amendment 4
addresses the band, and it changes the margin test rather than
`indecision_limit`, for reasons recorded there.

## The two runs differ by one scenario, not by noise

Benchmark 4's two runs gave coverage 0.43 and 0.57, which read as
replicate-to-replicate noise. These two did not behave that way. Every
scenario exited for the same reason after the same number of tool calls in
both runs, with a single exception:

| scenario | run a | run b |
|---|---|---|
| `extended_run` | `tool_call_cap`, 4 calls, coverage 1.00 | `tool_call_cap`, 7 calls, coverage **0.00** |

One scenario of the seven carrying required analyses is worth 0.143 of mean
coverage, and 0.679 − 0.536 = 0.143 exactly. **E1's pass/fail turned on one
scenario**, which means the primary metric has a resolution of ±0.143 and
cannot resolve 0.54 from 0.68. That is a limitation of the metric's power. It
is recorded here rather than used to reinterpret the outcome: by the bar as
written, E1 failed.

The mechanism is measurable. The model is not deterministic, but its jitter
is small and bounded. Across the 40 rounds the two runs share, every round's
comparative answers differ, 213 of 316 per-tool scores moved, and **the
largest movement is 0.05** — far smaller than the distance from a median
score to any band edge, which is why the band counts came out within one of
each other, and why the comparative map's median sum reproduced to 0.01
(2.07 and 2.08). A score sitting *near* an edge is the exception, and
`extended_run` is that exception: 0.05 of jitter across a threshold, worth
0.143 of the primary metric.

So replicates remain worth their cost, but for a sharper reason than
benchmark 4 suggested. They are not averaging out broad noise; they are
sampling which near-threshold scores happen to fall which way.

## What this says about the question, not the policy

Three experiments have now changed the inputs (benchmark 3's conditional tool
descriptions), the proposition (benchmark 4's comparative question) and the
reader (benchmark 5's two-map policy). The ranking improved at every step and
is now significantly better than a hand-built decision tree, twice over, with
evidence-sensitivity holding at a +0.12 pair gap. The agent still does not
convert that into coverage.

One structural fact underlies the remaining problem. The comparative
proposition — *exactly one analysis is the best use of the next step; is it
this one?* — is only decidable jointly across the field, but
`jev/questions.py` records that each question is evaluated in isolation
against the same state, so no call can see what the others scored and none
can normalise. Measured over all 80 rounds, the comparative scores sum to
2.07 and 2.08 median rather than to 1.0, and the sum rises with the size of
the field: 1.91 and 1.92 at seven candidates, 2.49 and 2.50 at nine.

The model did shift scale honestly when the proposition changed — from about
0.74 to about 0.40 — so it read the exclusivity. It cannot enforce it. Every
threshold applied to a *gap* on that map therefore has no fixed meaning,
which is the argument amendment 4 rests on.

## Standing conclusion

Amendment 3 was correct about the category error and wrong about the
consequence. Reading "which one wins" as "is anything worth running" was a
genuine confusion, fixing it eliminated 27 spurious halts across two runs,
and it turned out not to be the binding constraint on coverage. The binding
constraint is the next band down, and it was named in advance.

What should be carried forward as established: the comparative question
ranks better than a hand-built decision tree, at significance, in two of two
runs; the pair gap is stable at +0.12 with the same four of six pairs
separating; forbidden analyses remain at zero in every run of every
benchmark. What should be carried back: benchmark 4's cost advantage, and
with it criterion 3's first pass.

What remains unmeasurable: criterion 4, for want of positive labels. It needs
coverage above roughly 0.7 before the stop signal can be scored at all, which
makes it a downstream beneficiary of amendment 4 rather than a test of it.
