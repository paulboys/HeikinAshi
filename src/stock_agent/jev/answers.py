"""Typed answers from the decision model.

Three answer shapes are returned, matching the three question types:

* ``noul``   -> ``{"noul": probability}``
* ``choice`` -> ``{"choice": key, "confidence": f, "probabilities": {...}}``
* ``score``  -> ``{"score": int, "confidence": f}``

Parsing is total: an answer that is absent, or present but the wrong shape,
is recorded as such rather than raising. A decision made on fewer answers is
recoverable; an exception in the middle of a run is not.

Public API:
    NoulAnswer, ChoiceAnswer, ScoreAnswer, Answer, JevResponse
    parse_answers(answer_map, questions) -> tuple[dict, tuple, tuple]
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "Answer",
    "ChoiceAnswer",
    "JevResponse",
    "NoulAnswer",
    "ScoreAnswer",
    "parse_answers",
]

# Probabilities occasionally arrive a hair outside [0, 1] through floating
# point; clamp that rather than discarding an otherwise good answer.
_TOLERANCE = 1e-6


@dataclass(frozen=True)
class NoulAnswer:
    """A probability that some proposition holds.

    Attributes:
        qid: Question identifier.
        p: Probability in [0, 1].
        raw: The answer exactly as received.
    """

    qid: str
    p: float
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ChoiceAnswer:
    """A selection among named options.

    Attributes:
        qid: Question identifier.
        choice: The selected option key.
        confidence: Reported confidence, when present.
        probabilities: Per-option probabilities, when present. These are what
            make order-bias correction possible.
        raw: The answer exactly as received.
    """

    qid: str
    choice: str
    confidence: float | None
    probabilities: Mapping[str, float] | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ScoreAnswer:
    """An ordinal rating.

    Attributes:
        qid: Question identifier.
        score: The selected level.
        confidence: Reported confidence, when present.
        raw: The answer exactly as received.
    """

    qid: str
    score: int
    confidence: float | None
    raw: Mapping[str, Any]


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer


@dataclass(frozen=True)
class JevResponse:
    """One round-trip to the decision model.

    Attributes:
        answers: Successfully parsed answers, keyed by question identifier.
        missing: Questions asked but not answered.
        malformed: Questions answered in an unusable shape.
        raw: The decoded body, for the trace.
        latency_s: Wall-clock cost of the request.
        usage: Reported token or cost accounting, when present.
        endpoint: Endpoint used.
        model: Model requested.
        model_served: Model the response reports having used, when given.
            This, not the requested name, is what a benchmark is keyed on.
        attempts: Attempts made, including the first.
        http_status: Final HTTP status, when one was seen.
        wrapper_key: Where the answer map was found; None means the root.
        error: What went wrong, when something did.
    """

    answers: Mapping[str, Answer]
    missing: tuple[str, ...]
    malformed: tuple[str, ...]
    raw: Mapping[str, Any] | None
    latency_s: float
    usage: Mapping[str, Any] | None
    endpoint: str
    model: str
    attempts: int
    http_status: int | None
    wrapper_key: str | None
    error: str | None
    model_served: str | None = None

    def ok(self) -> bool:
        """Report whether the response carries usable answers.

        Returns:
            True when at least one answer parsed and no transport error
            occurred.
        """
        return self.error is None and bool(self.answers)

    def noul(self, qid: str) -> float | None:
        """Return a noul probability.

        Args:
            qid: Question identifier.

        Returns:
            The probability, or None when absent or of another type.
        """
        answer = self.answers.get(qid)
        return answer.p if isinstance(answer, NoulAnswer) else None

    def choice(self, qid: str) -> ChoiceAnswer | None:
        """Return a choice answer.

        Args:
            qid: Question identifier.

        Returns:
            The answer, or None when absent or of another type.
        """
        answer = self.answers.get(qid)
        return answer if isinstance(answer, ChoiceAnswer) else None

    def score(self, qid: str) -> ScoreAnswer | None:
        """Return a score answer.

        Args:
            qid: Question identifier.

        Returns:
            The answer, or None when absent or of another type.
        """
        answer = self.answers.get(qid)
        return answer if isinstance(answer, ScoreAnswer) else None


def _as_probability(value: object) -> float | None:
    """Coerce a value to a probability in [0, 1].

    Args:
        value: Raw value from the response.

    Returns:
        The probability, or None when it is not a number in range.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number < -_TOLERANCE or number > 1.0 + _TOLERANCE:
        return None
    return min(1.0, max(0.0, number))


def _as_confidence(raw: Mapping[str, Any]) -> float | None:
    """Read an optional confidence field.

    Args:
        raw: The answer mapping.

    Returns:
        The confidence, or None when absent or unusable.
    """
    return _as_probability(raw.get("confidence"))


def _probabilities(raw: Mapping[str, Any]) -> Mapping[str, float] | None:
    """Read an optional per-option probability map.

    Args:
        raw: The answer mapping.

    Returns:
        The map with numeric values only, or None when absent or empty.
    """
    found = raw.get("probabilities")
    if not isinstance(found, Mapping):
        return None
    cleaned = {
        str(k): float(v)
        for k, v in found.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    return cleaned or None


def _parse_one(
    qid: str,
    raw: object,
    question: Mapping[str, Any],
) -> Answer | None:
    """Parse one answer against the question that produced it.

    Args:
        qid: Question identifier.
        raw: The raw answer.
        question: The question definition, which supplies the expected type
            and, for a choice, the permitted option keys.

    Returns:
        The typed answer, or None when the shape is unusable.
    """
    if not isinstance(raw, Mapping):
        return None
    kind = question.get("type")

    if kind == "noul":
        probability = _as_probability(raw.get("noul"))
        return None if probability is None else NoulAnswer(qid, probability, raw)

    if kind == "choice":
        selected = raw.get("choice")
        if not isinstance(selected, str):
            return None
        criteria = question.get("criteria")
        # An option outside the menu is unusable; the policy would have no
        # tool to map it onto.
        if isinstance(criteria, Mapping) and selected not in criteria:
            return None
        return ChoiceAnswer(qid, selected, _as_confidence(raw), _probabilities(raw), raw)

    if kind == "score":
        value = raw.get("score")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        criteria = question.get("criteria")
        index = int(value)
        if isinstance(criteria, (list, tuple)) and not 0 <= index < len(criteria):
            return None
        return ScoreAnswer(qid, index, _as_confidence(raw), raw)

    return None


def parse_answers(
    answer_map: Mapping[str, Any],
    questions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Answer], tuple[str, ...], tuple[str, ...]]:
    """Parse every answer, separating the unusable from the absent.

    Args:
        answer_map: Per-question answers from the response.
        questions: The questions that were asked.

    Returns:
        The parsed answers, the identifiers that went unanswered, and the
        identifiers answered in an unusable shape.
    """
    parsed: dict[str, Answer] = {}
    missing: list[str] = []
    malformed: list[str] = []

    for qid, question in questions.items():
        if qid not in answer_map:
            missing.append(qid)
            continue
        answer = _parse_one(qid, answer_map[qid], question)
        if answer is None:
            malformed.append(qid)
        else:
            parsed[qid] = answer

    return parsed, tuple(missing), tuple(malformed)
