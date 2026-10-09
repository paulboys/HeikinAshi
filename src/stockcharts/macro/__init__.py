"""Treasury yield and macro-stress tracking.

Fetches the Treasury par-yield curve, FRED macro series, auction results and
New York Fed repo data, then evaluates each against the watchlist thresholds
in :mod:`stockcharts.macro.config`.
"""

from __future__ import annotations

from stockcharts.macro.config import (
    DISCLAIMER,
    KEY_DATES,
    SCENARIOS,
    WATCHLIST,
    KeyDate,
    Scenario,
    Status,
    Threshold,
)
from stockcharts.macro.series import SERIES, SeriesSpec

__all__ = [
    "DISCLAIMER",
    "KEY_DATES",
    "SCENARIOS",
    "SERIES",
    "WATCHLIST",
    "KeyDate",
    "Scenario",
    "SeriesSpec",
    "Status",
    "Threshold",
]
