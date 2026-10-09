"""Plotly figures for the Treasury yield dashboard.

The decomposition figure stacks four panels that answer the question the
dashboard exists for: is the long end moving because of expected policy, or
because of the premium investors demand for duration risk?

Panel construction follows the dynamic ``row_specs`` pattern used by
:mod:`stockcharts.charts.interactive`, so rows can be dropped when their data
is unavailable without disturbing the rest of the figure.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BG = "#131722"
GRID = "#1e222d"
TEXT = "#d1d4dc"
MUTED = "#9598a1"
ACCENT = "#2962ff"
GREEN = "#26a69a"
RED = "#ef5350"
AMBER = "#ff9800"
PURPLE = "#ab47bc"

ROW_HEIGHTS: dict[str, float] = {
    "nominal": 0.34,
    "decomp": 0.22,
    "curve": 0.22,
    "premium": 0.22,
}

TENOR_COLORS: dict[float, str] = {
    2.0: MUTED,
    5.0: "#4dd0e1",
    10.0: ACCENT,
    20.0: AMBER,
    30.0: RED,
}


def _grid_style() -> dict[str, object]:
    """Return the shared axis styling.

    Returns:
        Keyword arguments for ``update_xaxes`` and ``update_yaxes``.
    """
    return {
        "gridcolor": GRID,
        "zerolinecolor": GRID,
        "showspikes": True,
        "spikemode": "across",
        "spikesnap": "cursor",
        "spikecolor": MUTED,
        "spikethickness": 1,
    }


def _trim(frame: pd.DataFrame | pd.Series, lookback_days: int) -> pd.DataFrame | pd.Series:
    """Restrict a time series to a trailing window.

    Args:
        frame: Object with a datetime index.
        lookback_days: Days of history to keep.

    Returns:
        The trimmed object.
    """
    if len(frame) == 0:
        return frame
    cutoff = pd.Timestamp(frame.index[-1]) - pd.Timedelta(days=lookback_days)
    return frame[frame.index >= cutoff]


def build_yield_figure(
    curve: pd.DataFrame,
    real_curve: pd.DataFrame | None = None,
    series: dict[str, pd.Series] | None = None,
    expected_short: pd.Series | None = None,
    rows: Sequence[str] | None = None,
    lookback_days: int = 365,
    title: str = "Treasury yield decomposition",
    height: int = 860,
) -> go.Figure:
    """Build the stacked decomposition figure.

    Args:
        curve: Nominal par yield curve, tenors in years as columns.
        real_curve: Real (TIPS) curve, used for the second panel.
        series: FRED series keyed by catalog key, for breakevens and premium.
        expected_short: Derived expected short rate, plotted against premium.
        rows: Panels to draw.  Defaults to every panel with data.
        lookback_days: Days of history to show.
        title: Figure title.
        height: Figure height in pixels.

    Returns:
        The assembled figure.  An empty curve yields a placeholder figure
        rather than raising.
    """
    series = series or {}
    real_curve = real_curve if real_curve is not None else pd.DataFrame()

    available: list[str] = []
    if not curve.empty:
        available.append("nominal")
    if not curve.empty and (not real_curve.empty or "breakeven_10y" in series):
        available.append("decomp")
    if not curve.empty and {2.0, 10.0} <= set(curve.columns):
        available.append("curve")
    if "term_premium_10y" in series:
        available.append("premium")

    row_specs = [r for r in (rows or available) if r in available]
    if not row_specs:
        figure = go.Figure()
        figure.update_layout(
            template="plotly_dark",
            paper_bgcolor=BG,
            plot_bgcolor=BG,
            height=height,
            annotations=[
                {
                    "text": "No yield data available",
                    "showarrow": False,
                    "font": {"color": MUTED, "size": 16},
                }
            ],
        )
        return figure

    weights = [ROW_HEIGHTS.get(r, 0.25) for r in row_specs]
    total = sum(weights)
    heights = [w / total for w in weights]

    titles = {
        "nominal": "Nominal par yields",
        "decomp": "10y: nominal vs real vs breakeven",
        "curve": "Curve spreads",
        "premium": "Term premium vs expected short rate",
    }
    figure = make_subplots(
        rows=len(row_specs),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.045,
        row_heights=heights,
        subplot_titles=[titles[r] for r in row_specs],
    )

    trimmed = _trim(curve, lookback_days)

    if "nominal" in row_specs:
        row = row_specs.index("nominal") + 1
        for tenor, color in TENOR_COLORS.items():
            if tenor not in trimmed.columns:
                continue
            column = trimmed[tenor].dropna()
            if column.empty:
                continue
            label = f"{tenor:.0f}y" if tenor >= 1 else f"{tenor * 12:.0f}m"
            figure.add_trace(
                go.Scatter(
                    x=column.index,
                    y=column.to_numpy(),
                    name=label,
                    line={"color": color, "width": 1.8},
                    hovertemplate=f"{label} %{{y:.2f}}%<extra></extra>",
                ),
                row=row,
                col=1,
            )
        # Bands mark the levels the watchlist treats as watch and alert.
        figure.add_hrect(
            y0=5.0, y1=5.5, fillcolor="rgba(255,152,0,0.07)", line_width=0, row=row, col=1
        )
        figure.add_hrect(
            y0=5.5, y1=8.0, fillcolor="rgba(239,83,80,0.07)", line_width=0, row=row, col=1
        )

    if "decomp" in row_specs:
        row = row_specs.index("decomp") + 1
        if 10.0 in trimmed.columns:
            nominal = trimmed[10.0].dropna()
            figure.add_trace(
                go.Scatter(
                    x=nominal.index,
                    y=nominal.to_numpy(),
                    name="10y nominal",
                    line={"color": ACCENT, "width": 1.8},
                    hovertemplate="nominal %{y:.2f}%<extra></extra>",
                ),
                row=row,
                col=1,
            )
        if not real_curve.empty and 10.0 in real_curve.columns:
            real = _trim(real_curve, lookback_days)[10.0].dropna()
            figure.add_trace(
                go.Scatter(
                    x=real.index,
                    y=real.to_numpy(),
                    name="10y real",
                    line={"color": GREEN, "width": 1.8},
                    hovertemplate="real %{y:.2f}%<extra></extra>",
                ),
                row=row,
                col=1,
            )
            figure.add_hline(y=3.0, line={"color": RED, "width": 1, "dash": "dot"}, row=row, col=1)
        breakeven = series.get("breakeven_10y")
        if breakeven is not None and not breakeven.empty:
            trimmed_be = _trim(breakeven, lookback_days)
            figure.add_trace(
                go.Scatter(
                    x=trimmed_be.index,
                    y=trimmed_be.to_numpy(),
                    name="10y breakeven",
                    line={"color": AMBER, "width": 1.5, "dash": "dash"},
                    hovertemplate="breakeven %{y:.2f}%<extra></extra>",
                ),
                row=row,
                col=1,
            )

    if "curve" in row_specs:
        row = row_specs.index("curve") + 1
        for short, long, color in ((2.0, 10.0, ACCENT), (5.0, 30.0, PURPLE)):
            if {short, long} <= set(trimmed.columns):
                spread = (trimmed[long] - trimmed[short]).dropna() * 100.0
                label = f"{short:.0f}s{long:.0f}s"
                figure.add_trace(
                    go.Scatter(
                        x=spread.index,
                        y=spread.to_numpy(),
                        name=label,
                        line={"color": color, "width": 1.6},
                        hovertemplate=f"{label} %{{y:.0f}}bp<extra></extra>",
                    ),
                    row=row,
                    col=1,
                )
        figure.add_hline(y=0, line={"color": MUTED, "width": 1, "dash": "dot"}, row=row, col=1)
        figure.add_hrect(
            y0=-200, y1=0, fillcolor="rgba(239,83,80,0.07)", line_width=0, row=row, col=1
        )

    if "premium" in row_specs:
        row = row_specs.index("premium") + 1
        premium = _trim(series["term_premium_10y"], lookback_days)
        figure.add_trace(
            go.Scatter(
                x=premium.index,
                y=premium.to_numpy(),
                name="term premium",
                line={"color": RED, "width": 1.8},
                hovertemplate="term premium %{y:.2f}%<extra></extra>",
            ),
            row=row,
            col=1,
        )
        if expected_short is not None and not expected_short.empty:
            trimmed_exp = _trim(expected_short, lookback_days)
            figure.add_trace(
                go.Scatter(
                    x=trimmed_exp.index,
                    y=trimmed_exp.to_numpy(),
                    name="expected short rate",
                    line={"color": GREEN, "width": 1.8},
                    hovertemplate="expected short %{y:.2f}%<extra></extra>",
                ),
                row=row,
                col=1,
            )

    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font={"color": TEXT},
        title={"text": title, "font": {"size": 16}},
        height=height,
        margin={"l": 60, "r": 50, "t": 60, "b": 40},
        hovermode="x unified",
        dragmode="pan",
        legend={"orientation": "h", "y": -0.06, "font": {"size": 11}},
    )
    grid = _grid_style()
    figure.update_xaxes(**grid)
    figure.update_yaxes(**grid, side="right")
    for index, spec in enumerate(row_specs, start=1):
        unit = "bp" if spec == "curve" else "%"
        figure.update_yaxes(ticksuffix=unit, row=index, col=1)
    for annotation in figure.layout.annotations:
        annotation.font.size = 12
        annotation.font.color = MUTED
    return figure


def build_curve_snapshot_figure(
    curve: pd.DataFrame,
    comparisons: Sequence[int] = (5, 21),
    height: int = 360,
) -> go.Figure:
    """Plot the current par curve against earlier snapshots.

    Args:
        curve: Nominal par yield curve, tenors in years as columns.
        comparisons: Observation counts to look back for the ghosted lines.
        height: Figure height in pixels.

    Returns:
        The assembled figure.
    """
    figure = go.Figure()
    if curve.empty:
        figure.update_layout(
            template="plotly_dark",
            paper_bgcolor=BG,
            plot_bgcolor=BG,
            height=height,
            annotations=[{"text": "No curve data", "showarrow": False, "font": {"color": MUTED}}],
        )
        return figure

    tenors = sorted(float(c) for c in curve.columns)
    ghosts = [(c, f"{c} sessions ago", MUTED) for c in comparisons if len(curve) > c]
    for offset, label, color in reversed(ghosts):
        row = curve.iloc[-(offset + 1)]
        figure.add_trace(
            go.Scatter(
                x=tenors,
                y=[row.get(t) for t in tenors],
                name=label,
                line={"color": color, "width": 1.2, "dash": "dot"},
                hovertemplate="%{x}y %{y:.2f}%<extra></extra>",
            )
        )
    latest = curve.iloc[-1]
    as_of = pd.Timestamp(curve.index[-1]).date().isoformat()
    figure.add_trace(
        go.Scatter(
            x=tenors,
            y=[latest.get(t) for t in tenors],
            name=f"today ({as_of})",
            line={"color": ACCENT, "width": 2.4},
            marker={"size": 6},
            mode="lines+markers",
            hovertemplate="%{x}y %{y:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font={"color": TEXT},
        title={"text": "Par yield curve", "font": {"size": 16}},
        height=height,
        margin={"l": 60, "r": 50, "t": 60, "b": 40},
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.18, "font": {"size": 11}},
    )
    grid = _grid_style()
    figure.update_xaxes(
        **grid,
        title="Tenor (years)",
        type="log",
        tickvals=tenors,
        ticktext=[f"{t:.0f}y" if t >= 1 else f"{t * 12:.0f}m" for t in tenors],
    )
    figure.update_yaxes(**grid, side="right", ticksuffix="%")
    return figure


__all__ = ["build_curve_snapshot_figure", "build_yield_figure"]
