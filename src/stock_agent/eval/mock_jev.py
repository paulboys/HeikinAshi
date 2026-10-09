"""A stand-in for the decision model, for development and tests.

Deterministic by design: a mock that returned random probabilities would make
every loop test flaky and would hide exactly the branches worth checking.
Each strategy targets a specific part of the policy, so between them the
whole agent is exercisable with no API key and no network.

Strategies:
    ``oracle``      favours the tools a scenario expects -- the happy path
    ``uniform``     everything at 0.5 -- the indecision path
    ``adversarial`` one tool at 0.99 forever -- the repeat caps and termination
    ``stuck``       never sufficient -- the iteration cap
    ``malformed``   wrong shapes -- missing and malformed handling
    ``down``        raises -- the no-fallback path

Public API:
    MockJevClient, Strategy
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from stock_agent.jev.answers import JevResponse, parse_answers
from stock_agent.jev.questions import (
    CONVICTION_QID,
    SELECT_FWD_QID,
    SELECT_REV_QID,
    STOP_CONFLICT_QID,
    STOP_ENOUGH_QID,
    tool_for_qid,
)

__all__ = ["MockJevClient", "Strategy"]

Strategy = Literal["oracle", "uniform", "adversarial", "stuck", "malformed", "down"]

_USEFUL_PREFIX = "useful__"


class MockJevClient:
    """Serves scripted answers with the real response shape."""

    def __init__(
        self,
        strategy: Strategy = "oracle",
        preferred: Sequence[str] = (),
        model: str = "mock",
        enough_after: int = 3,
    ) -> None:
        """Create a mock client.

        Args:
            strategy: Which behaviour to serve.
            preferred: Tool names the oracle should favour, in order.
            model: Model name reported on each response.
            enough_after: Analyses the oracle runs before declaring the
                evidence sufficient.
        """
        self.strategy = strategy
        self.preferred = list(preferred)
        self.model = model
        self.enough_after = enough_after
        self.endpoint = "mock://systemone"
        self.calls = 0
        self.dry_run = False
        self.requests: list[dict[str, Any]] = []

    def __repr__(self) -> str:
        """Render the client.

        Returns:
            A short description.
        """
        return f"MockJevClient(strategy={self.strategy!r}, calls={self.calls})"

    def build_body(
        self,
        state: str,
        questions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Assemble a request body in the real shape.

        Args:
            state: The compact textual state.
            questions: Question identifier to definition.

        Returns:
            The body.
        """
        return {"state": state, "model": self.model, "questions": dict(questions)}

    def ask(
        self,
        state: str,
        questions: Mapping[str, Mapping[str, Any]],
    ) -> JevResponse:
        """Answer a question set.

        Args:
            state: The compact textual state.
            questions: Question identifier to definition.

        Returns:
            A response in the same shape the real client produces.
        """
        self.calls += 1
        self.requests.append(self.build_body(state, questions))

        if self.strategy == "down":
            return JevResponse(
                answers={},
                missing=tuple(questions),
                malformed=(),
                raw=None,
                latency_s=0.0,
                usage=None,
                endpoint=self.endpoint,
                model=self.model,
                attempts=1,
                http_status=503,
                wrapper_key=None,
                error="HTTPError: 503",
            )

        raw = self._answers(state, questions)
        parsed, missing, malformed = parse_answers(raw, questions)
        return JevResponse(
            answers=parsed,
            missing=missing,
            malformed=malformed,
            raw={"answers": raw},
            latency_s=0.24,
            usage={"mock": True},
            endpoint=self.endpoint,
            model=self.model,
            attempts=1,
            http_status=200,
            wrapper_key="answers",
            error=None if parsed else "every answer was missing or malformed",
        )

    def _answers(
        self,
        state: str,
        questions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Build the raw answer map for a strategy.

        Args:
            state: The compact textual state, used by the oracle to judge
                how much has been measured.
            questions: Question identifier to definition.

        Returns:
            The raw per-question answers.
        """
        tools = [q for q in questions if q.startswith(_USEFUL_PREFIX)]

        if self.strategy == "malformed":
            # Shapes the parser must reject rather than crash on.
            answers: dict[str, Any] = {q: {"noul": "very likely"} for q in tools}
            answers[STOP_ENOUGH_QID] = {"noul": 1.7}
            return answers

        measured = state.count("\n[")
        answers = {}

        # Only the absolute question: these strategies exist to exercise the
        # policy's branches, not to model comparative judgement. Leaving the
        # comparative questions unanswered routes them on the absolute map at
        # the absolute act threshold, which is what makes them controls.
        for qid in tools:
            answers[qid] = {"noul": self._usefulness(tool_for_qid(qid))}

        if self.strategy == "stuck":
            answers[STOP_ENOUGH_QID] = {"noul": 0.0}
        elif self.strategy == "uniform":
            answers[STOP_ENOUGH_QID] = {"noul": 0.5}
        else:
            answers[STOP_ENOUGH_QID] = {"noul": 0.95 if measured >= self.enough_after else 0.10}

        answers[STOP_CONFLICT_QID] = {"noul": 0.5 if self.strategy == "uniform" else 0.1}
        answers[CONVICTION_QID] = {"score": 3, "confidence": 0.6}

        for qid in (SELECT_FWD_QID, SELECT_REV_QID):
            if qid in questions:
                options = list(questions[qid].get("criteria", {}))
                if options:
                    # Deliberately picks the first option, reproducing the
                    # order bias the shadow pair exists to detect.
                    answers[qid] = {
                        "choice": options[0],
                        "confidence": 0.7,
                        "probabilities": {
                            name: (0.7 if i == 0 else 0.3 / max(1, len(options) - 1))
                            for i, name in enumerate(options)
                        },
                    }
        return answers

    def _usefulness(self, tool: str) -> float:
        """Score one tool under the current strategy.

        Args:
            tool: Tool name.

        Returns:
            A probability.
        """
        if self.strategy == "uniform":
            return 0.5
        if self.strategy == "adversarial":
            # Always the same tool, to prove the loop still terminates.
            return 0.99 if tool == (self.preferred[0] if self.preferred else tool) else 0.05
        if self.strategy == "stuck":
            return 0.9 if tool in self.preferred else 0.5
        if self.preferred:
            return 0.85 if tool in self.preferred else 0.15
        return 0.8
