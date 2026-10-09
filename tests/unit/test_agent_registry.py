"""Registry construction, gating, and dependency resolution."""

from datetime import date

import pytest

from stock_agent.conditions import MISSING, Condition, evaluate
from stock_agent.registry import (
    ToolCost,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    param_fingerprint,
)
from stock_agent.state import AnalysisState, Observation, ProvenanceRecord


def _ok(name):
    return lambda ctx: ToolResult(tool=name, success=True)


def _spec(name, **kw):
    kw.setdefault("category", "test")
    kw.setdefault("title", name)
    kw.setdefault("jev_description", f"does {name}")
    kw.setdefault("run", _ok(name))
    return ToolSpec(name=name, **kw)


def _state(**kw):
    kw.setdefault("ticker", "SYN")
    kw.setdefault("objective", "decide something")
    return AnalysisState(**kw)


def _record(state, key, value, tool, *, params=None, asof=None):
    state.observations[key] = Observation(
        key=key, value=value, display=f"{key}={value}", tool=tool, iteration=0
    )
    state.provenance[key] = ProvenanceRecord(
        tool=tool,
        param_fingerprint=param_fingerprint(tool, params or {}, asof),
        asof=None if asof is None else asof.isoformat(),
        iteration=0,
    )


# --- construction and validation --------------------------------------------


def test_registry_builds_and_counts():
    registry = ToolRegistry([_spec("a", produces=frozenset({"x"})), _spec("b")])

    assert len(registry) == 2
    assert "a" in registry
    assert registry.get("a").title == "a"


def test_duplicate_names_rejected():
    with pytest.raises(ValueError, match="duplicate tool name"):
        ToolRegistry([_spec("a"), _spec("a")])


def test_two_tools_cannot_produce_the_same_key():
    with pytest.raises(ValueError, match="produced by both"):
        ToolRegistry(
            [
                _spec("a", produces=frozenset({"x"})),
                _spec("b", produces=frozenset({"x"})),
            ]
        )


def test_unsatisfiable_requirement_rejected():
    with pytest.raises(ValueError, match="which no tool produces"):
        ToolRegistry([_spec("a", requires=frozenset({"nope"}))])


def test_dependency_cycle_rejected():
    with pytest.raises(ValueError, match="cycle"):
        ToolRegistry(
            [
                _spec("a", produces=frozenset({"x"}), requires=frozenset({"y"})),
                _spec("b", produces=frozenset({"y"}), requires=frozenset({"x"})),
            ]
        )


def test_implemented_tool_must_have_a_run_function():
    with pytest.raises(ValueError, match="no run function"):
        ToolRegistry([ToolSpec(name="a", category="t", title="a", jev_description="d", run=None)])


def test_absent_tools_are_allowed_without_a_run_function():
    registry = ToolRegistry(
        [
            ToolSpec(
                name="news",
                category="news",
                title="News",
                jev_description="d",
                implemented=False,
                absent_reason="no implementation",
                run=None,
            )
        ]
    )

    assert registry.absent()[0].name == "news"
    assert registry.implemented() == []


# --- satisfaction and fingerprints ------------------------------------------


def test_tool_is_satisfied_only_at_matching_params():
    spec = _spec("m", produces=frozenset({"rsi"}), default_params={"period": 14})
    state = _state()

    assert spec.satisfied_by(state, None) is False

    _record(state, "rsi", 70.0, "m", params={"period": 14})
    assert spec.satisfied_by(state, None) is True


def test_different_params_do_not_satisfy():
    spec = _spec("m", produces=frozenset({"rsi"}), default_params={"period": 21})
    state = _state()
    _record(state, "rsi", 70.0, "m", params={"period": 14})

    # RSI(14) must not count as RSI(21).
    assert spec.satisfied_by(state, None) is False


def test_different_asof_does_not_satisfy():
    spec = _spec("m", produces=frozenset({"rsi"}), default_params={})
    state = _state(asof=date(2024, 1, 2))
    _record(state, "rsi", 70.0, "m", asof=date(2023, 1, 2))

    assert spec.satisfied_by(state, date(2024, 1, 2)) is False


def test_tool_producing_nothing_is_never_satisfied():
    assert _spec("x").satisfied_by(_state(), None) is False


# --- gating -----------------------------------------------------------------


def test_candidates_reports_a_reason_for_every_exclusion():
    registry = ToolRegistry(
        [
            _spec("ok"),
            _spec("gated", applicable_when=(Condition("ohlc.n_bars", "gte", 500),)),
            ToolSpec(
                name="absent",
                category="c",
                title="t",
                jev_description="d",
                implemented=False,
                absent_reason="no implementation",
                run=None,
            ),
        ]
    )
    state = _state()
    _record(state, "ohlc.n_bars", 100, "price")

    eligible, excluded = registry.candidates(state)

    assert [s.name for s in eligible] == ["ok"]
    reasons = dict(excluded)
    assert "applicable_when" in reasons["gated"]
    assert "not_implemented" in reasons["absent"]


def test_live_only_tool_is_withheld_in_replay():
    registry = ToolRegistry([_spec("macro", asof_capable="none")])
    state = _state(asof=date(2024, 6, 30))

    eligible, excluded = registry.candidates(state)

    # Missing information is legitimate; contaminated history is not.
    assert eligible == []
    assert "asof_unsupported" in dict(excluded)["macro"]


def test_live_only_tool_runs_when_live():
    registry = ToolRegistry([_spec("macro", asof_capable="none")])

    eligible, _ = registry.candidates(_state())

    assert [s.name for s in eligible] == ["macro"]


def test_explicitly_withheld_tools_are_excluded():
    registry = ToolRegistry([_spec("a"), _spec("b")])

    eligible, excluded = registry.candidates(_state(), exclude=["b"])

    assert [s.name for s in eligible] == ["a"]
    assert dict(excluded)["b"] == "withheld"


def test_run_live_key_is_available_to_conditions():
    spec = _spec("macro", applicable_when=(Condition("run.live", "eq", True),))

    assert spec.applicable(_state())[0] is True
    assert spec.applicable(_state(asof=date(2024, 1, 1)))[0] is False


# --- prerequisites ----------------------------------------------------------


def test_prerequisite_plan_resolves_one_hop():
    registry = ToolRegistry(
        [
            _spec("momentum", produces=frozenset({"rsi_series"})),
            _spec("pattern", requires=frozenset({"rsi_series"})),
        ]
    )

    assert registry.prerequisite_plan("pattern", _state()) == ["momentum"]


def test_prerequisite_plan_resolves_transitively_in_order():
    registry = ToolRegistry(
        [
            _spec("price", produces=frozenset({"ohlc"})),
            _spec("momentum", produces=frozenset({"rsi"}), requires=frozenset({"ohlc"})),
            _spec("pattern", requires=frozenset({"rsi"})),
        ]
    )

    assert registry.prerequisite_plan("pattern", _state()) == ["price", "momentum"]


def test_satisfied_prerequisites_drop_out_of_the_plan():
    registry = ToolRegistry(
        [
            _spec("momentum", produces=frozenset({"rsi_series"})),
            _spec("pattern", requires=frozenset({"rsi_series"})),
        ]
    )
    state = _state()
    _record(state, "rsi_series", [1, 2], "momentum")

    assert registry.prerequisite_plan("pattern", state) == []


def test_producer_lookup():
    registry = ToolRegistry([_spec("m", produces=frozenset({"rsi"}))])

    assert registry.producer_of("rsi") == "m"
    assert registry.producer_of("nope") is None


# --- cost -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cost", "expected"),
    [
        (ToolCost(), "low"),
        (ToolCost(est_seconds=0.3), "medium"),
        (ToolCost(network=True), "medium"),
        (ToolCost(est_seconds=5.0), "high"),
        (ToolCost(network=True, network_calls=4), "high"),
    ],
)
def test_cost_classes(cost, expected):
    assert cost.cost_class == expected


# --- conditions -------------------------------------------------------------


def test_unknown_operator_rejected_at_construction():
    with pytest.raises(ValueError, match="unknown operator"):
        Condition("x", "roughly")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("op", "value", "found", "expected"),
    [
        ("exists", None, 1, True),
        ("absent", None, None, True),
        ("truthy", None, 1, True),
        ("falsy", None, 0, True),
        ("eq", 5, 5, True),
        ("neq", 5, 6, True),
        ("gt", 5, 6, True),
        ("gte", 5, 5, True),
        ("lt", 5, 4, True),
        ("lte", 5, 5, True),
        ("in", ["a", "b"], "a", True),
        ("gt", 5, 4, False),
    ],
)
def test_condition_operators(op, value, found, expected):
    lookup = (lambda _k: found) if found is not None else (lambda _k: MISSING)
    ok, _ = evaluate((Condition("k", op, value),), lookup)
    assert ok is expected


def test_missing_key_fails_closed_rather_than_raising():
    ok, reason = evaluate((Condition("nope", "gte", 5),), lambda _k: MISSING)

    assert ok is False
    assert "nope" in reason


def test_incomparable_types_fail_closed():
    ok, _ = evaluate((Condition("k", "gt", 5),), lambda _k: "a string")

    assert ok is False


def test_first_failure_is_reported():
    ok, reason = evaluate(
        (Condition("a", "eq", 1), Condition("b", "eq", 2)),
        lambda k: 1 if k == "a" else 99,
    )

    assert ok is False
    assert reason.startswith("b eq 2")
