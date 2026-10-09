"""Time-range (vertical) band shading for matplotlib and Plotly charts.

Converts a per-bar categorical label Series into contiguous spans and shades
them.  Nothing here knows how the labels were produced, so it works equally for
regime-segmentation output and for a plain boolean mask such as the
relative-strength shading in ``main_plot_beta``.

Public API:
    REGIME_SPAN_COLORS: dict[str, str]
    label_runs(labels: pd.Series, extend_to_end: bool = True)
        -> list[tuple[Any, Any, str]]
    shade_spans_mpl(ax, spans, colors=None, alpha=0.18, zorder=0, hatch=None,
                    legend=False) -> int
    shade_spans_plotly(fig, spans, colors=None, opacity=0.13, layer="below",
                       row=None, col=None) -> int
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:  # import cost paid only by type checkers
    from matplotlib.axes import Axes
    from plotly.graph_objects import Figure

__all__ = [
    "REGIME_SPAN_COLORS",
    "label_runs",
    "shade_spans_mpl",
    "shade_spans_plotly",
]

# Hex literals mirror stockcharts.theme (GREEN / RED / MUTED).  Duplicated
# rather than imported because theme.py imports dash, which has no business on
# a matplotlib code path -- the same reasoning charts/interactive.py applies.
REGIME_SPAN_COLORS: dict[str, str] = {
    "bull": "#26a69a",
    "bear": "#ef5350",
    "sideways": "#9598a1",
    "insufficient-data": "#9598a1",
}


def _median_step(index: pd.Index) -> pd.Timedelta | float | None:
    """Return the typical spacing between index entries.

    Args:
        index: Index to measure.

    Returns:
        The median difference between consecutive entries, or None when it
        cannot be determined (fewer than two entries, or a non-numeric index).
    """
    if len(index) < 2:
        return None
    try:
        diffs = pd.Series(index[1:]) - pd.Series(index[:-1])
        return diffs.median()
    except (TypeError, ValueError):
        return None


def label_runs(
    labels: pd.Series,
    extend_to_end: bool = True,
) -> list[tuple[Any, Any, str]]:
    """Merge a per-bar label Series into contiguous runs.

    Consecutive spans tile exactly: each run's ``end`` is the next run's
    ``start``, so bands abut with no gap and no overlap.

    Args:
        labels: Per-bar labels indexed by time.  NaN entries are dropped, so a
            series with leading warm-up NaNs can be passed as-is.
        extend_to_end: When True the final run's ``end`` is pushed forward by
            one median index step so the last band reaches the right edge of
            the plot.  This is what stops the final bar going unshaded.

    Returns:
        A list of ``(start, end, label)`` tuples in chronological order.  An
        empty or all-NaN input yields an empty list.
    """
    if labels is None or len(labels) == 0:
        return []

    clean = labels.dropna()
    if clean.empty:
        return []

    # Run ids increment whenever the label changes.
    run_id = clean.ne(clean.shift()).cumsum()
    starts = clean.groupby(run_id).apply(lambda run: run.index[0])
    values = clean.groupby(run_id).first()

    spans: list[tuple[Any, Any, str]] = []
    start_list = list(starts)
    for position, (start, label) in enumerate(zip(start_list, values, strict=False)):
        if position + 1 < len(start_list):
            end = start_list[position + 1]
        else:
            end = clean.index[-1]
            if extend_to_end:
                step = _median_step(clean.index)
                if step is not None:
                    try:
                        end = end + step
                    except (TypeError, ValueError):
                        pass
        spans.append((start, end, str(label)))
    return spans


def shade_spans_mpl(
    ax: Axes,
    spans: list[tuple[Any, Any, str]],
    colors: dict[str, str] | None = None,
    alpha: float = 0.18,
    zorder: int = 0,
    hatch: str | None = None,
    legend: bool = False,
) -> int:
    """Shade time ranges on a matplotlib axis.

    Args:
        ax: Target axis.
        spans: ``(start, end, label)`` tuples, typically from :func:`label_runs`.
        colors: Label to colour mapping.  Defaults to
            :data:`REGIME_SPAN_COLORS`.  Labels absent from the mapping are
            skipped, so a typo shows up as a missing band rather than a wrong
            one.
        alpha: Band opacity.
        zorder: Draw order; the default keeps bands behind plotted lines.
        hatch: Optional matplotlib hatch pattern, used to mark provisional
            bands.
        legend: When True the first band of each distinct label carries a
            legend entry, so ``ax.legend()`` shows one key per regime.

    Returns:
        The number of bands drawn.
    """
    palette = REGIME_SPAN_COLORS if colors is None else colors
    drawn = 0
    labelled: set[str] = set()
    for start, end, label in spans:
        colour = palette.get(label)
        if colour is None:
            continue
        kwargs: dict[str, Any] = {
            "color": colour,
            "alpha": alpha,
            "linewidth": 0,
            "zorder": zorder,
        }
        if hatch is not None:
            kwargs["hatch"] = hatch
        if legend and label not in labelled:
            kwargs["label"] = label
            labelled.add(label)
        ax.axvspan(start, end, **kwargs)
        drawn += 1
    return drawn


def shade_spans_plotly(
    fig: Figure,
    spans: list[tuple[Any, Any, str]],
    colors: dict[str, str] | None = None,
    opacity: float = 0.13,
    layer: str = "below",
    row: int | None = None,
    col: int | None = None,
) -> int:
    """Shade time ranges on a Plotly figure.

    Bands are layout shapes rather than traces, so they do not appear in the
    legend; add an invisible scatter per label if a key is needed.

    Args:
        fig: Target figure.
        spans: ``(start, end, label)`` tuples, typically from :func:`label_runs`.
        colors: Label to colour mapping.  Defaults to
            :data:`REGIME_SPAN_COLORS`; unknown labels are skipped.
        opacity: Band opacity.
        layer: ``"below"`` keeps bands behind the traces, which is almost
            always what is wanted.
        row: Subplot row, for figures built with ``make_subplots``.  Must be
            given together with ``col``.
        col: Subplot column, paired with ``row``.

    Returns:
        The number of bands drawn.
    """
    palette = REGIME_SPAN_COLORS if colors is None else colors
    drawn = 0
    for start, end, label in spans:
        colour = palette.get(label)
        if colour is None:
            continue
        kwargs: dict[str, Any] = {
            "x0": start,
            "x1": end,
            "fillcolor": colour,
            "opacity": opacity,
            "line_width": 0,
            "layer": layer,
        }
        if row is not None and col is not None:
            kwargs["row"] = row
            kwargs["col"] = col
        fig.add_vrect(**kwargs)
        drawn += 1
    return drawn
