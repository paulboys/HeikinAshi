"""What the agent knows, and the compact view of it the decision model sees.

The state is deliberately three-tiered:

* ``frames`` and ``artifacts`` hold raw pandas objects. They never leave
  Python, are never serialised, and never reach the decision model.
* ``observations`` hold JSON-safe scalars plus a one-line rendering. This is
  the only tier that can be sent anywhere.
* :meth:`AnalysisState.to_jev_state` renders those observations as the plain
  text the API takes as its ``state`` field.

The split matters because the decision model is asked to choose among
analyses, not to read data. Sending a price series would be expensive, slow
and would invite it to do arithmetic that Python does better.

Public API:
    Observation, ProvenanceRecord, StepRecord, AnalysisState
    state_hash(state: AnalysisState) -> str
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "AnalysisState",
    "Observation",
    "ProvenanceRecord",
    "StepRecord",
    "state_hash",
]

JsonValue = bool | int | float | str | None | list[Any] | dict[str, Any]

# Floats are rounded before hashing so that a 1e-15 difference between
# platforms cannot change the hash -- or, worse, the prompt text.
_HASH_PRECISION = 6


@dataclass(frozen=True)
class Observation:
    """One measured fact produced by a tool.

    Attributes:
        key: Stable identifier, unique across all tools.
        value: JSON-safe measurement.
        display: One-line rendering; this is what the decision model reads.
        tool: Name of the tool that produced it.
        iteration: Iteration during which it was produced.
        caveat: Any qualification that must travel with the number, such as a
            label being fitted in hindsight.
    """

    key: str
    value: JsonValue
    display: str
    tool: str
    iteration: int
    caveat: str | None = None


@dataclass(frozen=True)
class ProvenanceRecord:
    """How and when an observation was produced.

    Attributes:
        tool: Producing tool.
        param_fingerprint: Hash of the parameters used, so that the same
            measurement at different settings does not count as satisfied.
        asof: As-of date in force, if any.
        iteration: Iteration during which it was produced.
    """

    tool: str
    param_fingerprint: str
    asof: str | None
    iteration: int


@dataclass(frozen=True)
class StepRecord:
    """One tool execution.

    Attributes:
        tool: Tool name.
        role: Why it ran -- selected, a prerequisite, or forced bootstrap.
        iteration: Iteration during which it ran.
        status: Outcome.
        duration_s: Wall-clock cost.
        error: Error text when the status is not ok.
    """

    tool: str
    role: str
    iteration: int
    status: str
    duration_s: float
    error: str | None = None


@dataclass
class AnalysisState:
    """Everything the agent knows about one analysis in progress.

    Attributes:
        ticker: Symbol under analysis.
        objective: What the analysis is for, interpolated into questions.
        asof: As-of date, or None for a live run.
        data_source: Where price data comes from. Tools that reach the network
            outside the price provider are withheld unless this is ``live``,
            so a synthetic or fixture run is genuinely offline.
        interval: Bar aggregation.
        created_at: UTC ISO timestamp of the run start.
        iteration: Current iteration.
        observations: Measured facts, keyed by observation key.
        provenance: How each observation was produced.
        history: Every tool execution, in order.
        frames: Raw price frames. Never serialised, never sent.
        artifacts: Raw intermediate objects. Never serialised, never sent.
    """

    ticker: str
    objective: str
    asof: date | None = None
    data_source: str = "live"
    interval: str = "1d"
    created_at: str = ""
    iteration: int = 0
    observations: dict[str, Observation] = field(default_factory=dict)
    provenance: dict[str, ProvenanceRecord] = field(default_factory=dict)
    history: list[StepRecord] = field(default_factory=list)
    frames: dict[str, Any] = field(default_factory=dict, repr=False)
    artifacts: dict[str, Any] = field(default_factory=dict, repr=False)

    # -- recording ---------------------------------------------------------

    def record(
        self,
        observations: dict[str, Observation],
        provenance: dict[str, ProvenanceRecord],
    ) -> None:
        """Merge a tool's output into the state.

        Args:
            observations: New observations, keyed by observation key.
            provenance: Matching provenance records.
        """
        self.observations.update(observations)
        self.provenance.update(provenance)

    def has(self, *keys: str) -> bool:
        """Report whether every named observation exists.

        Args:
            *keys: Observation keys to check.

        Returns:
            True when all are present.
        """
        return all(k in self.observations for k in keys)

    def value(self, key: str, default: JsonValue = None) -> JsonValue:
        """Return an observation's value.

        Args:
            key: Observation key.
            default: Value returned when the key is absent.

        Returns:
            The measured value, or the default.
        """
        obs = self.observations.get(key)
        return default if obs is None else obs.value

    def tools_run(self) -> list[str]:
        """Return the distinct tools that have executed successfully.

        Returns:
            Tool names in first-execution order.
        """
        seen: list[str] = []
        for step in self.history:
            if step.status == "ok" and step.tool not in seen:
                seen.append(step.tool)
        return seen

    def tool_call_count(self, tool: str) -> int:
        """Count executions of one tool, successful or not.

        Args:
            tool: Tool name.

        Returns:
            Number of executions recorded.
        """
        return sum(1 for step in self.history if step.tool == tool)

    # -- the view the decision model receives ------------------------------

    def to_jev_state(
        self,
        not_yet: list[str],
        unavailable: list[str],
    ) -> str:
        """Render the compact text sent as the API's ``state`` field.

        The two trailing sections are load-bearing rather than cosmetic.
        Questions are evaluated in isolation from one another, so a per-tool
        question has no other way to learn what the alternatives are, or that
        some analyses cannot be run at all.

        Args:
            not_yet: Human titles of analyses still available.
            unavailable: Human titles of analyses with no implementation.

        Returns:
            Deterministic plain text.
        """
        asof_text = "live" if self.asof is None else f"as of {self.asof.isoformat()}"
        bars = self.value("ohlc.n_bars", "unknown")
        lines = [
            f"TICKER: {self.ticker}   WINDOW: {asof_text}   "
            f"INTERVAL: {self.interval}   BARS: {bars}",
            f"OBJECTIVE: {self.objective}",
            "",
        ]

        done = sorted(self.observations.values(), key=lambda o: (o.tool, o.key))
        if any(o.display for o in done):
            by_tool: dict[str, list[Observation]] = {}
            for obs in done:
                if obs.display:
                    by_tool.setdefault(obs.tool, []).append(obs)
            lines.append(f"MEASURED SO FAR ({len(by_tool)} analyses run):")
            for tool in sorted(by_tool):
                rendered = "; ".join(o.display for o in by_tool[tool])
                caveats = [o.caveat for o in by_tool[tool] if o.caveat]
                if caveats:
                    rendered += f" [{caveats[0]}]"
                lines.append(f"[{tool}] {rendered}")
        else:
            lines.append("MEASURED SO FAR: nothing yet.")
        lines.append("")

        lines.append(
            "NOT YET MEASURED: " + (", ".join(not_yet) if not_yet else "nothing remaining")
        )
        if unavailable:
            lines.append("UNAVAILABLE IN THIS SYSTEM: " + ", ".join(unavailable))
        return "\n".join(lines)


def _roundable(value: JsonValue) -> JsonValue:
    """Round floats recursively so hashes are stable across platforms.

    Args:
        value: Any JSON-safe value.

    Returns:
        The value with every float rounded.
    """
    if isinstance(value, float):
        return round(value, _HASH_PRECISION)
    if isinstance(value, list):
        return [_roundable(v) for v in value]
    if isinstance(value, dict):
        return {k: _roundable(v) for k, v in sorted(value.items())}
    return value


def state_hash(state: AnalysisState) -> str:
    """Fingerprint what the agent knows, ignoring when it learned it.

    Deliberately excludes iteration, timestamps and rendered text, so two
    runs that reach identical knowledge by different routes hash identically.
    That is what makes the hash usable as a loop guard and a cache key.

    Args:
        state: State to fingerprint.

    Returns:
        A 16-character hex digest.
    """
    canonical = {
        "ticker": state.ticker,
        "objective": state.objective,
        "asof": None if state.asof is None else state.asof.isoformat(),
        "interval": state.interval,
        "observations": {
            key: {"value": _roundable(obs.value), "tool": obs.tool}
            for key, obs in sorted(state.observations.items())
        },
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# Coarse on purpose. These are meant to be what a glance at the chart would
# tell you -- that volume looks unusual, that the range has widened -- not the
# measurements themselves. A state carrying the exact figure an analysis
# produces would make that analysis genuinely redundant, and a decision model
# would be right to decline it. Rounding is the line between a hint and an
# answer.
_HINT_PRECISION = 1


def _hint(value: float) -> float:
    """Round a ratio to a coarse hint.

    Args:
        value: The precise ratio.

    Returns:
        The ratio rounded, so it signals rather than settles.
    """
    return round(value, _HINT_PRECISION)


def summarize_frame(df: pd.DataFrame) -> dict[str, JsonValue]:
    """Reduce a price frame to the scalars worth carrying in the state.

    The decision model sees only this. Until these hints were added it saw a
    last close, a median volume, a twenty-bar range and a sixty-three-bar
    return -- in which a planted sixfold volume spike over five bars left no
    trace at all, because a sixty-bar median absorbs it. Asked whether volume
    was worth analysing, the model answered identically on a series with a
    spike and one without, which was the correct answer to the question it
    had been given.

    Args:
        df: Price history.

    Returns:
        A JSON-safe mapping; empty when the frame holds no rows.
    """
    if df is None or df.empty:
        return {}
    close = df["Close"].dropna()
    if close.empty:
        return {}
    out: dict[str, JsonValue] = {
        "n_bars": int(len(df)),
        "last_close": float(close.iloc[-1]),
        "first_date": str(pd.Timestamp(df.index[0]).date()),
        "last_date": str(pd.Timestamp(df.index[-1]).date()),
    }
    if len(close) > 1:
        window = min(63, len(close) - 1)
        out["return_63"] = float(close.iloc[-1] / close.iloc[-1 - window] - 1.0)
        span = close.iloc[-min(20, len(close)) :]
        out["range_low"] = float(span.min())
        out["range_high"] = float(span.max())

        # Where the last close sits in its recent range. A crude stand-in for
        # whether momentum is stretched, available without computing RSI.
        width = float(span.max() - span.min())
        if width > 0:
            out["range_position"] = _hint(float(close.iloc[-1] - span.min()) / width)

    if len(close) > 6:
        out["return_5"] = _hint(float(close.iloc[-1] / close.iloc[-6] - 1.0) * 100.0)
        recent = close.tail(11).to_numpy(dtype=float)
        out["up_days_10"] = int((np.diff(recent) > 0).sum())

    if len(close) > 21:
        out["drawdown_pct"] = _hint(float(close.iloc[-1] / close.cummax().iloc[-1] - 1.0) * 100.0)

    # Realised volatility recently against the whole window. Signals that the
    # character of the series has changed, which is the reason to reach for a
    # volatility analysis rather than a substitute for one.
    if len(close) > 42:
        values = close.to_numpy(dtype=float)
        returns = np.diff(np.log(values))
        full = float(np.std(returns, ddof=1))
        if full > 0:
            recent_vol = float(np.std(returns[-20:], ddof=1))
            out["vol_ratio_20"] = _hint(recent_vol / full)

    if "Volume" in df:
        volume = df["Volume"].dropna()
        if not volume.empty:
            out["median_volume"] = float(volume.tail(60).median())
        # The surge a sixty-bar median hides. Five bars against the sixty
        # before them, which is the comparison that makes a spike visible.
        if len(volume) > 65:
            baseline = float(volume.iloc[-65:-5].median())
            if baseline > 0:
                out["volume_ratio_5"] = _hint(float(volume.tail(5).mean()) / baseline)
    return out
