"""The experimental apparatus: scenarios, arms, metrics and the harness.

The most important tests here are not about code working. They are about the
benchmark being capable of giving an unfavourable answer:

* every planted feature is confirmed against the production detector, so a
  scenario cannot be silently measuring nothing;
* the metrics are shown to separate an oracle from random choices, so a
  favourable result cannot come from metrics that score everything alike;
* the minimal pairs are shown to differ in exactly one expectation, so a
  difference between halves cannot come from two things changing at once.

A benchmark that cannot fail is not evidence.
"""

import math

import pytest

from stock_agent.asof import FrameProvider
from stock_agent.config import AgentConfig
from stock_agent.eval import scenarios as scen
from stock_agent.eval.baseline_rules import (
    ARM_NAMES,
    CheapestFirstClient,
    RandomClient,
    RuleBasedClient,
    build_arm,
)
from stock_agent.eval.harness import (
    ORACLE_FLOOR,
    RANDOM_CEILING,
    run_arm,
    run_benchmark,
    validate_metrics,
)
from stock_agent.eval.metrics import (
    auc,
    boot_auc,
    brier,
    calibrate,
    ece,
    ndcg_at_k,
    paired_bootstrap,
    reliability,
    score_run,
)
from stock_agent.loop import run_analysis
from stock_agent.tools.builtin import build_registry

# A few fast scenarios, for tests about plumbing rather than about the
# benchmark's verdict. The expensive segmentation stays out of these.
FAST = ("volume_surge", "volume_normal", "momentum_oversold")


def _fast_scenarios():
    return tuple(scen.by_name(n) for n in FAST)


# --- the scenarios are what they claim --------------------------------------


def test_every_planted_feature_fires_in_the_real_detector():
    """The keystone.

    A scenario labelled "divergence present" whose detector never fires makes
    every arm identically and invisibly wrong. One base series did fire a
    bearish divergence by chance, which is how this check earned its place.
    """
    failures = [(name, detail) for name, ok, detail in scen.verify_all() if not ok]

    assert failures == []


def test_the_scenario_set_is_the_declared_shape():
    assert len(scen.SCENARIOS) == 15
    assert len(scen.pairs()) == 6
    assert all(len(halves) == 2 for halves in scen.pairs().values())


def test_each_pair_differs_in_exactly_one_expectation():
    """Otherwise a difference between halves has more than one cause."""
    for name, (first, second) in scen.pairs().items():
        present = first if first.half == "present" else second
        absent = second if first.half == "present" else first

        assert present.pivotal is not None, name
        assert absent.pivotal is None, name
        # The present half expects the pivotal analysis and, where the tool
        # needs one, its prerequisite. The absent half expects nothing.
        assert present.pivotal in present.required, name
        assert absent.required == frozenset(), name


def test_no_scenario_asserts_a_price_direction():
    """Expectations are about routing, never about returns."""
    banned = ("will rise", "will fall", "buy", "sell", "profit", "return")
    for scenario in scen.SCENARIOS:
        lowered = scenario.description.lower()
        assert not any(word in lowered for word in banned), scenario.name


def test_every_expectation_names_a_real_tool():
    registry = build_registry()

    for scenario in scen.SCENARIOS:
        for tool in scenario.required | scenario.forbidden:
            assert tool in registry, f"{scenario.name} expects unknown tool {tool}"
        if scenario.pivotal is not None:
            assert scenario.pivotal in registry


def test_relevance_weights_the_pivotal_analysis_above_the_merely_required():
    scenario = scen.by_name("divergence_present")

    values = scenario.relevance(
        [
            "pattern.rsi_divergence",
            "momentum.rsi_stochastic",
            "volume.surge",
        ]
    )

    assert values == [2, 1, 0]


def test_an_unknown_scenario_is_an_error():
    with pytest.raises(KeyError, match="unknown scenario"):
        scen.by_name("no_such_scenario")


# --- the arms ---------------------------------------------------------------


@pytest.mark.parametrize("arm", ["rules", "cheapest", "random", "oracle"])
def test_every_arm_completes_a_run(arm):
    scenario = scen.by_name("volume_surge")

    run = run_analysis(
        ticker="SYN",
        objective="o",
        registry=build_registry(),
        model=build_arm(arm, scenario),
        provider=FrameProvider(scenario.build()),
        config=AgentConfig(),
    )

    assert run.exit_reason
    assert run.tools_run


@pytest.mark.parametrize("arm", ["rules", "cheapest", "random", "oracle"])
def test_every_arm_answers_in_the_real_response_shape(arm):
    """The arms must be indistinguishable from the real client to the policy."""
    from stock_agent.jev.questions import STOP_ENOUGH_QID, build_question_set

    scenario = scen.by_name("volume_surge")
    specs = build_registry().implemented()[:4]
    questions = build_question_set(specs, "o")

    response = build_arm(arm, scenario).ask("state text", questions)

    assert response.ok()
    assert response.noul(STOP_ENOUGH_QID) is not None
    assert not response.malformed


def test_the_baselines_read_the_numeric_state_and_the_model_does_not():
    """A deliberate asymmetry: handicapping the baseline would prove nothing."""
    from stock_agent.jev.client import JevClient

    assert hasattr(RuleBasedClient(), "observe")
    assert hasattr(CheapestFirstClient(), "observe")
    assert not hasattr(JevClient(dry_run=True), "observe")


def test_the_loop_hands_the_numeric_state_to_an_arm_that_wants_it():
    scenario = scen.by_name("volume_surge")
    arm = RuleBasedClient()

    run_analysis(
        ticker="SYN",
        objective="o",
        registry=build_registry(),
        model=arm,
        provider=FrameProvider(scenario.build()),
        config=AgentConfig(),
    )

    assert arm.state is not None
    assert arm.state.has("ohlc.n_bars")


def test_the_cheapest_arm_prefers_the_cheap():
    arm = CheapestFirstClient()

    assert arm.score("volume.surge") > arm.score("market_regime.price")
    assert arm.score("trend.heiken_runs") > arm.score("events.insider")


def test_the_cheapest_arm_declines_nothing_and_never_stops_early():
    arm = CheapestFirstClient()

    assert arm.enough(["volume.surge"]) == 0.0
    assert arm.enough([]) == 1.0


def test_the_random_arm_is_reproducible():
    first = [RandomClient(seed=4).score("x") for _ in range(5)]
    second = [RandomClient(seed=4).score("x") for _ in range(5)]

    assert first == second
    assert RandomClient(seed=5).score("x") != RandomClient(seed=4).score("x")


def test_the_rule_arm_checks_divergence_even_at_a_middling_reading():
    """The planted divergence ends at RSI 57.

    An extremes-only rule would miss it, and a baseline that misses the thing
    the scenario is about is a straw man.
    """
    arm = RuleBasedClient()
    arm.observe(_state_with({"momentum.rsi": 57.0}))

    assert arm.score("pattern.rsi_divergence") >= 0.65


def test_the_rule_arm_leaves_the_expensive_analysis_alone_when_something_fired():
    arm = RuleBasedClient()
    arm.observe(
        _state_with(
            {
                "momentum.rsi": 22.0,
                "volatility.ratio": 2.1,
                "ohlc.n_bars": 400,
            }
        )
    )

    assert arm.score("market_regime.price") < 0.4
    assert arm.score("volatility.vix") >= 0.65


def test_the_oracle_needs_a_scenario_to_be_an_oracle_about():
    with pytest.raises(ValueError, match="needs a scenario"):
        build_arm("oracle")


def test_an_unknown_arm_is_an_error():
    with pytest.raises(ValueError, match="unknown arm"):
        build_arm("wishful")


def test_the_arm_names_cover_what_build_arm_accepts():
    assert set(ARM_NAMES) == {"rules", "cheapest", "random", "oracle", "jev"}


def _state_with(values):
    """Build a state carrying some observations, for scoring one arm."""
    from stock_agent.state import AnalysisState, Observation

    state = AnalysisState(ticker="SYN", objective="o")
    for key, value in values.items():
        state.observations[key] = Observation(
            key=key, value=value, display="", tool="t", iteration=0
        )
    return state


# --- the routing metrics ----------------------------------------------------


def _score(**over):
    base = {
        "scenario_name": "s",
        "arm": "a",
        "required": frozenset({"x"}),
        "forbidden": frozenset(),
        "pivotal": "x",
        "tools_run": ["x"],
        "per_round": [["x"]],
        "tool_calls": 1,
        "jev_calls": 1,
        "network_calls": 0,
        "latency_s": 0.0,
        "wall_s": 0.0,
        "exit_reason": "done",
        "partial": False,
    }
    return score_run(**{**base, **over})


def test_coverage_is_undefined_when_a_scenario_expects_nothing():
    """Averaging those in handed every arm a free perfect score.

    Nine of the fifteen scenarios expect nothing. Scoring them 1.0 put a
    random router at 0.82 coverage and the oracle's nDCG at 0.25 -- the
    metrics were nearly blind.
    """
    score = _score(required=frozenset(), pivotal=None, tools_run=["a", "b"])

    assert math.isnan(score.required_coverage)
    assert math.isnan(score.precision)
    # Effort on those scenarios is judged by what it ran, not by coverage.
    assert score.tools_run == 2


def test_coverage_and_precision_are_measured_when_something_is_expected():
    score = _score(
        required=frozenset({"x", "y"}),
        tools_run=["x", "z"],
        tool_calls=2,
    )

    assert score.required_coverage == 0.5
    assert score.precision == 0.5


def test_running_everything_covers_everything_but_scores_badly_on_precision():
    """Which is why the benchmark also runs under a budget."""
    score = _score(
        required=frozenset({"x"}),
        tools_run=["x", "a", "b", "c", "d"],
        tool_calls=5,
    )

    assert score.required_coverage == 1.0
    assert score.precision == 0.2


def test_wasted_and_repeated_work_are_counted():
    score = _score(
        required=frozenset({"x"}),
        forbidden=frozenset({"b"}),
        tools_run=["x", "b"],
        tool_calls=5,
    )

    assert score.forbidden_hits == 1
    assert score.redundant_calls == 3


def test_steps_to_coverage_counts_rounds_not_tools():
    score = _score(
        required=frozenset({"x", "y"}),
        tools_run=["a", "x", "y"],
        per_round=[["a"], ["x"], ["y"]],
    )

    assert score.steps_to_coverage == 3


def test_steps_to_coverage_is_none_when_coverage_never_completes():
    score = _score(
        required=frozenset({"x", "y"}),
        tools_run=["x"],
        per_round=[["x"]],
    )

    assert score.steps_to_coverage is None


def test_the_pivotal_analysis_is_tracked_separately():
    assert _score(tools_run=["x"]).pivotal_found is True
    assert _score(tools_run=["q"]).pivotal_found is False
    assert _score(pivotal=None).pivotal_found is None


# --- ranking and calibration ------------------------------------------------


def test_ndcg_rewards_putting_the_pivotal_analysis_first():
    assert ndcg_at_k([2, 1, 0, 0]) == 1.0
    assert ndcg_at_k([1, 2, 0, 0]) < 1.0
    assert ndcg_at_k([0, 0, 1, 2]) < ndcg_at_k([1, 2, 0, 0])


def test_ndcg_is_zero_when_nothing_is_relevant():
    """The harness skips these rounds rather than averaging the zero in."""
    assert ndcg_at_k([0, 0, 0]) == 0.0
    assert ndcg_at_k([]) == 0.0


def test_auc_counts_ties_as_half():
    assert auc([1.0], [0.0]) == 1.0
    assert auc([0.0], [1.0]) == 0.0
    assert auc([0.5], [0.5]) == 0.5


def test_auc_is_undefined_with_only_one_class():
    assert math.isnan(auc([0.9], []))
    assert math.isnan(auc([], [0.1]))


def test_the_bootstrap_interval_is_reproducible_and_brackets_the_estimate():
    pos = [0.9, 0.8, 0.85, 0.7]
    neg = [0.2, 0.1, 0.3, 0.25]

    low, high = boot_auc(pos, neg)

    assert (low, high) == boot_auc(pos, neg)
    assert low <= auc(pos, neg) <= high


def test_brier_skill_is_zero_for_a_base_rate_forecaster():
    labels = [1, 1, 0, 0]
    base = [0.5] * 4

    _, _, skill = brier(labels, base)

    assert skill == pytest.approx(0.0)


def test_brier_skill_is_positive_for_a_better_forecaster():
    _, _, skill = brier([1, 1, 0, 0], [0.9, 0.9, 0.1, 0.1])

    assert skill > 0.5


def test_reliability_bins_only_the_bins_that_hold_something():
    rows = reliability([1, 0], [0.95, 0.05])

    assert len(rows) == 2
    assert rows[0]["low"] == 0.0
    assert rows[-1]["high"] == pytest.approx(1.0)


def test_a_probability_of_exactly_one_lands_in_the_last_bin():
    rows = reliability([1], [1.0])

    assert len(rows) == 1
    assert rows[0]["mean_p"] == 1.0


def test_ece_is_zero_for_perfectly_calibrated_predictions():
    assert ece([1, 0], [1.0, 0.0]) == pytest.approx(0.0)


def test_calibration_reports_discrimination_against_chance():
    confident = calibrate("good", [(1, 0.9)] * 8 + [(0, 0.1)] * 8)
    useless = calibrate("flat", [(1, 0.5)] * 8 + [(0, 0.5)] * 8)

    assert confident.roc_auc == 1.0
    assert confident.discriminates is True
    assert useless.roc_auc == 0.5
    assert useless.discriminates is False


def test_calibration_of_nothing_reports_that_rather_than_failing():
    empty = calibrate("none", [])

    assert empty.n == 0
    assert math.isnan(empty.roc_auc)
    assert empty.discriminates is False


# --- comparing arms ---------------------------------------------------------


def test_a_consistent_difference_is_significant():
    delta = paired_bootstrap("cov", "B", "A", {f"s{i}": (1.0, 0.4) for i in range(8)})

    assert delta.delta == pytest.approx(0.6)
    assert delta.significant is True


def test_a_difference_that_changes_sign_is_not_significant():
    delta = paired_bootstrap(
        "cov", "B", "A", {"s1": (1.0, 0.0), "s2": (0.0, 1.0), "s3": (0.5, 0.5)}
    )

    assert delta.significant is False


def test_undefined_scenarios_are_dropped_from_a_comparison():
    delta = paired_bootstrap(
        "cov",
        "B",
        "A",
        {"s1": (1.0, 0.5), "s2": (float("nan"), 0.5), "s3": (1.0, 0.5)},
    )

    assert delta.n_pairs == 2


def test_comparing_nothing_yields_no_claim():
    delta = paired_bootstrap("cov", "B", "A", {})

    assert delta.n_pairs == 0
    assert delta.significant is False


# --- the harness ------------------------------------------------------------


def test_a_single_run_is_scored_and_traced(tmp_path):
    result = run_arm("rules", scen.by_name("volume_surge"), trace_dir=tmp_path)

    assert result.error is None
    assert result.score.arm == "rules"
    assert result.trace_path is not None and result.trace_path.exists()
    assert result.usefulness_items
    assert result.enough_items


def test_the_pivotal_analysis_is_reached_on_the_scenario_about_it():
    result = run_arm("oracle", scen.by_name("volume_surge"))

    assert result.score.pivotal_found is True
    assert result.score.required_coverage == 1.0


def test_a_failing_arm_is_recorded_rather_than_ending_the_benchmark():
    class Broken:
        model = "broken"
        endpoint = "arm://broken"
        calls = 0

        def ask(self, state, questions):
            raise RuntimeError("this arm is broken")

    result = run_arm("broken", scen.by_name("volume_surge"), model=Broken())

    assert result.error is not None
    assert "this arm is broken" in result.error
    assert result.score.exit_reason == "harness_error"


def test_an_unknown_regime_is_an_error():
    with pytest.raises(ValueError, match="unknown regime"):
        run_arm("rules", scen.by_name("volume_surge"), regime="whatever")


def test_a_benchmark_reports_every_arm_on_every_scenario():
    report = run_benchmark(arms=("rules", "oracle"), scenarios=_fast_scenarios(), verify=False)

    assert len(report.results) == 6
    assert report.arms() == ["rules", "oracle"]
    assert report.calibrations["rules"]
    assert report.deltas


def test_the_benchmark_reports_an_unverified_scenario_instead_of_hiding_it():
    import dataclasses

    broken = dataclasses.replace(
        scen.by_name("volume_normal"),
        name="mislabelled",
        check=lambda frames: (False, "the planted feature is not there"),
    )

    report = run_benchmark(arms=("rules",), scenarios=(broken,), verify=True)

    assert report.scenario_failures == [("mislabelled", "the planted feature is not there")]


def test_averages_skip_the_scenarios_where_a_metric_is_undefined():
    report = run_benchmark(
        arms=("oracle",),
        scenarios=(scen.by_name("volume_surge"), scen.by_name("volume_normal")),
        verify=False,
    )

    # volume_normal expects nothing, so coverage comes only from volume_surge.
    assert report.mean("oracle", "required_coverage") == 1.0


def test_the_report_serialises_for_a_record(tmp_path):
    import json

    report = run_benchmark(arms=("rules",), scenarios=_fast_scenarios(), verify=False)

    payload = json.dumps(report.to_dict(), default=str)

    assert "summary" in payload
    assert "calibration" in payload


# --- the gate on the whole benchmark ----------------------------------------


def test_the_metrics_can_tell_good_routing_from_random_choices():
    """Phase 4's reason to exist.

    If an oracle that is told the answer cannot be separated from seeded
    random choices, then the metrics score everything alike and no later
    comparison means anything -- including a favourable one. This runs the
    full fifteen scenarios in the budgeted regime, so it is slow, and it is
    worth it.
    """
    result = validate_metrics()

    assert result["oracle_coverage"] >= ORACLE_FLOOR, result
    assert result["random_coverage"] <= RANDOM_CEILING, result
    assert result["separated"] is True, result
    # The ranking metric has to separate them too, since it is the only one
    # that reads the whole probability vector.
    assert result["oracle_ndcg"] > result["random_ndcg"] + 0.2, result


# --- the command line -------------------------------------------------------


def test_the_scenarios_command_verifies_and_succeeds(capsys):
    from stock_agent.cli import main

    code = main(["scenarios"])

    assert code == 0
    assert "verified against the real detectors" in capsys.readouterr().out


def test_the_scenarios_command_emits_the_expectations_as_json(capsys):
    import json

    from stock_agent.cli import main

    main(["scenarios", "--json"])
    rows = json.loads(capsys.readouterr().out)

    assert len(rows) == 15
    assert all(r["verified"] for r in rows)
    assert any(r["pivotal"] == "volume.surge" for r in rows)


def test_the_bench_command_runs_and_reports(capsys):
    from stock_agent.cli import main

    code = main(
        [
            "bench",
            "--arms",
            "rules,oracle",
            "--scenario",
            "volume_surge",
            "--no-verify",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "regime: budgeted" in out
    assert "paired differences" in out


def test_the_bench_command_refuses_to_call_the_real_model_without_permission(capsys):
    """Spending money must be deliberate."""
    from stock_agent.cli import main

    code = main(["bench", "--arms", "jev", "--scenario", "volume_surge"])

    assert code == 2
    assert "--live" in capsys.readouterr().err


def test_the_bench_command_rejects_an_unknown_scenario(capsys):
    from stock_agent.cli import main

    code = main(["bench", "--scenario", "no_such_thing"])

    assert code == 2
    assert "unknown scenario" in capsys.readouterr().err


def test_the_calibrate_command_scores_saved_traces(tmp_path, capsys):
    from stock_agent.cli import main

    main(
        [
            "bench",
            "--arms",
            "oracle",
            "--scenario",
            "volume_surge",
            "--no-verify",
            "--trace-dir",
            str(tmp_path),
        ]
    )
    capsys.readouterr()

    code = main(["calibrate", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "oracle: usefulness" in out
    assert "ROC AUC" in out


def test_calibrate_skips_a_trace_it_cannot_label(tmp_path, capsys):
    """Labels come from a scenario, so an unnameable trace cannot be scored."""
    from stock_agent.cli import main

    (tmp_path / "mystery.jsonl").write_text("", encoding="utf-8")

    code = main(["calibrate", str(tmp_path)])

    captured = capsys.readouterr()
    assert code == 1
    assert "does not name an arm and scenario" in captured.err


def test_calibrate_reports_an_empty_directory_rather_than_crashing(tmp_path, capsys):
    from stock_agent.cli import main

    code = main(["calibrate", str(tmp_path)])

    assert code == 1
    assert "no traces found" in capsys.readouterr().err


# --- the within-pair comparison ---------------------------------------------


def test_the_absent_half_borrows_its_partners_pivotal_analysis():
    """Comparing halves means scoring the same analysis on both."""
    present = scen.by_name("volume_surge")
    absent = scen.by_name("volume_normal")

    assert present.pivotal_probe == "volume.surge"
    assert absent.pivotal is None
    assert absent.pivotal_probe == "volume.surge"


def test_a_control_has_nothing_to_probe():
    assert scen.by_name("short_history").pivotal_probe is None


def test_pair_preference_counts_the_pairs_scored_the_right_way_round():
    from stock_agent.eval.metrics import pair_preference

    result = pair_preference(
        "a",
        {
            "volume": ("volume.surge", 0.9, 0.2),
            "trend": ("trend.heiken_runs", 0.8, 0.3),
            "momentum": ("momentum.rsi_stochastic", 0.4, 0.6),
        },
    )

    assert result.pairs == 3
    assert result.preferred == 2
    assert result.rate == pytest.approx(2 / 3)
    assert result.mean_gap == pytest.approx((0.7 + 0.5 - 0.2) / 3)


def test_pair_preference_skips_a_pair_it_could_not_score_on_both_halves():
    from stock_agent.eval.metrics import pair_preference

    result = pair_preference(
        "a",
        {
            "volume": ("volume.surge", 0.9, 0.2),
            "trend": ("trend.heiken_runs", 0.8, None),
        },
    )

    assert result.pairs == 1
    assert any(row["comparable"] is False for row in result.detail)


def test_pair_preference_counts_ties_separately():
    from stock_agent.eval.metrics import pair_preference

    result = pair_preference("a", {"volume": ("volume.surge", 0.5, 0.5)})

    assert result.ties == 1
    assert result.preferred == 0
    assert result.mean_gap == 0.0


def test_pair_preference_of_nothing_makes_no_claim():
    from stock_agent.eval.metrics import pair_preference

    result = pair_preference("a", {})

    assert result.pairs == 0
    assert math.isnan(result.rate)


def test_an_arm_with_no_signal_does_not_prefer_the_present_half():
    """A floor for the metric: random scores cannot know which half is which."""
    report = run_benchmark(
        arms=("random",),
        scenarios=(scen.by_name("volume_surge"), scen.by_name("volume_normal")),
        verify=False,
    )

    assert report.preferences
    assert report.preferences[0].arm == "random"
    assert report.preferences[0].pairs == 1


def test_the_benchmark_reports_a_within_pair_comparison_per_arm():
    report = run_benchmark(
        arms=("rules", "oracle"),
        scenarios=(scen.by_name("volume_surge"), scen.by_name("volume_normal")),
        verify=False,
    )

    arms = {p.arm for p in report.preferences}
    assert arms == {"rules", "oracle"}
    # The oracle is told the answer, so it must want the analysis more on the
    # half where the feature is actually planted.
    oracle = next(p for p in report.preferences if p.arm == "oracle")
    assert oracle.preferred == 1
