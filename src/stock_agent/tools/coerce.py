"""Narrowing helpers for the broad JSON union tools read from.

Parameters and observations are stored as ``JsonValue`` so that everything in
the state is serialisable into a trace. Arithmetic needs concrete types, and
an unchecked ``int(...)`` on that union is both a type error and a real one: a
parameter arriving as a string or a list should fall back to the default, not
raise from inside a tool.

Public API:
    whole(value, default) -> int
    number(value, default) -> float
    maybe_number(value) -> float | None
    text(value, default) -> str
"""

from __future__ import annotations

from stock_agent.state import JsonValue

__all__ = ["maybe_number", "number", "text", "whole"]


def _numeric(value: object) -> float | None:
    """Accept only genuine numbers.

    Booleans are rejected: ``True`` is an ``int`` in Python, and silently
    reading a flag as the number one would be a confusing measurement.

    Args:
        value: Any value.

    Returns:
        The number, or None.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def whole(value: JsonValue | object, default: int) -> int:
    """Read an integer, falling back when the value is not numeric.

    Args:
        value: Value to narrow.
        default: Value returned when it is not a number.

    Returns:
        The integer.
    """
    found = _numeric(value)
    return default if found is None else int(found)


def number(value: JsonValue | object, default: float) -> float:
    """Read a float, falling back when the value is not numeric.

    Args:
        value: Value to narrow.
        default: Value returned when it is not a number.

    Returns:
        The float.
    """
    found = _numeric(value)
    return default if found is None else found


def maybe_number(value: JsonValue | object) -> float | None:
    """Read a float, distinguishing absent from zero.

    Args:
        value: Value to narrow.

    Returns:
        The float, or None when it is not a number.
    """
    return _numeric(value)


def text(value: JsonValue | object, default: str = "") -> str:
    """Read a string, falling back when the value is not one.

    Args:
        value: Value to narrow.
        default: Value returned when it is not a string.

    Returns:
        The string.
    """
    return value if isinstance(value, str) else default
