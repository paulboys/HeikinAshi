"""Bounds that hold regardless of what the decision model returns.

Termination must not depend on the model being sensible. The candidate set
shrinks monotonically as tools are satisfied, re-entry is bounded by the
material-change rule and a per-tool cap, and a state-unchanged check is the
backstop. A model that answers 0.99 for one tool forever still halts.

Public API:
    BudgetState, LoopGuard, GuardTrip
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from stock_agent.config import BudgetConfig
from stock_agent.registry import ToolSpec
from stock_agent.state import AnalysisState

__all__ = ["BudgetState", "GuardTrip", "LoopGuard"]


@dataclass
class BudgetState:
    """Consumption so far.

    Attributes:
        iterations: Decision rounds completed.
        tool_calls: Tool executions, including prerequisites.
        jev_calls: Requests to the decision model.
        network_calls: Outbound data fetches.
        consecutive_tool_errors: Failures since the last success.
        started_at: Perf counter reading at the start of the run.
    """

    iterations: int = 0
    tool_calls: int = 0
    jev_calls: int = 0
    network_calls: int = 0
    consecutive_tool_errors: int = 0
    started_at: float = field(default_factory=time.perf_counter)

    @property
    def wall_seconds(self) -> float:
        """Return elapsed wall-clock time.

        Returns:
            Seconds since the run began.
        """
        return time.perf_counter() - self.started_at

    def to_dict(self) -> dict[str, float | int]:
        """Render the budget for the trace.

        Returns:
            A JSON-safe mapping.
        """
        return {
            "iterations": self.iterations,
            "tool_calls": self.tool_calls,
            "jev_calls": self.jev_calls,
            "network_calls": self.network_calls,
            "wall_s": round(self.wall_seconds, 3),
        }


@dataclass(frozen=True)
class GuardTrip:
    """A bound that has been reached.

    Attributes:
        reason: Short identifier, used as the run's exit reason.
        detail: Human explanation for the trace and the report.
    """

    reason: str
    detail: str


class LoopGuard:
    """Enforces the budgets and the rules that make a run terminate."""

    def __init__(self, budget: BudgetConfig, state: BudgetState | None = None) -> None:
        """Create a guard.

        Args:
            budget: The caps to enforce.
            state: Existing consumption, for resuming.
        """
        self.budget = budget
        self.state = state or BudgetState()
        self._tool_counts: dict[str, int] = {}
        self._disabled: set[str] = set()
        self._made_no_progress = False

    # -- checks ------------------------------------------------------------

    def check(self) -> GuardTrip | None:
        """Test every bound, in a fixed priority order.

        Returns:
            The first bound reached, or None to continue.
        """
        budget = self.budget
        consumed = self.state

        if consumed.iterations >= budget.max_iterations:
            return GuardTrip(
                "iteration_cap",
                f"reached {budget.max_iterations} iterations",
            )
        if consumed.tool_calls >= budget.max_tool_calls:
            return GuardTrip(
                "tool_call_cap",
                f"reached {budget.max_tool_calls} tool calls",
            )
        if consumed.jev_calls >= budget.max_jev_calls:
            return GuardTrip(
                "jev_call_cap",
                f"reached {budget.max_jev_calls} decision requests",
            )
        if consumed.wall_seconds >= budget.max_wall_seconds:
            return GuardTrip(
                "wall_clock",
                f"exceeded {budget.max_wall_seconds:.0f}s",
            )
        if consumed.network_calls >= budget.max_network_calls:
            return GuardTrip(
                "network_cap",
                f"reached {budget.max_network_calls} network calls",
            )
        if consumed.consecutive_tool_errors >= budget.max_consecutive_tool_errors:
            return GuardTrip(
                "tool_failures",
                f"{consumed.consecutive_tool_errors} tool failures in a row",
            )
        if self._made_no_progress:
            # The previous iteration ran tools but learned nothing, so asking
            # the same question against the same state cannot help.
            return GuardTrip(
                "state_unchanged",
                "an iteration completed without changing what is known",
            )
        return None

    def observe_iteration(self, before: str, after: str) -> None:
        """Record whether an iteration changed what is known.

        Compared within a single iteration rather than across two:
        consecutive iterations trivially share a fingerprint, since nothing
        happens between the end of one and the start of the next.

        Args:
            before: Fingerprint at the start of the iteration.
            after: Fingerprint at the end of it.
        """
        self._made_no_progress = before == after

    # -- tool admission ----------------------------------------------------

    def may_run(
        self,
        spec: ToolSpec,
        state: AnalysisState,
    ) -> tuple[bool, str | None]:
        """Decide whether a tool may execute now.

        A tool may repeat only when it would measure something different:
        either its parameters changed, or an input it depends on has been
        rewritten since it last ran. Without that rule a model that keeps
        choosing the same tool would spin.

        Args:
            spec: The tool under consideration.
            state: Current state.

        Returns:
            Whether it may run, and the reason it may not.
        """
        if spec.name in self._disabled:
            return False, "disabled after repeated failure"

        count = self._tool_counts.get(spec.name, 0)
        if count >= self.budget.max_same_tool_calls:
            return False, (
                f"already run {count} times " f"(limit {self.budget.max_same_tool_calls})"
            )
        if count == 0:
            return True, None

        if spec.satisfied_by(state, state.asof):
            return False, "already satisfied at these parameters"
        return True, None

    def record_tool(self, name: str, success: bool, network_calls: int = 0) -> None:
        """Account for one tool execution.

        Args:
            name: Tool name.
            success: Whether it produced a measurement.
            network_calls: Outbound calls it made.
        """
        self._tool_counts[name] = self._tool_counts.get(name, 0) + 1
        self.state.tool_calls += 1
        self.state.network_calls += network_calls
        if success:
            self.state.consecutive_tool_errors = 0
        else:
            self.state.consecutive_tool_errors += 1
            # A tool that has failed is withheld rather than offered again:
            # the model cannot know it is broken.
            self._disabled.add(name)

    def record_jev_call(self) -> None:
        """Account for one decision request."""
        self.state.jev_calls += 1

    def record_iteration(self) -> None:
        """Account for one completed decision round."""
        self.state.iterations += 1

    @property
    def disabled(self) -> frozenset[str]:
        """Return the tools withheld after failing.

        Returns:
            Tool names.
        """
        return frozenset(self._disabled)

    def counts(self) -> dict[str, int]:
        """Return how often each tool has run.

        Returns:
            Tool name to execution count.
        """
        return dict(self._tool_counts)
