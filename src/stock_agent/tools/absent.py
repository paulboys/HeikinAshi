"""The analyses this system cannot perform, and why.

These are registered rather than omitted. Questions are evaluated in
isolation, so the only channel through which the decision model can learn
that fundamentals or news are unavailable is the state text -- and a router
that does not know what is missing will keep implying it was considered.

Each reason is a finding about this repository, not a general claim: the gap
is in what stockcharts implements, and the wording says which. They are never
dispatchable, so none has a run function.

Public API:
    absent_specs() -> list[ToolSpec]
"""

from __future__ import annotations

from stock_agent.registry import ToolSpec

__all__ = ["absent_specs"]

# (name, category, title, reason). The title is what the model reads in the
# state's UNAVAILABLE section, so it names the analysis a reader would ask
# for rather than the module that would have held it.
_ABSENT: tuple[tuple[str, str, str, str], ...] = (
    (
        "fundamentals.summary",
        "fundamentals",
        "Fundamentals (earnings, valuation, growth)",
        "no fundamentals source exists in stockcharts; the only such code is "
        "an un-importable notebook cell",
    ),
    (
        "news.headlines",
        "news",
        "News and sentiment",
        "no news, RSS or sentiment source exists, and none would carry a "
        "point-in-time guarantee for a historical replay",
    ),
    (
        "correlation.matrix",
        "correlation",
        "Cross-asset correlation",
        "screener/correlation.py is an orphan script with no functions, "
        "hardcoded tickers and a loop bug; there is no usable implementation",
    ),
    (
        "portfolio.risk",
        "portfolio",
        "Portfolio risk and position sizing",
        "no portfolio, weighting, Sharpe or value-at-risk code exists",
    ),
    (
        "backtest.replay",
        "backtesting",
        "Backtest of this setup",
        "no backtesting, forward-return or walk-forward capability exists, so "
        "no claim about how this setup has performed can be measured here",
    ),
)


def absent_specs() -> list[ToolSpec]:
    """Return the analyses the decision model must be told it cannot have.

    Returns:
        Unimplemented tool specifications.
    """
    return [
        ToolSpec(
            name=name,
            category=category,
            title=title,
            jev_description="not available in this system.",
            implemented=False,
            absent_reason=reason,
            run=None,
        )
        for name, category, title, reason in _ABSENT
    ]
