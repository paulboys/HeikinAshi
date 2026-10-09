"""A small declarative algebra for gating tools.

Applicability is expressed as data rather than as callables, for four
reasons: conditions serialise straight into the decision trace, they can be
printed by the CLI, they are checkable by mypy, and a registry built from
them is diffable across versions. Nothing here evaluates arbitrary code.

Public API:
    Condition, evaluate(conditions, lookup) -> tuple[bool, str | None]
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

__all__ = ["MISSING", "OPERATORS", "Condition", "evaluate"]

Operator = Literal[
    "exists", "absent", "truthy", "falsy", "eq", "neq", "gt", "gte", "lt", "lte", "in"
]

OPERATORS: frozenset[str] = frozenset(
    ("exists", "absent", "truthy", "falsy", "eq", "neq", "gt", "gte", "lt", "lte", "in")
)


class _Missing:
    """Sentinel for an observation key that is not present."""

    def __repr__(self) -> str:
        """Render the sentinel.

        Returns:
            A short marker.
        """
        return "<missing>"


# Public because a lookup callable has to be able to signal absence.
MISSING = _Missing()

ConditionValue = bool | int | float | str | None | list[object]


@dataclass(frozen=True)
class Condition:
    """One gate on whether a tool may run.

    Attributes:
        key: Observation key to inspect.
        op: Comparison to apply.
        value: Right-hand operand, where the operator takes one.
    """

    key: str
    op: Operator
    value: ConditionValue = None

    def __post_init__(self) -> None:
        """Reject unknown operators at construction.

        Failing here rather than at evaluation turns a typo into an immediate
        registry build error instead of a tool that silently never runs.

        Raises:
            ValueError: If the operator is not recognised.
        """
        if self.op not in OPERATORS:
            raise ValueError(f"unknown operator {self.op!r}; expected one of {sorted(OPERATORS)}")

    def describe(self) -> str:
        """Render the condition for a trace or the CLI.

        Returns:
            A short human-readable form.
        """
        if self.op in ("exists", "absent", "truthy", "falsy"):
            return f"{self.key} {self.op}"
        return f"{self.key} {self.op} {self.value!r}"


def _compare(op: Operator, found: object, expected: ConditionValue) -> bool:
    """Apply one operator to a found value.

    Args:
        op: Comparison to apply.
        found: Value read from the state.
        expected: Right-hand operand.

    Returns:
        Whether the comparison holds. Comparisons between incomparable types
        return False rather than raising, so a malformed observation disables
        a tool instead of crashing a run.
    """
    if op == "exists":
        return found is not MISSING
    if op == "absent":
        return found is MISSING
    if found is MISSING:
        return False
    if op == "truthy":
        return bool(found)
    if op == "falsy":
        return not bool(found)
    if op == "eq":
        return bool(found == expected)
    if op == "neq":
        return bool(found != expected)
    if op == "in":
        return isinstance(expected, list) and found in expected
    if not isinstance(found, (int, float)) or isinstance(found, bool):
        return False
    if not isinstance(expected, (int, float)) or isinstance(expected, bool):
        return False
    if op == "gt":
        return found > expected
    if op == "gte":
        return found >= expected
    if op == "lt":
        return found < expected
    return found <= expected


def evaluate(
    conditions: Sequence[Condition],
    lookup: Callable[[str], object],
) -> tuple[bool, str | None]:
    """Test every condition, reporting the first that fails.

    Args:
        conditions: Conditions, combined with logical AND.
        lookup: Resolves an observation key, returning the module's missing
            sentinel when absent.

    Returns:
        Whether all conditions hold, and a description of the first failure.
    """
    for condition in conditions:
        found = lookup(condition.key)
        if not _compare(condition.op, found, condition.value):
            shown = "absent" if found is MISSING else repr(found)
            return False, f"{condition.describe()} (found {shown})"
    return True, None
