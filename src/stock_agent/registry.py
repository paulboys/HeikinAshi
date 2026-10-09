"""The catalogue of analyses the agent may run.

The registry is what makes routing safe: the decision model is shown tool
names and one-line descriptions, never callables, and it chooses only from
the set Python has already judged applicable. Dependencies between analyses
are declared over *observation keys* rather than tool names, so the graph
describes what a tool needs rather than who happens to provide it.

Public API:
    ToolCost, ToolContext, ToolResult, ToolSpec, ToolRegistry
    param_fingerprint(tool: str, params: Mapping, asof) -> str
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from stock_agent.asof import OhlcFrame, OhlcRequest, PriceProvider, get_ohlc
from stock_agent.conditions import MISSING, Condition, evaluate
from stock_agent.state import AnalysisState, JsonValue, Observation, ProvenanceRecord

__all__ = [
    "ToolContext",
    "ToolCost",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "param_fingerprint",
]


def param_fingerprint(
    tool: str,
    params: Mapping[str, JsonValue],
    asof: date | None,
) -> str:
    """Fingerprint the settings a measurement was taken at.

    Two measurements count as the same only if they used the same parameters
    at the same as-of date, so RSI(14) never satisfies a request for RSI(21).

    Args:
        tool: Tool name.
        params: Parameters used.
        asof: As-of date in force.

    Returns:
        A 12-character hex digest.
    """
    payload = json.dumps(
        {
            "tool": tool,
            "params": dict(sorted(params.items())),
            "asof": None if asof is None else asof.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class ToolCost:
    """What running a tool costs.

    Attributes:
        est_seconds: Rough wall-clock cost, used to break ties cheaply first.
        network: Whether it reaches the network.
        network_calls: Expected outbound calls.
    """

    est_seconds: float = 0.01
    network: bool = False
    network_calls: int = 0

    @property
    def cost_class(self) -> Literal["low", "medium", "high"]:
        """Bucket the cost for policy decisions.

        Returns:
            The coarse cost band.
        """
        if self.est_seconds >= 2.0 or self.network_calls > 1:
            return "high"
        if self.network or self.est_seconds >= 0.25:
            return "medium"
        return "low"


@dataclass
class ToolContext:
    """What a tool is handed when it runs.

    Attributes:
        state: The analysis so far.
        provider: Source of price history.
        params: Parameters for this execution.
        interval: Bar aggregation.
        bars: Bars of history to request.
    """

    state: AnalysisState
    provider: PriceProvider
    params: Mapping[str, JsonValue] = field(default_factory=dict)
    interval: str = "1d"
    bars: int = 504

    def ohlc(self, ticker: str | None = None, bars: int | None = None) -> OhlcFrame:
        """Obtain price history through the chokepoint.

        Frames are memoised per run, so several tools analysing the same
        ticker share one fetch rather than each paying for their own.

        Args:
            ticker: Symbol to fetch; defaults to the ticker under analysis.
            bars: Bars wanted; defaults to the run's setting.

        Returns:
            The truncated frame.
        """
        symbol = ticker or self.state.ticker
        want = bars or self.bars
        cache_key = f"{symbol}|{self.interval}|{want}|{self.state.asof}"
        cached = self.state.frames.get(cache_key)
        if cached is not None:
            return cached
        frame = get_ohlc(
            OhlcRequest(symbol, interval=self.interval, bars=want, asof=self.state.asof),
            self.provider,
        )
        self.state.frames[cache_key] = frame
        return frame


@dataclass
class ToolResult:
    """Structured evidence from one tool execution.

    Tools return measurements, not prose: the decision model reasons over
    machine-readable values plus a one-line rendering of each.

    Attributes:
        tool: Tool name.
        success: Whether the measurement was taken.
        metrics: Measured values, keyed by observation key.
        displays: One-line rendering per key.
        findings: Short factual statements, for the final report.
        error: Why it failed, when it did.
        caveat: Qualification that must travel with every metric.
        network_calls: Outbound calls made.
    """

    tool: str
    success: bool
    metrics: dict[str, JsonValue] = field(default_factory=dict)
    displays: dict[str, str] = field(default_factory=dict)
    findings: tuple[str, ...] = ()
    error: str | None = None
    caveat: str | None = None
    network_calls: int = 0

    def observations(self, iteration: int) -> dict[str, Observation]:
        """Convert the metrics into state observations.

        Args:
            iteration: Iteration during which this ran.

        Returns:
            Observations keyed by observation key.
        """
        # A key with no display is supporting data: still available to
        # conditions and prerequisites, but not worth a line in the model's
        # prompt or the report. The prompt is the model's entire input, so
        # noise in it is not free.
        return {
            key: Observation(
                key=key,
                value=value,
                display=self.displays.get(key, ""),
                tool=self.tool,
                iteration=iteration,
                caveat=self.caveat,
            )
            for key, value in self.metrics.items()
        }


@dataclass(frozen=True)
class ToolSpec:
    """Everything the agent knows about one analysis.

    Attributes:
        name: Stable dotted identifier, used in questions and traces.
        category: Conceptual grouping.
        title: Short human label, interpolated into question text.
        jev_description: The single sentence the decision model is shown.
        produces: Observation keys written on success.
        requires: Observation keys that must already exist.
        applicable_when: Hard gates checked before the model sees the menu.
        cost: Expected cost.
        implemented: False for analyses this system cannot perform.
        absent_reason: Why an unimplemented analysis is absent.
        retrospective: True when results are fitted with hindsight.
        asof_capable: How well the tool supports a historical window.
        computed_in_agent: True when the agent computes this itself rather
            than wrapping an existing library function.
        default_params: Parameters used unless overridden.
        run: The implementation.
    """

    name: str
    category: str
    title: str
    jev_description: str
    produces: frozenset[str] = frozenset()
    requires: frozenset[str] = frozenset()
    applicable_when: tuple[Condition, ...] = ()
    cost: ToolCost = field(default_factory=ToolCost)
    implemented: bool = True
    absent_reason: str | None = None
    retrospective: bool = False
    asof_capable: Literal["native", "truncate", "none"] = "truncate"
    computed_in_agent: bool = False
    default_params: Mapping[str, JsonValue] = field(default_factory=dict)
    run: Callable[[ToolContext], ToolResult] | None = None

    def satisfied_by(self, state: AnalysisState, asof: date | None) -> bool:
        """Report whether the state already holds this tool's output.

        Args:
            state: Current state.
            asof: As-of date in force.

        Returns:
            True when every produced key exists and was measured at the same
            parameters and as-of date.
        """
        if not self.produces:
            return False
        fingerprint = param_fingerprint(self.name, self.default_params, asof)
        return all(
            key in state.observations
            and state.provenance.get(key) is not None
            and state.provenance[key].param_fingerprint == fingerprint
            for key in self.produces
        )

    def applicable(self, state: AnalysisState) -> tuple[bool, str | None]:
        """Test the hard gates on this tool.

        Args:
            state: Current state.

        Returns:
            Whether it may run, and the first failing gate otherwise.
        """

        def lookup(key: str) -> object:
            if key in state.observations:
                return state.observations[key].value
            if key == "run.live":
                return state.asof is None
            if key == "run.data_source":
                return state.data_source
            if key == "ticker.symbol":
                return state.ticker
            return MISSING

        return evaluate(self.applicable_when, lookup)

    def provenance(self, asof: date | None, iteration: int) -> dict[str, ProvenanceRecord]:
        """Build provenance records for this tool's outputs.

        Args:
            asof: As-of date in force.
            iteration: Iteration during which it ran.

        Returns:
            One record per produced key.
        """
        fingerprint = param_fingerprint(self.name, self.default_params, asof)
        return {
            key: ProvenanceRecord(
                tool=self.name,
                param_fingerprint=fingerprint,
                asof=None if asof is None else asof.isoformat(),
                iteration=iteration,
            )
            for key in self.produces
        }


class ToolRegistry:
    """The validated set of analyses available to a run."""

    def __init__(self, specs: Sequence[ToolSpec]) -> None:
        """Build and validate the registry.

        Args:
            specs: Tool specifications.

        Raises:
            ValueError: If names collide, two tools claim the same output, a
                requirement is unsatisfiable, or the graph contains a cycle.
        """
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            if spec.name in self._specs:
                raise ValueError(f"duplicate tool name {spec.name!r}")
            self._specs[spec.name] = spec

        producer: dict[str, str] = {}
        for spec in specs:
            for key in spec.produces:
                if key in producer:
                    raise ValueError(
                        f"observation {key!r} is produced by both "
                        f"{producer[key]!r} and {spec.name!r}"
                    )
                producer[key] = spec.name
        self._producer = producer

        for spec in specs:
            if not spec.implemented:
                continue
            if spec.run is None:
                raise ValueError(f"{spec.name!r} is implemented but has no run function")
            for key in spec.requires:
                if key not in producer:
                    raise ValueError(f"{spec.name!r} requires {key!r}, which no tool produces")
        self._check_acyclic()

    def _check_acyclic(self) -> None:
        """Verify the dependency graph has no cycles.

        Raises:
            ValueError: If a cycle is found.
        """
        colour: dict[str, int] = {}

        def visit(name: str, path: list[str]) -> None:
            state = colour.get(name, 0)
            if state == 1:
                cycle = " -> ".join([*path, name])
                raise ValueError(f"tool dependency cycle: {cycle}")
            if state == 2:
                return
            colour[name] = 1
            spec = self._specs[name]
            for key in sorted(spec.requires):
                upstream = self._producer.get(key)
                if upstream is not None and upstream != name:
                    visit(upstream, [*path, name])
            colour[name] = 2

        for name in sorted(self._specs):
            visit(name, [])

    # -- access ------------------------------------------------------------

    def __len__(self) -> int:
        """Return the number of registered tools.

        Returns:
            Tool count, including unimplemented ones.
        """
        return len(self._specs)

    def __contains__(self, name: object) -> bool:
        """Report whether a tool name is registered.

        Args:
            name: Tool name.

        Returns:
            True when registered.
        """
        return name in self._specs

    def get(self, name: str) -> ToolSpec:
        """Look a tool up by name.

        Args:
            name: Tool name.

        Returns:
            The specification.

        Raises:
            KeyError: If the name is not registered.
        """
        if name not in self._specs:
            raise KeyError(f"unknown tool {name!r}")
        return self._specs[name]

    def all(self) -> list[ToolSpec]:
        """Return every registered tool.

        Returns:
            Specifications in name order.
        """
        return [self._specs[n] for n in sorted(self._specs)]

    def implemented(self) -> list[ToolSpec]:
        """Return the tools this system can actually run.

        Returns:
            Implemented specifications in name order.
        """
        return [s for s in self.all() if s.implemented]

    def absent(self) -> list[ToolSpec]:
        """Return the analyses this system cannot perform.

        Returns:
            Unimplemented specifications in name order.
        """
        return [s for s in self.all() if not s.implemented]

    def producer_of(self, key: str) -> str | None:
        """Name the tool that produces an observation key.

        Args:
            key: Observation key.

        Returns:
            The producing tool's name, or None.
        """
        return self._producer.get(key)

    def prerequisite_plan(self, name: str, state: AnalysisState) -> list[str]:
        """List the tools that must run before one can.

        Resolution is deliberately done here rather than routed to the
        decision model: the experiment is about which analysis is worth
        running, not about dependency bookkeeping.

        Args:
            name: Tool the caller wants to run.
            state: Current state.

        Returns:
            Prerequisite tool names in execution order, excluding the tool
            itself and anything already satisfied.
        """
        plan: list[str] = []
        seen: set[str] = set()

        def walk(tool_name: str) -> None:
            spec = self._specs[tool_name]
            for key in sorted(spec.requires):
                if key in state.observations:
                    continue
                upstream = self._producer.get(key)
                if upstream is None or upstream in seen or upstream == name:
                    continue
                seen.add(upstream)
                walk(upstream)
                plan.append(upstream)

        walk(name)
        return plan

    def unreachable_requirement(
        self,
        name: str,
        state: AnalysisState,
        unavailable: set[str],
    ) -> str | None:
        """Find a requirement this tool can no longer obtain.

        A tool whose prerequisite has already failed cannot succeed, so
        offering it would spend a question and a tool call on a certainty. The
        search is transitive: a prerequisite that is itself blocked blocks
        everything downstream of it.

        Args:
            name: Tool to test.
            state: Current state.
            unavailable: Tools that may no longer run.

        Returns:
            A description of the first blocked requirement, or None.
        """

        def walk(tool_name: str, seen: frozenset[str]) -> str | None:
            if tool_name in seen:
                return None
            for key in sorted(self._specs[tool_name].requires):
                if key in state.observations:
                    continue
                upstream = self._producer.get(key)
                if upstream is None:
                    return f"{key} has no producer"
                if upstream in unavailable:
                    return f"{key} requires {upstream}, which cannot run"
                blocked = walk(upstream, seen | {tool_name})
                if blocked is not None:
                    return blocked
            return None

        return walk(name, frozenset())

    def candidates(
        self,
        state: AnalysisState,
        exclude: Sequence[str] = (),
    ) -> tuple[list[ToolSpec], list[tuple[str, str]]]:
        """Split the registry into what may run now and what may not.

        Args:
            state: Current state.
            exclude: Tool names to withhold regardless of applicability.

        Returns:
            The runnable specifications, and (tool, reason) pairs for the
            rest, so the trace records why each was withheld.
        """
        eligible: list[ToolSpec] = []
        excluded: list[tuple[str, str]] = []
        withheld = set(exclude)

        for spec in self.all():
            if not spec.implemented:
                excluded.append((spec.name, f"not_implemented: {spec.absent_reason}"))
                continue
            if spec.name in withheld:
                excluded.append((spec.name, "withheld"))
                continue
            if spec.satisfied_by(state, state.asof):
                excluded.append((spec.name, "already_satisfied"))
                continue
            if state.asof is not None and spec.asof_capable == "none":
                excluded.append((spec.name, "asof_unsupported: no point-in-time data available"))
                continue
            ok, failure = spec.applicable(state)
            if not ok:
                excluded.append((spec.name, f"applicable_when: {failure}"))
                continue
            blocked = self.unreachable_requirement(spec.name, state, withheld)
            if blocked is not None:
                excluded.append((spec.name, f"prerequisite_unavailable: {blocked}"))
                continue
            eligible.append(spec)

        return eligible, excluded
