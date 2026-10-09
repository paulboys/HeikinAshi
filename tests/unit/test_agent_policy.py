"""Every branch of the routing policy.

The policy is a pure function, so these cover it exhaustively rather than
sampling it through a running loop.
"""

import pytest

from stock_agent.config import PolicyConfig
from stock_agent.policy import decide

CFG = PolicyConfig()


def _decide(usefulness, enough=0.1, conflict=0.1, **kw):
    kw.setdefault("config", CFG)
    kw.setdefault("indecision_streak", 0)
    kw.setdefault("tools_run", 3)
    return decide(usefulness, enough, conflict, **kw)


# --- acting -----------------------------------------------------------------


def test_clear_winner_runs_alone():
    d = _decide({"a": 0.90, "b": 0.20})

    assert d.band == "act_clear"
    assert d.selected == ("a",)
    assert d.should_stop is False
    assert "act" in d.rationale


def test_two_strong_and_inseparable_candidates_both_run():
    """Running both beats paying for another round trip to break the tie."""
    d = _decide({"a": 0.88, "b": 0.86})

    assert d.band == "act_tied"
    assert set(d.selected) == {"a", "b"}


def test_corun_is_capped():
    cfg = PolicyConfig(max_corun=1)
    d = _decide({"a": 0.88, "b": 0.86}, config=cfg)

    assert len(d.selected) == 1


def test_single_candidate_needs_no_margin():
    d = _decide({"a": 0.90})

    assert d.band == "act_clear"
    assert d.margin == pytest.approx(0.90)


# --- the grey band ----------------------------------------------------------


def test_grey_band_with_a_clear_margin_still_runs():
    d = _decide({"a": 0.55, "b": 0.20})

    assert d.band == "consider"
    assert d.selected == ("a",)


def test_grey_band_without_a_margin_is_indecisive_but_still_acts():
    d = _decide({"a": 0.52, "b": 0.50})

    assert d.band == "indecisive"
    assert d.indecision_streak == 1
    # An iteration that runs nothing cannot change the state it is stuck on.
    assert len(d.selected) == 1


def test_indecision_breaks_ties_toward_the_cheap_tool():
    d = _decide(
        {"expensive": 0.52, "cheap": 0.50},
        costs={"expensive": "high", "cheap": "low"},
    )

    assert d.selected == ("cheap",)


def test_repeated_indecision_terminates():
    d = _decide({"a": 0.52, "b": 0.50}, indecision_streak=1)

    assert d.band == "stop_repeated_indecision"
    assert d.exit_reason == "repeated_indecision"
    assert d.should_stop is True


def test_a_decisive_iteration_clears_the_streak():
    d = _decide({"a": 0.90, "b": 0.10}, indecision_streak=1)

    assert d.indecision_streak == 0


# --- declining --------------------------------------------------------------


def test_nothing_useful_stops_with_its_own_reason():
    d = _decide({"a": 0.20, "b": 0.10})

    assert d.band == "stop_no_useful_tool"
    assert d.exit_reason == "no_useful_tool"


def test_empty_candidate_set_stops():
    d = _decide({})

    assert d.band == "stop_nothing_available"
    assert d.exit_reason == "no_candidates"


# --- stopping ---------------------------------------------------------------


def test_sufficient_evidence_stops():
    d = _decide({"a": 0.9}, enough=0.95)

    assert d.band == "stop_sufficient"
    assert d.exit_reason == "jev_sufficient"


def test_low_confidence_sufficiency_never_stops():
    """The stopping rule is the application's, not the model's."""
    d = _decide({"a": 0.9}, enough=0.50)

    assert d.should_stop is False
    assert d.band == "act_clear"


def test_sufficiency_before_the_minimum_tool_count_does_not_stop():
    d = _decide({"a": 0.9}, enough=0.99, tools_run=1)

    assert d.should_stop is False
    assert any("minimum" in n for n in d.notes)


def test_conflict_vetoes_a_stop_once():
    d = _decide({"a": 0.9}, enough=0.95, conflict=0.80)

    assert d.should_stop is False
    assert d.stop_vetoed_by_conflict is True
    assert any("disagrees" in n for n in d.notes)


def test_the_veto_cannot_repeat():
    """A second veto would be a loop, so the stop is honoured."""
    d = _decide({"a": 0.9}, enough=0.95, conflict=0.80, conflict_veto_used=True)

    assert d.band == "stop_sufficient"


def test_low_conflict_does_not_veto():
    d = _decide({"a": 0.9}, enough=0.95, conflict=0.10)

    assert d.band == "stop_sufficient"


def test_absent_sufficiency_answer_continues():
    d = _decide({"a": 0.9}, enough=None)

    assert d.should_stop is False


# --- failure ----------------------------------------------------------------


def test_model_failure_stops_without_substituting_anything():
    d = decide({"a": 0.9}, 0.1, 0.1, CFG, 0, 3, jev_failed=True)

    assert d.band == "jev_unavailable"
    assert d.exit_reason == "jev_error"
    assert d.selected == ()
    assert "substituting another model" in d.rationale


def test_failure_beats_every_other_signal():
    d = decide({"a": 0.99}, 0.99, 0.0, CFG, 0, 9, jev_failed=True)

    assert d.band == "jev_unavailable"


# --- boundaries -------------------------------------------------------------


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (0.65, "act_clear"),
        (0.6499, "consider"),
        (0.40, "consider"),
        (0.3999, "stop_no_useful_tool"),
    ],
)
def test_band_boundaries_are_inclusive_at_the_threshold(p, expected):
    assert _decide({"a": p, "b": 0.01}).band == expected


@pytest.mark.parametrize("enough", [0.70, 0.7001])
def test_stop_threshold_is_inclusive(enough):
    assert _decide({"a": 0.9}, enough=enough).band == "stop_sufficient"


def test_margin_boundary_is_inclusive():
    # Exactly at margin_min counts as decided, not indecisive.
    d = _decide({"a": 0.90, "b": 0.80})

    assert d.band == "act_clear"
    assert d.margin == pytest.approx(0.10)


def test_rationale_always_explains_the_arithmetic():
    for usefulness, enough in (
        ({"a": 0.9, "b": 0.1}, 0.1),
        ({"a": 0.5, "b": 0.1}, 0.1),
        ({"a": 0.1, "b": 0.05}, 0.1),
        ({"a": 0.9}, 0.95),
    ):
        assert _decide(usefulness, enough=enough).rationale
