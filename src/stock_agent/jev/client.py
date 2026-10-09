"""Transport for the JEV decision model.

Modelled directly on the working implementation in ``latin-mqm-judges``
(``jev_probe.call_jev`` / ``load_key`` / ``find_answers``), with three
additions: retries, a dry-run mode, and typed answers.

Two conventions are carried over deliberately:

* **Keys are bound to endpoints.** The official key is only ever sent to the
  official host, and the legacy reseller key only to a non-official one, so a
  misconfigured endpoint cannot exfiltrate a credential.
* **Answers may be nested.** The response has been seen with the per-question
  map at the root or under any of five wrapper keys, so all are probed and
  the one that matched is recorded.

Public API:
    OFFICIAL_ENDPOINT, OFFICIAL_KEY_VAR, LEGACY_KEY_VAR, RETRY_STATUS
    load_key(endpoint, env_path=None) -> str
    find_answers(response, questions) -> tuple[dict, str | None]
    JevClient
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from stock_agent.jev.answers import JevResponse, parse_answers

__all__ = [
    "LEGACY_KEY_VAR",
    "OFFICIAL_ENDPOINT",
    "OFFICIAL_KEY_VAR",
    "RETRY_STATUS",
    "JevClient",
    "find_answers",
    "load_key",
]

OFFICIAL_ENDPOINT = "https://api.typesafe.ai/v1/systemone"

# A key is valid only for the host it was issued for. Keeping the mapping
# explicit means an --endpoint override cannot send the official key
# somewhere else.
OFFICIAL_KEY_VAR = "TYPE_SET_API_KEY"
LEGACY_KEY_VAR = "JEV_API_KEY"

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

# Wrapper keys the per-question answer map has been observed under.
_WRAPPERS = ("answers", "results", "questions", "output", "data")


def _repo_root(start: Path) -> Path | None:
    """Find the nearest ancestor directory holding a pyproject.toml.

    Args:
        start: Directory to search upward from.

    Returns:
        The repository root, or None when no marker is found.
    """
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def load_key(endpoint: str = OFFICIAL_ENDPOINT, env_path: Path | None = None) -> str:
    """Read the API key for an endpoint from the environment or a .env file.

    Args:
        endpoint: The endpoint the key will be sent to, which selects which
            variable is read.
        env_path: Explicit .env location; otherwise the repository root's.

    Returns:
        The key.

    Raises:
        RuntimeError: If no key is configured for that endpoint.
    """
    var = OFFICIAL_KEY_VAR if endpoint == OFFICIAL_ENDPOINT else LEGACY_KEY_VAR

    from_env = os.environ.get(var, "").strip()
    if from_env:
        return from_env

    path = env_path
    if path is None:
        root = _repo_root(Path(__file__).resolve().parent)
        path = None if root is None else root / ".env"

    if path is not None and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if "=" not in stripped or stripped.startswith("#"):
                continue
            name, _, raw = stripped.partition("=")
            if name.strip() == var:
                value = raw.strip().strip("'\"`")
                if value:
                    return value

    raise RuntimeError(f"{var} not found in the environment or .env; it is required for {endpoint}")


def find_answers(
    response: Mapping[str, Any],
    questions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    """Locate the per-question answer map inside a response.

    Args:
        response: Decoded response body.
        questions: The questions that were asked, used to recognise the map.

    Returns:
        The answer map and the wrapper key it was found under, where ``None``
        means the root. An unrecognisable response yields an empty map.
    """
    if not isinstance(response, dict):
        return {}, None
    for key in _WRAPPERS:
        nested = response.get(key)
        if isinstance(nested, dict) and any(q in nested for q in questions):
            return nested, key
    if any(q in response for q in questions):
        return dict(response), None
    return {}, None


class JevClient:
    """Posts question sets to the decision model and returns typed answers."""

    def __init__(
        self,
        endpoint: str = OFFICIAL_ENDPOINT,
        model: str = "jev-1.13.0",
        timeout: float = 60.0,
        max_retries: int = 2,
        retry_backoff: float = 1.5,
        dry_run: bool = False,
        key: str | None = None,
        opener: Callable[..., Any] | None = None,
        recorder: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Create a client.

        Args:
            endpoint: Decision endpoint.
            model: Model identifier sent with each request.
            timeout: Per-attempt timeout in seconds.
            max_retries: Attempts beyond the first on a retryable failure.
            retry_backoff: Exponential backoff base between attempts.
            dry_run: Build and record request bodies without sending them.
            key: Explicit key; otherwise resolved lazily per endpoint.
            opener: ``urlopen``-compatible callable, for testing.
            recorder: Receives each request body, for dry runs and tracing.
        """
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = retry_backoff
        self.dry_run = dry_run
        self.calls = 0
        self._key = key
        self._opener = opener or urllib.request.urlopen
        self._recorder = recorder

    def __repr__(self) -> str:
        """Render the client without ever exposing the key.

        Returns:
            A short description.
        """
        state = "set" if self._key else "unset"
        return (
            f"JevClient(endpoint={self.endpoint!r}, model={self.model!r}, "
            f"key=<{state}>, dry_run={self.dry_run})"
        )

    def build_body(
        self,
        state: str,
        questions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Assemble the request body.

        Args:
            state: The compact textual state the questions are asked against.
            questions: Question identifier to question definition.

        Returns:
            The body, exactly as it will be sent.
        """
        return {"state": state, "model": self.model, "questions": dict(questions)}

    def ask(
        self,
        state: str,
        questions: Mapping[str, Mapping[str, Any]],
    ) -> JevResponse:
        """Ask a set of questions about a state.

        Every question is evaluated independently against the same state, and
        latency does not grow materially with the number asked, so sending
        many at once costs about the same as sending one.

        Args:
            state: The compact textual state.
            questions: Question identifier to question definition.

        Returns:
            A response carrying typed answers, or an error. Nothing raises:
            a failed decision must degrade the run, not crash it.
        """
        body = self.build_body(state, questions)
        if self._recorder is not None:
            self._recorder(body)

        if self.dry_run:
            # Deliberately never resolves the key, so a dry run works with no
            # credential configured at all.
            return JevResponse(
                answers={},
                missing=tuple(questions),
                malformed=(),
                raw=None,
                latency_s=0.0,
                usage=None,
                endpoint=self.endpoint,
                model=self.model,
                attempts=0,
                http_status=None,
                wrapper_key=None,
                error="dry-run",
            )

        try:
            key = self._key if self._key is not None else load_key(self.endpoint)
        except RuntimeError as exc:
            return JevResponse(
                answers={},
                missing=tuple(questions),
                malformed=(),
                raw=None,
                latency_s=0.0,
                usage=None,
                endpoint=self.endpoint,
                model=self.model,
                attempts=0,
                http_status=None,
                wrapper_key=None,
                error=str(exc),
            )

        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        started = time.perf_counter()
        last_error: str | None = None
        status: int | None = None
        attempts = 0

        for attempt in range(self.max_retries + 1):
            attempts = attempt + 1
            request = urllib.request.Request(
                self.endpoint,
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                self.calls += 1
                with self._opener(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", 200)
                    decoded = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                status = exc.code
                last_error = f"HTTPError: {exc.code}"
                if exc.code not in RETRY_STATUS:
                    return self._failure(questions, last_error, started, attempts, status)
            except OSError as exc:
                # OSError, not URLError: a read timeout raises TimeoutError,
                # which is not a URLError subclass, so catching only URLError
                # silently skips every timeout.
                last_error = f"{type(exc).__name__}: {str(exc)[:150]}"
            except (ValueError, json.JSONDecodeError) as exc:
                return self._failure(
                    questions,
                    f"{type(exc).__name__}: {str(exc)[:150]}",
                    started,
                    attempts,
                    status,
                )
            if attempt < self.max_retries:
                time.sleep(self.retry_backoff**attempt)
        else:
            return self._failure(questions, last_error, started, attempts, status)

        latency = time.perf_counter() - started
        answer_map, wrapper = find_answers(decoded, questions)
        if not answer_map:
            return self._failure(
                questions,
                "no recognisable answers in response",
                started,
                attempts,
                status,
                raw=decoded,
            )

        answers, missing, malformed = parse_answers(answer_map, questions)
        return JevResponse(
            answers=answers,
            missing=missing,
            malformed=malformed,
            raw=decoded,
            latency_s=round(latency, 4),
            usage=decoded.get("usage") if isinstance(decoded, dict) else None,
            endpoint=self.endpoint,
            model=self.model,
            attempts=attempts,
            http_status=status,
            wrapper_key=wrapper,
            error=None if answers else "every answer was missing or malformed",
            model_served=(
                str(decoded.get("model"))
                if isinstance(decoded, dict) and decoded.get("model")
                else None
            ),
        )

    def _failure(
        self,
        questions: Mapping[str, Mapping[str, Any]],
        error: str | None,
        started: float,
        attempts: int,
        status: int | None,
        raw: Mapping[str, Any] | None = None,
    ) -> JevResponse:
        """Build a response representing a failed request.

        Args:
            questions: Questions that went unanswered.
            error: What went wrong.
            started: Perf counter reading when the request began.
            attempts: Attempts made.
            status: HTTP status, if one was seen.
            raw: Decoded body, if one was received.

        Returns:
            A response carrying the error.
        """
        return JevResponse(
            answers={},
            missing=tuple(questions),
            malformed=(),
            raw=raw,
            latency_s=round(time.perf_counter() - started, 4),
            usage=None,
            endpoint=self.endpoint,
            model=self.model,
            attempts=attempts,
            http_status=status,
            wrapper_key=None,
            error=error or "request failed",
        )
