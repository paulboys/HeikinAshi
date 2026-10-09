"""Transport, key handling and answer parsing for the decision model."""

import json
import urllib.error
from unittest.mock import patch

import pytest

from stock_agent.jev.answers import ChoiceAnswer, NoulAnswer, ScoreAnswer, parse_answers
from stock_agent.jev.client import (
    LEGACY_KEY_VAR,
    OFFICIAL_ENDPOINT,
    OFFICIAL_KEY_VAR,
    JevClient,
    find_answers,
    load_key,
)
from stock_agent.jev.questions import (
    STOP_ENOUGH_QID,
    average_choice_probabilities,
    best_next_qid,
    best_next_question,
    build_question_set,
    tool_for_best_next_qid,
    tool_for_qid,
    usefulness_qid,
    usefulness_question,
)
from stock_agent.registry import ToolSpec

SECRET = "sk-test-do-not-leak-12345"

QUESTIONS = {
    "p": {"type": "noul", "instructions": "i"},
    "c": {"type": "choice", "instructions": "i", "criteria": {"a": "A", "b": "B"}},
    "s": {"type": "score", "instructions": "i", "criteria": ["lo", "mid", "hi"]},
}


class _Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc: object):
        return False


def _opener(payload, status=200, record=None):
    def opener(request, timeout):
        if record is not None:
            record.append(request)
        return _Response(payload, status)

    return opener


def _spec(name):
    return ToolSpec(
        name=name,
        category="c",
        title=name.title(),
        jev_description=f"does {name}.",
        run=lambda ctx: None,
    )


# --- key handling -----------------------------------------------------------


def test_official_endpoint_reads_the_official_variable(monkeypatch):
    monkeypatch.setenv(OFFICIAL_KEY_VAR, SECRET)
    monkeypatch.delenv(LEGACY_KEY_VAR, raising=False)

    assert load_key(OFFICIAL_ENDPOINT) == SECRET


def test_non_official_endpoint_reads_the_legacy_variable(monkeypatch):
    """A key is only ever sent to the host it was issued for."""
    monkeypatch.setenv(OFFICIAL_KEY_VAR, "official-only")
    monkeypatch.setenv(LEGACY_KEY_VAR, "legacy-only")

    assert load_key("https://elsewhere.example/v1/systemone") == "legacy-only"


def test_env_file_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv(OFFICIAL_KEY_VAR, raising=False)
    env = tmp_path / ".env"
    env.write_text(f"# comment\nOTHER=x\n{OFFICIAL_KEY_VAR}='{SECRET}'\n", encoding="utf-8")

    assert load_key(OFFICIAL_ENDPOINT, env_path=env) == SECRET


def test_missing_key_raises_naming_the_variable(monkeypatch, tmp_path):
    monkeypatch.delenv(OFFICIAL_KEY_VAR, raising=False)

    with pytest.raises(RuntimeError, match=OFFICIAL_KEY_VAR):
        load_key(OFFICIAL_ENDPOINT, env_path=tmp_path / "absent.env")


def test_repr_never_exposes_the_key():
    client = JevClient(key=SECRET)

    assert SECRET not in repr(client)
    assert "key=<set>" in repr(client)


def test_key_is_sent_as_a_bearer_header_not_in_the_body():
    seen = []
    client = JevClient(key=SECRET, opener=_opener({"p": {"noul": 0.5}}, record=seen))

    client.ask("state", {"p": QUESTIONS["p"]})

    assert seen[0].get_header("Authorization") == f"Bearer {SECRET}"
    assert SECRET not in seen[0].data.decode("utf-8")


# --- request shape ----------------------------------------------------------


def test_body_matches_the_documented_contract():
    body = JevClient(model="jev-1.13", dry_run=True).build_body("S", QUESTIONS)

    assert sorted(body) == ["model", "questions", "state"]
    assert body["model"] == "jev-1.13"
    assert body["state"] == "S"


def test_dry_run_sends_nothing_and_needs_no_key(monkeypatch):
    monkeypatch.delenv(OFFICIAL_KEY_VAR, raising=False)
    calls = []
    recorded = []
    client = JevClient(
        dry_run=True,
        opener=_opener({}, record=calls),
        recorder=recorded.append,
    )

    response = client.ask("S", QUESTIONS)

    assert calls == []
    assert client.calls == 0
    assert response.error == "dry-run"
    assert recorded and sorted(recorded[0]) == ["model", "questions", "state"]


# --- answer location --------------------------------------------------------


@pytest.mark.parametrize("wrapper", [None, "answers", "results", "questions", "output", "data"])
def test_answers_found_at_root_or_under_any_wrapper(wrapper):
    inner = {"p": {"noul": 0.5}}
    payload = inner if wrapper is None else {wrapper: inner}

    found, key = find_answers(payload, {"p": QUESTIONS["p"]})

    assert found == inner
    assert key == wrapper


def test_unrecognisable_response_yields_no_answers():
    found, key = find_answers({"something": "else"}, {"p": QUESTIONS["p"]})

    assert found == {}
    assert key is None


def test_wrapper_key_is_recorded_on_the_response():
    client = JevClient(key=SECRET, opener=_opener({"results": {"p": {"noul": 0.7}}}))

    response = client.ask("S", {"p": QUESTIONS["p"]})

    assert response.wrapper_key == "results"
    assert response.noul("p") == 0.7


# --- answer parsing ---------------------------------------------------------


def test_each_answer_type_parses():
    parsed, missing, malformed = parse_answers(
        {
            "p": {"noul": 0.42},
            "c": {"choice": "a", "confidence": 0.8, "probabilities": {"a": 0.8, "b": 0.2}},
            "s": {"score": 2, "confidence": 0.6},
        },
        QUESTIONS,
    )

    assert isinstance(parsed["p"], NoulAnswer) and parsed["p"].p == 0.42
    assert isinstance(parsed["c"], ChoiceAnswer) and parsed["c"].probabilities == {
        "a": 0.8,
        "b": 0.2,
    }
    assert isinstance(parsed["s"], ScoreAnswer) and parsed["s"].score == 2
    assert missing == () and malformed == ()


def test_absent_answers_are_missing_not_malformed():
    _, missing, malformed = parse_answers({"p": {"noul": 0.1}}, QUESTIONS)

    assert set(missing) == {"c", "s"}
    assert malformed == ()


@pytest.mark.parametrize(
    "bad",
    [
        {"noul": 1.4},
        {"noul": "high"},
        {"noul": None},
        {"noul": True},
        {},
        "not a mapping",
    ],
)
def test_unusable_noul_is_malformed(bad):
    _, _, malformed = parse_answers({"p": bad}, {"p": QUESTIONS["p"]})

    assert malformed == ("p",)


def test_choice_outside_the_menu_is_malformed():
    _, _, malformed = parse_answers({"c": {"choice": "zzz"}}, {"c": QUESTIONS["c"]})

    assert malformed == ("c",)


def test_score_outside_the_scale_is_malformed():
    _, _, malformed = parse_answers({"s": {"score": 9}}, {"s": QUESTIONS["s"]})

    assert malformed == ("s",)


def test_probability_just_outside_range_is_clamped_not_rejected():
    parsed, _, malformed = parse_answers({"p": {"noul": 1.0000000001}}, {"p": QUESTIONS["p"]})

    assert malformed == ()
    assert parsed["p"].p == 1.0


# --- failure handling -------------------------------------------------------


def test_retries_on_throttling_then_succeeds():
    attempts = {"n": 0}

    def opener(request, timeout):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many", {}, None)
        return _Response({"p": {"noul": 0.9}})

    client = JevClient(key=SECRET, opener=opener, max_retries=2)
    with patch("stock_agent.jev.client.time.sleep"):
        response = client.ask("S", {"p": QUESTIONS["p"]})

    assert attempts["n"] == 3
    assert response.ok() and response.noul("p") == 0.9


def test_does_not_retry_on_a_client_error():
    attempts = {"n": 0}

    def opener(request, timeout):
        attempts["n"] += 1
        raise urllib.error.HTTPError(request.full_url, 400, "Bad", {}, None)

    response = JevClient(key=SECRET, opener=opener, max_retries=3).ask("S", {"p": QUESTIONS["p"]})

    assert attempts["n"] == 1
    assert response.ok() is False
    assert "400" in response.error


def test_timeout_is_retried_then_reported_not_raised():
    """A read timeout raises TimeoutError, which is not a URLError subclass."""

    def opener(request, timeout):
        raise TimeoutError("read timed out")

    with patch("stock_agent.jev.client.time.sleep"):
        response = JevClient(key=SECRET, opener=opener, max_retries=1).ask(
            "S", {"p": QUESTIONS["p"]}
        )

    assert response.ok() is False
    assert "TimeoutError" in response.error
    assert response.attempts == 2


def test_missing_key_degrades_rather_than_raising(monkeypatch, tmp_path):
    monkeypatch.delenv(OFFICIAL_KEY_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    client = JevClient(opener=_opener({}))
    with patch("stock_agent.jev.client.load_key", side_effect=RuntimeError("no key")):
        response = client.ask("S", QUESTIONS)

    assert response.ok() is False
    assert "no key" in response.error


def test_non_json_body_is_reported():
    class Broken(_Response):
        def read(self):
            return b"<html>nope</html>"

    response = JevClient(key=SECRET, opener=lambda r, timeout: Broken({})).ask(
        "S", {"p": QUESTIONS["p"]}
    )

    assert response.ok() is False


def test_response_without_recognisable_answers_is_an_error():
    response = JevClient(key=SECRET, opener=_opener({"unrelated": 1})).ask(
        "S", {"p": QUESTIONS["p"]}
    )

    assert response.ok() is False
    assert "no recognisable answers" in response.error


def test_usage_is_captured_when_present():
    client = JevClient(
        key=SECRET, opener=_opener({"answers": {"p": {"noul": 0.3}}, "usage": {"tokens": 42}})
    )

    response = client.ask("S", {"p": QUESTIONS["p"]})

    assert response.usage == {"tokens": 42}


# --- question construction --------------------------------------------------


def test_question_identifiers_round_trip():
    assert tool_for_qid(usefulness_qid("pattern.rsi_divergence")) == "pattern.rsi_divergence"


def test_non_usefulness_identifier_rejected():
    with pytest.raises(ValueError, match="not a usefulness"):
        tool_for_qid(STOP_ENOUGH_QID)


def test_one_batched_request_covers_every_candidate_plus_stopping():
    specs = [_spec("a.one"), _spec("b.two"), _spec("c.three")]

    questions = build_question_set(specs, "an objective")

    # Three usefulness and three best-next, plus enough + conflict +
    # conviction, plus the two halves of the order-balanced shadow pair.
    assert len(questions) == 3 + 3 + 3 + 2
    for spec in specs:
        assert usefulness_qid(spec.name) in questions
        assert best_next_qid(spec.name) in questions


def test_best_next_identifiers_round_trip_and_do_not_collide():
    name = "pattern.rsi_divergence"

    assert tool_for_best_next_qid(best_next_qid(name)) == name
    # The mock arms select their questions by prefix, so an overlap would
    # silently make one question answer the other.
    assert not best_next_qid(name).startswith("useful__")
    assert not usefulness_qid(name).startswith("best__")
    with pytest.raises(ValueError, match="not a best-next"):
        tool_for_best_next_qid(usefulness_qid(name))


def test_best_next_is_comparative_where_usefulness_is_absolute():
    spec = _spec("a.one")

    absolute = usefulness_question(spec, "obj")["criteria"]["true"]
    comparative = best_next_question(spec, "obj")["criteria"]["true"]

    # The absolute question is satisfiable by every candidate at once, which
    # is why it could not produce a ranking; the comparative one is not.
    assert "not already implied" in absolute
    assert "No other analysis" in comparative


def test_shadow_choice_asks_both_option_orders():
    specs = [_spec("a.one"), _spec("b.two")]

    questions = build_question_set(specs, "obj")
    forward = list(questions["select_fwd"]["criteria"])
    reverse = list(questions["select_rev"]["criteria"])

    # The model favours whichever option comes first, so the pair exists to
    # measure that rather than be fooled by it.
    assert forward == list(reversed(reverse))


def test_shadow_choice_omitted_for_a_single_candidate():
    questions = build_question_set([_spec("only.one")], "obj")

    assert "select_fwd" not in questions


def test_order_bias_averaging_matches_the_reference_rule():
    averaged = average_choice_probabilities({"a": 0.8, "b": 0.2}, {"a": 0.4, "b": 0.6})

    assert averaged == {"a": pytest.approx(0.6), "b": pytest.approx(0.4)}


def test_averaging_needs_both_orders():
    assert average_choice_probabilities({"a": 1.0}, None) == {}
    assert average_choice_probabilities(None, {"a": 1.0}) == {}


# --- facts established against the live endpoint ----------------------------


def test_model_pin_carries_the_patch_segment():
    """Verified live: "jev-1.13" is rejected with HTTP 400, "jev-1.13.0" works.

    The behaviours this agent is designed around were measured on this model,
    so the pin is load-bearing for reproducibility, not cosmetic.
    """
    from stock_agent.config import DEFAULT_MODEL

    assert DEFAULT_MODEL == "jev-1.13.0"
    assert JevClient(dry_run=True).model == "jev-1.13.0"


def test_served_model_is_captured_from_the_response():
    """The live response carries a root-level model field.

    A benchmark has to be keyed on what actually served the request, not on
    what was asked for.
    """
    client = JevClient(
        key=SECRET, opener=_opener({"answers": {"p": {"noul": 0.5}}, "model": "jev-1.13.0"})
    )

    response = client.ask("S", {"p": QUESTIONS["p"]})

    assert response.model_served == "jev-1.13.0"


def test_live_response_envelope_parses():
    """The exact shape returned by the live endpoint, as observed."""
    live = {
        "answers": {"probe": {"noul": 0.98}},
        "model": "jev-1.13.0",
        "usage": {"input_tokens": 293, "output_tokens": 20},
    }
    client = JevClient(key=SECRET, opener=_opener(live))

    response = client.ask("INDEX: S&P 500", {"probe": QUESTIONS["p"]})

    assert response.ok()
    assert response.wrapper_key == "answers"
    assert response.usage == {"input_tokens": 293, "output_tokens": 20}
    assert response.model_served == "jev-1.13.0"
