"""The append-only record of every decision the agent made.

The project's research question is whether the decision model routes well,
not whether its final answer reads plausibly. That can only be answered from
a record of what was asked, what came back, and what the policy did with it --
so the trace captures the rendered questions verbatim, the raw response, the
probabilities, and the arithmetic behind each branch.

One JSONL file per run, three record types: ``run_start``, one ``iteration``
each round, and ``run_end``.

Public API:
    TraceWriter, read_trace(path) -> list[dict]
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TextIO

__all__ = ["SCHEMA_VERSION", "TraceWriter", "read_trace"]

SCHEMA_VERSION = 1


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        Timestamp with a trailing Z.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(payload: object) -> str:
    """Hash a JSON-serialisable payload.

    Args:
        payload: Value to hash.

    Returns:
        A 16-character hex digest.
    """
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class TraceWriter:
    """Writes one run's decision trace."""

    def __init__(self, path: Path | None, run_id: str | None = None) -> None:
        """Create a writer.

        Args:
            path: Destination file; None discards records, which keeps tests
                and dry runs from writing to disk.
            run_id: Identifier for this run; generated when omitted.
        """
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.path = path
        self.records: list[dict[str, Any]] = []
        self._handle: TextIO | None = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = path.open("w", encoding="utf-8")

    def _write(self, record: dict[str, Any]) -> None:
        """Append one record.

        Args:
            record: The record to write.
        """
        record["run_id"] = self.run_id
        self.records.append(record)
        if self._handle is not None:
            self._handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._handle.flush()

    def run_start(
        self,
        ticker: str,
        objective: str,
        asof: str | None,
        config: Mapping[str, Any],
        tools: Sequence[Mapping[str, Any]],
        absent: Sequence[Mapping[str, Any]],
        provider: str,
        mode: str,
    ) -> None:
        """Record the run's starting conditions.

        Args:
            ticker: Symbol under analysis.
            objective: What the analysis is for.
            asof: As-of date, or None for live.
            config: Every tunable setting in force.
            tools: Registry entries available.
            absent: Analyses this system cannot perform, with reasons.
            provider: Where price data came from.
            mode: How the decision model was reached.
        """
        self._write(
            {
                "record": "run_start",
                "schema_version": SCHEMA_VERSION,
                "ts": _now(),
                "ticker": ticker,
                "objective": objective,
                "asof": asof,
                "live": asof is None,
                "provider": provider,
                "mode": mode,
                "config": dict(config),
                "registry": {"tools": list(tools), "absent": list(absent)},
                "env": {
                    "python": platform.python_version(),
                    "platform": sys.platform,
                },
            }
        )

    def iteration(
        self,
        iteration: int,
        state_hash_before: str,
        state_hash_after: str,
        state_text: str,
        candidates: Sequence[str],
        excluded: Sequence[tuple[str, str]],
        questions: Mapping[str, Mapping[str, Any]] | None,
        response: Mapping[str, Any] | None,
        parsed: Mapping[str, Any],
        shadow: Mapping[str, Any] | None,
        decision: Mapping[str, Any],
        tool_calls: Sequence[Mapping[str, Any]],
        budget: Mapping[str, Any],
    ) -> None:
        """Record one decision round.

        The record is written after the round's tools have run, so each is
        self-contained: a reader never has to look ahead to learn what a
        decision led to.

        Args:
            iteration: Round number, from zero.
            state_hash_before: Knowledge fingerprint before the round.
            state_hash_after: Knowledge fingerprint after it.
            state_text: Exactly what the decision model was shown.
            candidates: Tools offered.
            excluded: Tools withheld, each with its reason.
            questions: The rendered questions, verbatim.
            response: The decoded response and its metadata.
            parsed: Probabilities extracted from the response.
            shadow: The order-balanced choice comparison, when asked.
            decision: The policy's branch and arithmetic.
            tool_calls: What ran, in order.
            budget: Consumption after the round.
        """
        self._write(
            {
                "record": "iteration",
                "ts": _now(),
                "iteration": iteration,
                "state_hash_before": state_hash_before,
                "state_hash_after": state_hash_after,
                "state_text": state_text,
                "state_text_sha256": _sha256(state_text),
                "candidates": list(candidates),
                "candidates_excluded": [
                    {"tool": name, "reason": reason} for name, reason in excluded
                ],
                "jev_request": None
                if questions is None
                else {
                    "n_questions": len(questions),
                    "body_sha256": _sha256({"state": state_text, "questions": questions}),
                    "questions": dict(questions),
                },
                "jev_response": dict(response) if response else None,
                "parsed": dict(parsed),
                "shadow_choice": dict(shadow) if shadow else None,
                "decision": dict(decision),
                "tool_calls": [dict(c) for c in tool_calls],
                "budget_after": dict(budget),
            }
        )

    def run_end(
        self,
        exit_reason: str,
        exit_detail: str,
        partial: bool,
        tools_run: Sequence[str],
        observations: Mapping[str, Any],
        caveats: Sequence[str],
        budget: Mapping[str, Any],
        final_state_hash: str,
    ) -> None:
        """Record how the run finished.

        Args:
            exit_reason: Short identifier for why it stopped.
            exit_detail: Human explanation.
            partial: Whether the analysis was cut short.
            tools_run: Analyses that produced measurements.
            observations: Everything measured.
            caveats: Qualifications the reader must carry.
            budget: Final consumption.
            final_state_hash: Knowledge fingerprint at the end.
        """
        self._write(
            {
                "record": "run_end",
                "ts": _now(),
                "exit_reason": exit_reason,
                "exit_detail": exit_detail,
                "partial": partial,
                "tools_run": list(tools_run),
                "final_observations": dict(observations),
                "caveats": list(caveats),
                "totals": dict(budget),
                "final_state_hash": final_state_hash,
            }
        )

    def close(self) -> None:
        """Close the underlying file, if any."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> TraceWriter:
        """Enter a context manager.

        Returns:
            This writer.
        """
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        """Close the file on exit.

        Args:
            *exc: Exception information, unused.

        Returns:
            False, so exceptions propagate.
        """
        self.close()
        return False


def read_trace(path: Path) -> list[dict[str, Any]]:
    """Read a trace back.

    Args:
        path: Trace file.

    Returns:
        Every record, in order.
    """
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
