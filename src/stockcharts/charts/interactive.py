"""Reusable interactive Plotly chart builder.

Builds TradingView-style candlestick charts with:
- Heiken Ashi candlesticks + volume subplot
- Dark theme (#131722)
- Drawing toolbar (line, path, rect, eraser, horizontal line)
- Infinite horizontal price-level lines with price labels
- Shape save/load via localStorage
- Undo/redo (Ctrl+Z / Ctrl+Y)
- Touch axis-drag zoom
- Crosshair spikes

Public API:
    build_interactive_figure(ticker, ha_data, raw_data, period) -> go.Figure
    get_interactive_config() -> dict
    get_post_script(ticker, period) -> str
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import plotly.graph_objects as go

if TYPE_CHECKING:  # annotations only, so pandas is not imported at runtime
    import pandas as pd


def build_interactive_figure(
    ticker: str,
    ha_data: pd.DataFrame,
    raw_data: pd.DataFrame,
    period: str = "1d",
    height: int | None = None,
    width: int | None = None,
    candle_type: str = "normal",
    show_volume_profile: bool = False,
    lookback: str | None = None,
    show_stochastic: bool = False,
    stoch_k: int = 14,
    stoch_d: int = 3,
    stoch_smooth: int = 3,
    stoch_overbought: int = 80,
    stoch_oversold: int = 20,
) -> go.Figure:
    """Build a TradingView-style interactive candlestick chart.

    Args:
        ticker: Stock symbol for the title.
        ha_data: Heiken Ashi DataFrame with HA_Open/High/Low/Close columns.
        raw_data: Original OHLC DataFrame with Volume column.
        period: Aggregation period label (e.g., '1d', '1wk').
        height: Chart height in pixels (None = responsive/autosize).
        width: Chart width in pixels (None = responsive/autosize).
        candle_type: 'normal' for standard OHLC candles (default),
                     'ha' for Heiken Ashi candles.
        show_volume_profile: If True, overlay horizontal volume-at-price
                             bars on the price subplot.
        lookback: Display window (e.g. '1y', '6mo', 'max'). Used to
                  slice data for the volume profile so the histogram
                  matches the visible chart window.
        show_stochastic: If True, add a Stochastic Oscillator subplot.
        stoch_k: %K lookback period (default 14).
        stoch_d: %D smoothing period (default 3).
        stoch_smooth: %K smoothing period (default 3; 1 = fast stochastic).
        stoch_overbought: Overbought threshold line (default 80).
        stoch_oversold: Oversold threshold line (default 20).

    Returns:
        Plotly Figure object ready for display or write_html.
    """
    import pandas as pd

    dt_index = pd.to_datetime(ha_data.index)
    has_volume = "Volume" in raw_data.columns and raw_data["Volume"].sum() > 0

    # Select OHLC source based on candle type
    use_ha = candle_type == "ha"
    if use_ha:
        c_open = ha_data["HA_Open"]
        c_high = ha_data["HA_High"]
        c_low = ha_data["HA_Low"]
        c_close = ha_data["HA_Close"]
        candle_label = "HA"
    else:
        c_open = raw_data["Open"]
        c_high = raw_data["High"]
        c_low = raw_data["Low"]
        c_close = raw_data["Close"]
        candle_label = "OHLC"

    candle_trace = go.Candlestick(
        x=dt_index,
        open=c_open,
        high=c_high,
        low=c_low,
        close=c_close,
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        increasing_fillcolor="#26a69a",
        decreasing_fillcolor="#ef5350",
        name=candle_label,
        hovertemplate=(
            "<b>%{x|%Y-%m-%d}</b><br>"
            "Open: $%{open:.2f}<br>"
            "High: $%{high:.2f}<br>"
            "Low: $%{low:.2f}<br>"
            "Close: $%{close:.2f}<extra></extra>"
        ),
    )

    # Determine subplot layout depending on enabled overlays
    from plotly.subplots import make_subplots

    n_rows = 1
    row_specs: list[str] = ["price"]
    if show_stochastic:
        n_rows += 1
        row_specs.append("stoch")
    if has_volume:
        n_rows += 1
        row_specs.append("volume")

    # Compute row heights proportionally
    _heights_map = {"price": 0.60, "stoch": 0.20, "volume": 0.20}
    raw_heights = [_heights_map[r] for r in row_specs]
    total = sum(raw_heights)
    row_heights = [h / total for h in raw_heights]

    if n_rows > 1:
        fig = make_subplots(
            rows=n_rows,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=row_heights,
        )
    else:
        fig = go.Figure()

    # --- Price subplot (always row 1) ---
    if n_rows > 1:
        fig.add_trace(candle_trace, row=1, col=1)
    else:
        fig.add_trace(candle_trace)
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)

    # --- Stochastic Oscillator subplot ---
    stoch_row: int | None = None
    if show_stochastic:
        from stockcharts.indicators.stochastic import compute_stochastic

        stoch_row = row_specs.index("stoch") + 1
        stoch_df = compute_stochastic(
            raw_data["High"],
            raw_data["Low"],
            raw_data["Close"],
            k_period=stoch_k,
            d_period=stoch_d,
            smooth_k=stoch_smooth,
        )
        # %K line (solid)
        fig.add_trace(
            go.Scatter(
                x=dt_index,
                y=stoch_df["pctK"],
                mode="lines",
                line=dict(color="#2962ff", width=1.2),
                name="%K",
                hovertemplate="%K: %{y:.1f}<extra></extra>",
            ),
            row=stoch_row,
            col=1,
        )
        # %D line (dashed)
        fig.add_trace(
            go.Scatter(
                x=dt_index,
                y=stoch_df["pctD"],
                mode="lines",
                line=dict(color="#ff6d00", width=1.2, dash="dash"),
                name="%D",
                hovertemplate="%D: %{y:.1f}<extra></extra>",
            ),
            row=stoch_row,
            col=1,
        )
        # Overbought / oversold reference lines
        for level, _label in [(stoch_overbought, "OB"), (stoch_oversold, "OS")]:
            fig.add_trace(
                go.Scatter(
                    x=[dt_index.min(), dt_index.max()],
                    y=[level, level],
                    mode="lines",
                    line=dict(color="#9598a1", width=0.8, dash="dot"),
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=stoch_row,
                col=1,
            )
        # Shade overbought / oversold zones
        fig.add_hrect(
            y0=stoch_overbought,
            y1=100,
            fillcolor="rgba(239,83,80,0.07)",
            line_width=0,
            row=stoch_row,
            col=1,
        )
        fig.add_hrect(
            y0=0,
            y1=stoch_oversold,
            fillcolor="rgba(38,166,154,0.07)",
            line_width=0,
            row=stoch_row,
            col=1,
        )
        fig.update_yaxes(
            title_text="Stoch",
            range=[-5, 105],
            fixedrange=True,
            row=stoch_row,
            col=1,
        )

    # --- Volume subplot ---
    vol_row: int | None = None
    if has_volume:
        vol_row = row_specs.index("volume") + 1
        vol_colors = [
            "#26a69a" if c >= o else "#ef5350" for o, c in zip(c_open, c_close, strict=False)
        ]
        fig.add_trace(
            go.Bar(
                x=dt_index,
                y=raw_data["Volume"],
                marker_color=vol_colors,
                opacity=0.4,
                name="Volume",
                hoverinfo="skip",
            ),
            row=vol_row,
            col=1,
        )
        fig.update_yaxes(title_text="Volume", row=vol_row, col=1)

    # --- Volume Profile is added AFTER axis styling (see below) ---

    # TradingView dark theme
    interval_label = {"1d": "Daily", "1wk": "Weekly", "1mo": "Monthly"}.get(period, period)
    candle_type_label = "Heiken Ashi" if use_ha else "Candlestick"
    fig.update_layout(
        title=dict(
            text=f"{ticker} — {candle_type_label} ({interval_label})",
            font=dict(size=18),
        ),
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        hovermode="closest",
        hoverdistance=10,
        autosize=True,
        height=height,
        width=width,
        margin=dict(l=60, r=50, t=50, b=40),
        paper_bgcolor="#131722",
        plot_bgcolor="#131722",
        font=dict(color="#d1d4dc"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        newshape=dict(
            line=dict(color="#2962ff", width=2),
            fillcolor="rgba(41,98,255,0.1)",
            opacity=0.7,
        ),
        dragmode="pan",
    )

    # Axis styling with crosshair spikes
    spike_style = dict(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=0.5,
        spikecolor="#9598a1",
        spikedash="solid",
    )
    grid_style = dict(
        showgrid=True,
        gridwidth=1,
        gridcolor="#1e222d",
        zeroline=False,
        automargin=True,
    )
    # Anchor x-axis to the bottom-most subplot's y-axis
    bottom_anchor = "free"
    if n_rows >= 2:
        bottom_anchor = f"y{n_rows}" if n_rows > 1 else "y"
    fig.update_xaxes(
        **grid_style,
        **spike_style,
        side="bottom",
        anchor=bottom_anchor,
        showticklabels=True,
        tickfont=dict(color="#9598a1"),
        title_font=dict(color="#9598a1"),
        constrain="domain",
    )
    fig.update_yaxes(
        **grid_style,
        **spike_style,
        side="right",
        showticklabels=True,
        tickfont=dict(color="#9598a1"),
        title_font=dict(color="#9598a1"),
        constrain="domain",
    )

    # Lock the volume subplot y-axis so zoom/drag only affects the price chart
    if has_volume and vol_row is not None:
        fig.update_yaxes(fixedrange=True, row=vol_row, col=1)

    # --- Volume Profile (single histogram for the display window) ---
    if show_volume_profile and has_volume:
        _add_volume_profile(fig, raw_data, lookback=lookback, n_subplot_rows=n_rows)

    return fig


def get_interactive_config() -> dict:
    """Return Plotly write_html config dict with drawing toolbar buttons.

    Returns:
        Config dictionary for fig.write_html(..., config=...) or dcc.Graph(config=...).
    """
    return {
        "modeBarButtonsToAdd": [
            "drawline",
            "drawopenpath",
            "drawclosedpath",
            "drawrect",
            "eraseshape",
        ],
        "displayModeBar": True,
        "scrollZoom": True,
        "displaylogo": False,
    }


def get_post_script(ticker: str, period: str = "", candle_type: str = "normal") -> str:
    """Return raw JavaScript for localStorage shape persistence, undo/redo, and touch zoom.

    This string is injected via Plotly's ``post_script`` parameter inside
    ``Plotly.newPlot().then(function(){ ... })``, so it must be raw JS only
    (no ``<script>`` tags).  ``{plot_id}`` is replaced by Plotly with the div id.

    Drawings are stored **per-ticker** (not per-interval) so that lines
    drawn on a weekly chart also appear on the daily chart and vice-versa.

    Args:
        ticker: Stock symbol (used for localStorage key).
        period: Aggregation period label (kept for status bar display only).
        candle_type: 'normal' or 'ha' (used for status bar label).

    Returns:
        Raw JavaScript string.
    """
    storage_key = f"stockcharts_{ticker}"
    candle_bar_label = "Heiken Ashi" if candle_type == "ha" else "Candlestick"
    return (
        "var gd = document.getElementById('{plot_id}');\n"
        "var SKEY = '" + storage_key + "';\n"
        "\n"
        "// --- Undo/Redo history for shapes ---\n"
        "var _hist = [];   // stack of shape snapshots (JSON strings)\n"
        "var _hIdx = -1;   // pointer into _hist\n"
        "var _skip = false; // flag to suppress recording during undo/redo\n"
        "\n"
        "function _snap() {\n"
        "  return JSON.stringify(gd.layout.shapes || []);\n"
        "}\n"
        "function _push(s) {\n"
        "  _hist = _hist.slice(0, _hIdx + 1);\n"
        "  _hist.push(s);\n"
        "  if (_hist.length > 200) _hist.shift();\n"
        "  _hIdx = _hist.length - 1;\n"
        "}\n"
        "\n"
        "// Restore saved shapes\n"
        "try {\n"
        "  var saved = localStorage.getItem(SKEY);\n"
        "  if (saved) {\n"
        "    var shapes = JSON.parse(saved);\n"
        "    _skip = true;\n"
        "    Plotly.relayout(gd, {shapes: shapes});\n"
        "    _skip = false;\n"
        "    console.log('Restored', shapes.length, 'shapes');\n"
        "  }\n"
        "} catch(e) { console.warn('Error loading shapes:', e); }\n"
        "_push(_snap());\n"
        "\n"
        "// Save shapes + record history on any relayout event\n"
        "gd.on('plotly_relayout', function(ed) {\n"
        "  try {\n"
        "    var shapes = gd.layout.shapes || [];\n"
        "    localStorage.setItem(SKEY, JSON.stringify(shapes));\n"
        "  } catch(e) { console.warn('Error saving shapes:', e); }\n"
        "  if (_skip) return;\n"
        "  var keys = Object.keys(ed || {});\n"
        "  var isShape = keys.some(function(k) {\n"
        "    return k === 'shapes' || k.indexOf('shapes[') === 0;\n"
        "  });\n"
        "  if (isShape) {\n"
        "    var cur = _snap();\n"
        "    if (_hIdx < 0 || cur !== _hist[_hIdx]) _push(cur);\n"
        "  }\n"
        "});\n"
        "\n"
        "// Ctrl+Z = undo, Ctrl+Y = redo\n"
        "document.addEventListener('keydown', function(e) {\n"
        "  if (!e.ctrlKey && !e.metaKey) return;\n"
        "  if (e.key === 'z' || e.key === 'Z') {\n"
        "    e.preventDefault();\n"
        "    if (_hIdx > 0) {\n"
        "      _hIdx--;\n"
        "      _skip = true;\n"
        "      Plotly.relayout(gd, {shapes: JSON.parse(_hist[_hIdx])});\n"
        "      _skip = false;\n"
        "    }\n"
        "  } else if (e.key === 'y' || e.key === 'Y') {\n"
        "    e.preventDefault();\n"
        "    if (_hIdx < _hist.length - 1) {\n"
        "      _hIdx++;\n"
        "      _skip = true;\n"
        "      Plotly.relayout(gd, {shapes: JSON.parse(_hist[_hIdx])});\n"
        "      _skip = false;\n"
        "    }\n"
        "  }\n"
        "});\n"
        "\n"
        "// --- Touch interaction: pan, pinch-zoom, axis-drag ---\n"
        "(function() {\n"
        "  var tc = {};           // touch context\n"
        "  var SENS = 0.005;      // axis-zone zoom sensitivity\n"
        "\n"
        "  function isDrawMode() {\n"
        "    var dm = gd._fullLayout.dragmode || '';\n"
        "    return dm.indexOf('draw') === 0;\n"
        "  }\n"
        "\n"
        "  // Block Plotly's native touch drag on its internal overlay elements\n"
        "  // so our custom pan/pinch handlers have full control.\n"
        "  // Only allow Plotly's touch through when a draw tool is active.\n"
        "  var drags = gd.querySelectorAll('.draglayer .drag, .draglayer .nsewdrag');\n"
        "  for (var i = 0; i < drags.length; i++) {\n"
        "    drags[i].style.touchAction = 'none';\n"
        "    drags[i].addEventListener('touchstart', function(ev) {\n"
        "      if (ev.touches.length >= 2 || !isDrawMode()) {\n"
        "        ev.stopImmediatePropagation();\n"
        "      }\n"
        "    }, {capture: true, passive: false});\n"
        "    drags[i].addEventListener('touchmove', function(ev) {\n"
        "      if (ev.touches.length >= 2 || !isDrawMode()) {\n"
        "        ev.stopImmediatePropagation();\n"
        "      }\n"
        "    }, {capture: true, passive: false});\n"
        "  }\n"
        "\n"
        "  var meta = document.querySelector('meta[name=viewport]');\n"
        "  if (!meta) { meta = document.createElement('meta');\n"
        "    meta.name = 'viewport'; document.head.appendChild(meta); }\n"
        "  meta.content = 'width=device-width,initial-scale=1.0,"
        "maximum-scale=1.0,user-scalable=no';\n"
        "\n"
        "  // Returns true if the touch point is inside the chart div\n"
        "  function isInsideGd(cx, cy) {\n"
        "    var bb = gd.getBoundingClientRect();\n"
        "    return cx >= bb.left && cx <= bb.right &&\n"
        "           cy >= bb.top  && cy <= bb.bottom;\n"
        "  }\n"
        "\n"
        "  function hitZone(cx, cy) {\n"
        "    var bb = gd.getBoundingClientRect();\n"
        "    var s = gd._fullLayout._size;\n"
        "    var px = cx - bb.left;\n"
        "    var py = cy - bb.top;\n"
        "    var plotR = s.l + s.w;\n"
        "    var plotB = s.t + s.h;\n"
        "    if (px > plotR && py >= s.t && py <= plotB) return 'price';\n"
        "    if (py > plotB && px >= s.l && px <= plotR) return 'time';\n"
        "    if (px >= s.l && px <= plotR && py >= s.t && py <= plotB) return 'plot';\n"
        "    return null;\n"
        "  }\n"
        "\n"
        "  function px2time(cx) {\n"
        "    var bb = gd.getBoundingClientRect();\n"
        "    var s = gd._fullLayout._size;\n"
        "    var frac = (cx - bb.left - s.l) / s.w;\n"
        "    var xr = gd._fullLayout.xaxis.range;\n"
        "    var t0 = new Date(xr[0]).getTime();\n"
        "    var t1 = new Date(xr[1]).getTime();\n"
        "    return t0 + frac * (t1 - t0);\n"
        "  }\n"
        "  function px2price(cy) {\n"
        "    var bb = gd.getBoundingClientRect();\n"
        "    var s = gd._fullLayout._size;\n"
        "    var frac = 1 - (cy - bb.top - s.t) / s.h;\n"
        "    var yr = gd._fullLayout.yaxis.range;\n"
        "    return yr[0] + frac * (yr[1] - yr[0]);\n"
        "  }\n"
        "  function midpoint(a, b) {\n"
        "    return { x: (a.clientX + b.clientX) / 2,\n"
        "             y: (a.clientY + b.clientY) / 2 };\n"
        "  }\n"
        "  function pinchDist(a, b) {\n"
        "    var dx = a.clientX - b.clientX;\n"
        "    var dy = a.clientY - b.clientY;\n"
        "    return Math.sqrt(dx * dx + dy * dy);\n"
        "  }\n"
        "  function snapAxes() {\n"
        "    var fl = gd._fullLayout;\n"
        "    var xr = fl.xaxis.range;\n"
        "    tc.xr0 = new Date(xr[0]).getTime();\n"
        "    tc.xr1 = new Date(xr[1]).getTime();\n"
        "    tc.yr0 = fl.yaxis.range[0];\n"
        "    tc.yr1 = fl.yaxis.range[1];\n"
        "    if (fl.yaxis2) {\n"
        "      tc.y2r0 = fl.yaxis2.range[0];\n"
        "      tc.y2r1 = fl.yaxis2.range[1];\n"
        "    } else { tc.y2r0 = undefined; }\n"
        "  }\n"
        "\n"
        "  // === TOUCH START (capture phase) ===\n"
        "  document.addEventListener('touchstart', function(e) {\n"
        "    var t0 = e.touches[0];\n"
        "    if (!isInsideGd(t0.clientX, t0.clientY)) return;\n"
        "    var n = e.touches.length;\n"
        "    var zone = hitZone(t0.clientX, t0.clientY);\n"
        "\n"
        "    // Let Plotly handle drawing-tool touches on the plot\n"
        "    if (n === 1 && zone === 'plot' && isDrawMode()) {\n"
        "      tc.mode = null; return;\n"
        "    }\n"
        "\n"
        "    // --- Two fingers → pinch-to-zoom ---\n"
        "    if (n === 2) {\n"
        "      e.preventDefault();\n"
        "      e.stopImmediatePropagation();\n"
        "      var t1 = e.touches[1];\n"
        "      var mid = midpoint(t0, t1);\n"
        "      tc.mode = 'pinch';\n"
        "      tc.dist0 = pinchDist(t0, t1);\n"
        "      tc.lastT = 0;\n"
        "      snapAxes();\n"
        "      tc.anchorT = px2time(mid.x);\n"
        "      tc.anchorP = px2price(mid.y);\n"
        "      return;\n"
        "    }\n"
        "\n"
        "    if (n !== 1) { tc.mode = null; return; }\n"
        "\n"
        "    // --- One finger on axis zones: zoom ---\n"
        "    if (zone === 'price' || zone === 'time') {\n"
        "      e.preventDefault();\n"
        "      e.stopImmediatePropagation();\n"
        "      tc.mode = zone;\n"
        "      tc.startX = t0.clientX; tc.startY = t0.clientY;\n"
        "      tc.lastT = 0;\n"
        "      snapAxes();\n"
        "      if (zone === 'time') tc.anchor = px2time(t0.clientX);\n"
        "      if (zone === 'price') tc.anchor = px2price(t0.clientY);\n"
        "      return;\n"
        "    }\n"
        "\n"
        "    // --- One finger on plot: PAN ---\n"
        "    if (zone === 'plot') {\n"
        "      e.preventDefault();\n"
        "      e.stopImmediatePropagation();\n"
        "      tc.mode = 'pan';\n"
        "      tc.startX = t0.clientX; tc.startY = t0.clientY;\n"
        "      tc.lastT = 0;\n"
        "      snapAxes();\n"
        "      tc.xSpan = tc.xr1 - tc.xr0;\n"
        "      tc.ySpan = tc.yr1 - tc.yr0;\n"
        "      tc.plotW = gd._fullLayout._size.w;\n"
        "      tc.plotH = gd._fullLayout._size.h;\n"
        "      return;\n"
        "    }\n"
        "\n"
        "    tc.mode = null;\n"
        "  }, {capture: true, passive: false});\n"
        "\n"
        "  // === TOUCH MOVE (capture phase) ===\n"
        "  document.addEventListener('touchmove', function(e) {\n"
        "    if (!tc.mode) return;\n"
        "    e.preventDefault();\n"
        "    e.stopImmediatePropagation();\n"
        "    var now = Date.now();\n"
        "    if (now - tc.lastT < 33) return;\n"
        "    tc.lastT = now;\n"
        "    var upd = {};\n"
        "\n"
        "    // --- PINCH-TO-ZOOM ---\n"
        "    if (tc.mode === 'pinch' && e.touches.length >= 2) {\n"
        "      var d = pinchDist(e.touches[0], e.touches[1]);\n"
        "      var factor = tc.dist0 / d;\n"
        "      var tLo = tc.anchorT - (tc.anchorT - tc.xr0) * factor;\n"
        "      var tHi = tc.anchorT + (tc.xr1 - tc.anchorT) * factor;\n"
        "      upd['xaxis.range[0]'] = new Date(tLo).toISOString();\n"
        "      upd['xaxis.range[1]'] = new Date(tHi).toISOString();\n"
        "      var pLo = tc.anchorP - (tc.anchorP - tc.yr0) * factor;\n"
        "      var pHi = tc.anchorP + (tc.yr1 - tc.anchorP) * factor;\n"
        "      upd['yaxis.range[0]'] = pLo;\n"
        "      upd['yaxis.range[1]'] = pHi;\n"
        "      if (tc.y2r0 !== undefined) {\n"
        "        var y2Mid = (tc.y2r0 + tc.y2r1) / 2;\n"
        "        upd['yaxis2.range[0]'] = y2Mid - (y2Mid - tc.y2r0) * factor;\n"
        "        upd['yaxis2.range[1]'] = y2Mid + (tc.y2r1 - y2Mid) * factor;\n"
        "      }\n"
        "      Plotly.relayout(gd, upd);\n"
        "      return;\n"
        "    }\n"
        "\n"
        "    if (e.touches.length !== 1) return;\n"
        "    var t = e.touches[0];\n"
        "\n"
        "    // --- PAN ---\n"
        "    if (tc.mode === 'pan') {\n"
        "      var dx = t.clientX - tc.startX;\n"
        "      var dy = t.clientY - tc.startY;\n"
        "      var dtMs = -(dx / tc.plotW) * tc.xSpan;\n"
        "      var dP   =  (dy / tc.plotH) * tc.ySpan;\n"
        "      upd['xaxis.range[0]'] = new Date(tc.xr0 + dtMs).toISOString();\n"
        "      upd['xaxis.range[1]'] = new Date(tc.xr1 + dtMs).toISOString();\n"
        "      upd['yaxis.range[0]'] = tc.yr0 + dP;\n"
        "      upd['yaxis.range[1]'] = tc.yr1 + dP;\n"
        "      Plotly.relayout(gd, upd);\n"
        "      return;\n"
        "    }\n"
        "\n"
        "    // --- AXIS-ZONE ZOOM ---\n"
        "    if (tc.mode === 'price') {\n"
        "      var dy = t.clientY - tc.startY;\n"
        "      var factor = Math.exp(dy * SENS);\n"
        "      upd['yaxis.range[0]'] = tc.anchor - (tc.anchor - tc.yr0) / factor;\n"
        "      upd['yaxis.range[1]'] = tc.anchor + (tc.yr1 - tc.anchor) / factor;\n"
        "      if (tc.y2r0 !== undefined) {\n"
        "        var y2Mid = (tc.y2r0 + tc.y2r1) / 2;\n"
        "        upd['yaxis2.range[0]'] = y2Mid - (y2Mid - tc.y2r0) / factor;\n"
        "        upd['yaxis2.range[1]'] = y2Mid + (tc.y2r1 - y2Mid) / factor;\n"
        "      }\n"
        "    } else if (tc.mode === 'time') {\n"
        "      var dx = t.clientX - tc.startX;\n"
        "      var factor = Math.exp(-dx * SENS);\n"
        "      var lo = tc.anchor - (tc.anchor - tc.xr0) / factor;\n"
        "      var hi = tc.anchor + (tc.xr1 - tc.anchor) / factor;\n"
        "      upd['xaxis.range[0]'] = new Date(lo).toISOString();\n"
        "      upd['xaxis.range[1]'] = new Date(hi).toISOString();\n"
        "    }\n"
        "    Plotly.relayout(gd, upd);\n"
        "  }, {capture: true, passive: false});\n"
        "\n"
        "  // === TOUCH END (capture phase) ===\n"
        "  document.addEventListener('touchend', function(e) {\n"
        "    if (!tc.mode) return;\n"
        "    e.stopImmediatePropagation();\n"
        "\n"
        "    // Lift from pinch → single finger → resume pan\n"
        "    if (e.touches.length === 1 && tc.mode === 'pinch') {\n"
        "      var t0 = e.touches[0];\n"
        "      tc.mode = 'pan';\n"
        "      tc.startX = t0.clientX; tc.startY = t0.clientY;\n"
        "      tc.lastT = 0;\n"
        "      snapAxes();\n"
        "      tc.xSpan = tc.xr1 - tc.xr0;\n"
        "      tc.ySpan = tc.yr1 - tc.yr0;\n"
        "      tc.plotW = gd._fullLayout._size.w;\n"
        "      tc.plotH = gd._fullLayout._size.h;\n"
        "      return;\n"
        "    }\n"
        "    if (e.touches.length === 0) tc.mode = null;\n"
        "  }, {capture: true, passive: false});\n"
        "\n"
        "  // Double-tap to reset\n"
        "  var lastTap = 0;\n"
        "  gd.addEventListener('touchend', function(e) {\n"
        "    if (e.touches.length !== 0) return;\n"
        "    var now = Date.now();\n"
        "    if (now - lastTap < 300) {\n"
        "      Plotly.relayout(gd, {'xaxis.autorange':true,\n"
        "        'yaxis.autorange':true, 'yaxis2.autorange':true});\n"
        "    }\n"
        "    lastTap = now;\n"
        "  });\n"
        "})();\n"
        "\n"
        "// ===== HORIZONTAL LINE TOOL =====\n"
        "(function() {\n"
        "  var hlineActive = false;\n"
        "  var HLINE_COLOR = '#ff9800';\n"
        "  var HLINE_WIDTH = 1.5;\n"
        "  var HLINE_DASH  = 'dash';\n"
        "  var HLINE_TAG   = 'hline_';   // prefix for annotation names\n"
        "\n"
        "  // --- Ghost preview elements (raw DOM for 60fps tracking) ---\n"
        "  var ghostLine = document.createElement('div');\n"
        "  ghostLine.style.cssText =\n"
        "    'position:absolute;left:0;right:0;height:0;'\n"
        "    + 'border-top:1.5px dashed rgba(255,152,0,0.5);'\n"
        "    + 'pointer-events:none;z-index:9998;display:none;';\n"
        "  gd.style.position = gd.style.position || 'relative';\n"
        "  gd.appendChild(ghostLine);\n"
        "\n"
        "  var ghostLabel = document.createElement('div');\n"
        "  ghostLabel.style.cssText =\n"
        "    'position:absolute;right:0;padding:2px 6px;'\n"
        "    + 'background:rgba(255,152,0,0.55);color:#fff;'\n"
        "    + 'font:11px monospace;border-radius:3px;'\n"
        "    + 'pointer-events:none;z-index:9998;display:none;'\n"
        "    + 'transform:translateY(-50%);white-space:nowrap;';\n"
        "  gd.appendChild(ghostLabel);\n"
        "\n"
        "  function showGhost(py, price) {\n"
        "    ghostLine.style.display  = 'block';\n"
        "    ghostLine.style.top      = py + 'px';\n"
        "    var s = gd._fullLayout._size;\n"
        "    ghostLine.style.left     = s.l + 'px';\n"
        "    ghostLine.style.right    = (gd.clientWidth - s.l - s.w) + 'px';\n"
        "    ghostLabel.style.display = 'block';\n"
        "    ghostLabel.style.top     = py + 'px';\n"
        "    ghostLabel.style.right   = (gd.clientWidth - s.l - s.w - 2) + 'px';\n"
        "    ghostLabel.textContent   = '$' + price.toFixed(2);\n"
        "  }\n"
        "  function hideGhost() {\n"
        "    ghostLine.style.display  = 'none';\n"
        "    ghostLabel.style.display = 'none';\n"
        "  }\n"
        "\n"
        "  // --- Inject H-Line button into the modebar ---\n"
        "  function injectBtn() {\n"
        "    var mbar = gd.querySelector('.modebar-group');\n"
        "    if (!mbar) { setTimeout(injectBtn, 200); return; }\n"
        "    var btn = document.createElement('a');\n"
        "    btn.setAttribute('data-attr', 'hline');\n"
        "    btn.setAttribute('data-val', 'hline');\n"
        "    btn.setAttribute('data-toggle', 'false');\n"
        "    btn.setAttribute('data-gravity', 's');\n"
        "    btn.className = 'modebar-btn';\n"
        "    btn.title = 'Draw horizontal price line (H)';\n"
        "    btn.style.cursor = 'pointer';\n"
        "    btn.style.position = 'relative';\n"
        '    btn.innerHTML = \'<svg viewBox="0 0 24 24" width="20" height="20">\'\n'
        '      + \'<line x1="2" y1="12" x2="22" y2="12" stroke="currentColor"\'\n'
        '      + \' stroke-width="2" stroke-dasharray="4,3"/>\'\n'
        '      + \'<circle cx="12" cy="12" r="3" fill="currentColor" opacity="0.6"/>\'\n'
        "      + '</svg>';\n"
        "    // Insert before the eraser button (last in group) or at end\n"
        "    var groups = gd.querySelectorAll('.modebar-group');\n"
        "    var drawGroup = groups.length > 1 ? groups[groups.length - 1] : groups[0];\n"
        "    drawGroup.appendChild(btn);\n"
        "\n"
        "    btn.addEventListener('click', function(e) {\n"
        "      e.stopPropagation();\n"
        "      toggleHline(!hlineActive);\n"
        "    });\n"
        "\n"
        "    // Store ref for styling\n"
        "    btn._hlineBtn = true;\n"
        "    window._hlineBtn = btn;\n"
        "  }\n"
        "  injectBtn();\n"
        "\n"
        "  function toggleHline(on) {\n"
        "    hlineActive = on;\n"
        "    var btn = window._hlineBtn;\n"
        "    if (!btn) return;\n"
        "    if (on) {\n"
        "      btn.style.background = 'rgba(255,152,0,0.25)';\n"
        "      btn.style.borderRadius = '3px';\n"
        "      gd.style.cursor = 'crosshair';\n"
        "      // Deactivate Plotly draw modes so our click handler fires\n"
        "      Plotly.relayout(gd, {dragmode: 'pan'});\n"
        "    } else {\n"
        "      btn.style.background = '';\n"
        "      gd.style.cursor = '';\n"
        "      hideGhost();\n"
        "    }\n"
        "  }\n"
        "\n"
        "  // Keyboard shortcut: 'H' to toggle h-line mode\n"
        "  document.addEventListener('keydown', function(e) {\n"
        "    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;\n"
        "    if (e.key === 'h' || e.key === 'H') {\n"
        "      if (!e.ctrlKey && !e.metaKey && !e.altKey) {\n"
        "        toggleHline(!hlineActive);\n"
        "      }\n"
        "    }\n"
        "    // Escape cancels h-line mode\n"
        "    if (e.key === 'Escape' && hlineActive) {\n"
        "      toggleHline(false);\n"
        "    }\n"
        "  });\n"
        "\n"
        "  // --- Mouse-move: update ghost preview line ---\n"
        "  gd.addEventListener('mousemove', function(e) {\n"
        "    var bb  = gd.getBoundingClientRect();\n"
        "    var s   = gd._fullLayout._size;\n"
        "    var yax = gd._fullLayout.yaxis;\n"
        "    var px  = e.clientX - bb.left;\n"
        "    var py  = e.clientY - bb.top;\n"
        "    // Use yaxis._offset/_length for price subplot only (excludes volume)\n"
        "    var inPrice = px >= s.l && px <= s.l + s.w &&\n"
        "                  py >= yax._offset && py <= yax._offset + yax._length;\n"
        "\n"
        "    // --- Ghost preview (h-line mode active) ---\n"
        "    if (hlineActive) {\n"
        "      if (inPrice) {\n"
        "        var yr = yax.range;\n"
        "        var frac = 1 - (py - yax._offset) / yax._length;\n"
        "        var price = yr[0] + frac * (yr[1] - yr[0]);\n"
        "        showGhost(py, price);\n"
        "      } else {\n"
        "        hideGhost();\n"
        "      }\n"
        "      hoverDiv.style.display = 'none';\n"
        "      return;\n"
        "    }\n"
        "\n"
        "    // --- Existing h-line hover tooltip (non-active mode) ---\n"
        "    if (!inPrice) {\n"
        "      hoverDiv.style.display = 'none'; return;\n"
        "    }\n"
        "    var shapes = gd.layout.shapes || [];\n"
        "    var yr2 = yax.range;\n"
        "    var priceAtMouse = yr2[0] + (1 - (py - yax._offset) / yax._length) * (yr2[1] - yr2[0]);\n"
        "    var hitThresh = Math.abs(yr2[1] - yr2[0]) * 0.008;\n"
        "    var closest = null;\n"
        "    var closestDist = Infinity;\n"
        "    for (var i = 0; i < shapes.length; i++) {\n"
        "      var sh = shapes[i];\n"
        "      if (!sh.name || sh.name.indexOf(HLINE_TAG) !== 0) continue;\n"
        "      var dist = Math.abs(sh.y0 - priceAtMouse);\n"
        "      if (dist < hitThresh && dist < closestDist) {\n"
        "        closest = sh; closestDist = dist;\n"
        "      }\n"
        "    }\n"
        "    if (closest) {\n"
        "      hoverDiv.textContent = '$' + closest.y0.toFixed(2);\n"
        "      hoverDiv.style.display = 'block';\n"
        "      hoverDiv.style.left = (e.clientX + 14) + 'px';\n"
        "      hoverDiv.style.top  = (e.clientY - 20) + 'px';\n"
        "    } else {\n"
        "      hoverDiv.style.display = 'none';\n"
        "    }\n"
        "  });\n"
        "  gd.addEventListener('mouseleave', function() {\n"
        "    hideGhost();\n"
        "    hoverDiv.style.display = 'none';\n"
        "  });\n"
        "\n"
        "  // --- Click handler: place h-line at clicked price ---\n"
        "  gd.addEventListener('click', function(e) {\n"
        "    if (!hlineActive) return;\n"
        "    // Convert click position to price\n"
        "    var bb  = gd.getBoundingClientRect();\n"
        "    var s   = gd._fullLayout._size;\n"
        "    var yax = gd._fullLayout.yaxis;\n"
        "    var px  = e.clientX - bb.left;\n"
        "    var py  = e.clientY - bb.top;\n"
        "    // Only place lines inside the price subplot (not volume)\n"
        "    if (px < s.l || px > s.l + s.w || py < yax._offset || py > yax._offset + yax._length) return;\n"
        "    var frac = 1 - (py - yax._offset) / yax._length;\n"
        "    var yr   = yax.range;\n"
        "    var price = yr[0] + frac * (yr[1] - yr[0]);\n"
        "    hideGhost();\n"
        "    addHline(price);\n"
        "  }, true);\n"
        "\n"
        "  // Deactivate h-line mode when any Plotly modebar button is clicked\n"
        "  gd.addEventListener('click', function(e) {\n"
        "    var mbBtn = e.target.closest('.modebar-btn');\n"
        "    if (mbBtn && !mbBtn._hlineBtn) {\n"
        "      toggleHline(false);\n"
        "    }\n"
        "  });\n"
        "\n"
        "  function addHline(price) {\n"
        "    var shapes = (gd.layout.shapes || []).slice();\n"
        "    var annots = (gd.layout.annotations || []).slice();\n"
        "    var hid = HLINE_TAG + Date.now();\n"
        "    shapes.push({\n"
        "      type: 'line',\n"
        "      xref: 'paper', x0: 0, x1: 1,\n"
        "      yref: 'y', y0: price, y1: price,\n"
        "      line: {color: HLINE_COLOR, width: HLINE_WIDTH, dash: HLINE_DASH},\n"
        "      name: hid,\n"
        "      editable: true,\n"
        "    });\n"
        "    annots.push({\n"
        "      x: 1.0, xref: 'paper', xanchor: 'left',\n"
        "      y: price, yref: 'y', yanchor: 'middle',\n"
        "      text: '$' + price.toFixed(2),\n"
        "      showarrow: false,\n"
        "      font: {color: '#fff', size: 11},\n"
        "      bgcolor: HLINE_COLOR,\n"
        "      borderpad: 3,\n"
        "      name: hid,\n"
        "    });\n"
        "    _skip = false;\n"
        "    Plotly.relayout(gd, {shapes: shapes, annotations: annots});\n"
        "  }\n"
        "\n"
        "  // --- Sync annotations when shapes change (delete / undo / redo) ---\n"
        "  function syncHlineAnnotations() {\n"
        "    var shapes = gd.layout.shapes || [];\n"
        "    var annots = (gd.layout.annotations || []).slice();\n"
        "    // Collect current hline shape names and their y-values\n"
        "    var shapeMap = {};\n"
        "    for (var i = 0; i < shapes.length; i++) {\n"
        "      var sh = shapes[i];\n"
        "      if (sh.name && sh.name.indexOf(HLINE_TAG) === 0) {\n"
        "        shapeMap[sh.name] = sh.y0;\n"
        "      }\n"
        "    }\n"
        "    // Remove stale annotations (shape was deleted)\n"
        "    var keep = [];\n"
        "    var changed = false;\n"
        "    for (var j = 0; j < annots.length; j++) {\n"
        "      var a = annots[j];\n"
        "      if (a.name && a.name.indexOf(HLINE_TAG) === 0) {\n"
        "        if (!(a.name in shapeMap)) { changed = true; continue; }\n"
        "        // Update price label if line was dragged\n"
        "        var newY = shapeMap[a.name];\n"
        "        if (Math.abs(a.y - newY) > 0.0001) {\n"
        "          a.y = newY;\n"
        "          a.text = '$' + newY.toFixed(2);\n"
        "          changed = true;\n"
        "        }\n"
        "      }\n"
        "      keep.push(a);\n"
        "    }\n"
        "    // Add annotations for shapes that don't have one yet (redo)\n"
        "    var annotNames = {};\n"
        "    for (var k = 0; k < keep.length; k++) {\n"
        "      if (keep[k].name) annotNames[keep[k].name] = true;\n"
        "    }\n"
        "    for (var name in shapeMap) {\n"
        "      if (!annotNames[name]) {\n"
        "        keep.push({\n"
        "          x: 1.0, xref: 'paper', xanchor: 'left',\n"
        "          y: shapeMap[name], yref: 'y', yanchor: 'middle',\n"
        "          text: '$' + shapeMap[name].toFixed(2),\n"
        "          showarrow: false,\n"
        "          font: {color: '#fff', size: 11},\n"
        "          bgcolor: HLINE_COLOR,\n"
        "          borderpad: 3,\n"
        "          name: name,\n"
        "        });\n"
        "        changed = true;\n"
        "      }\n"
        "    }\n"
        "    if (changed) {\n"
        "      _skip = true;\n"
        "      Plotly.relayout(gd, {annotations: keep});\n"
        "      _skip = false;\n"
        "    }\n"
        "  }\n"
        "\n"
        "  // Hook into relayout to keep annotations in sync\n"
        "  gd.on('plotly_relayout', function(ed) {\n"
        "    var keys = Object.keys(ed || {});\n"
        "    var isShape = keys.some(function(k) {\n"
        "      return k === 'shapes' || k.indexOf('shapes[') === 0;\n"
        "    });\n"
        "    if (isShape) setTimeout(syncHlineAnnotations, 50);\n"
        "  });\n"
        "\n"
        "  // --- Hover tooltip near placed h-lines ---\n"
        "  var hoverDiv = document.createElement('div');\n"
        "  hoverDiv.style.cssText =\n"
        "    'position:fixed;pointer-events:none;padding:4px 8px;'\n"
        "    + 'background:rgba(30,34,45,0.92);color:#ff9800;'\n"
        "    + 'font:12px monospace;border:1px solid #ff9800;'\n"
        "    + 'border-radius:4px;z-index:10000;display:none;';\n"
        "  document.body.appendChild(hoverDiv);\n"
        "\n"
        "  // --- Rebuild annotations on page load from restored shapes ---\n"
        "  setTimeout(function() {\n"
        "    var shapes = gd.layout.shapes || [];\n"
        "    var hasHlines = shapes.some(function(s) {\n"
        "      return s.name && s.name.indexOf(HLINE_TAG) === 0;\n"
        "    });\n"
        "    if (hasHlines) syncHlineAnnotations();\n"
        "  }, 300);\n"
        "})();\n"
        "\n"
        "// Status bar\n"
        "var bar = document.createElement('div');\n"
        "bar.style.cssText = "
        "'position:fixed;bottom:0;left:0;right:0;height:28px;"
        "background:#1e222d;color:#9598a1;font:12px monospace;"
        "display:flex;align-items:center;padding:0 12px;"
        "justify-content:space-between;z-index:9999;';\n"
        "bar.innerHTML = '"
        "<span>" + ticker + " | " + candle_bar_label + " " + period + "</span>"
        '<span style="color:#4caf50">Drawings auto-saved to browser</span>'
        "<span>H=HLine | Scroll=Zoom | Touch: Drag=Pan, Pinch=Zoom | Axis Drag=Scale | 2xTap=Reset</span>';\n"
        "document.body.appendChild(bar);\n"
        "document.body.style.marginBottom = '28px';\n"
    )


def _add_volume_profile(
    fig: go.Figure,
    raw_data: pd.DataFrame,
    lookback: str | None = None,
    num_bins: int = 60,
    n_subplot_rows: int = 2,
) -> None:
    """Overlay a single volume-at-price histogram on the price subplot.

    The histogram covers exactly the display window defined by
    *lookback* (e.g. '1y', '6mo').  Bars are rendered horizontally on a
    secondary x-axis that overlays the price chart, anchored to the
    left edge of the y-axis.

    The overlay axis number is chosen dynamically to avoid collisions
    with axes created by ``make_subplots``.

    Args:
        fig: Plotly Figure to add the trace to.
        raw_data: OHLC DataFrame with High, Low, Close, Volume columns
                  and a DatetimeIndex.
        lookback: Display window ('1mo', '3mo', '6mo', '1y', '2y', '5y',
                  'max', or None).  ``None`` / ``'max'`` uses all data.
        num_bins: Number of horizontal price bins.
        n_subplot_rows: Number of subplot rows in the figure, used to
                        pick a non-conflicting overlay axis number.
    """
    import pandas as pd

    if raw_data.empty or len(raw_data) < 2:
        return

    # --- Slice data to the lookback window ---------------------------
    _lookback_offsets = {
        "1mo": pd.DateOffset(months=1),
        "3mo": pd.DateOffset(months=3),
        "6mo": pd.DateOffset(months=6),
        "1y": pd.DateOffset(years=1),
        "2y": pd.DateOffset(years=2),
        "5y": pd.DateOffset(years=5),
    }
    offset = _lookback_offsets.get(lookback) if lookback else None
    if offset is not None and len(raw_data) > 0:
        cutoff = raw_data.index[-1] - offset
        window = raw_data.loc[raw_data.index >= cutoff]
    else:
        # "max" or None — use everything (cap at 2000 bars for perf)
        window = raw_data.iloc[-2000:] if len(raw_data) > 2000 else raw_data

    if window.empty or len(window) < 2:
        return

    highs = window["High"].values.astype(float)
    lows = window["Low"].values.astype(float)
    volumes = window["Volume"].values.astype(float)

    price_min = float(np.nanmin(lows))
    price_max = float(np.nanmax(highs))
    if price_max <= price_min:
        return

    edges = np.linspace(price_min, price_max, num_bins + 1)
    bin_centres = (edges[:-1] + edges[1:]) / 2.0
    vol_at_price = np.zeros(num_bins, dtype=float)

    # Distribute each candle's volume across the price bins it spans
    for h, lo, v in zip(highs, lows, volumes, strict=False):
        if np.isnan(h) or np.isnan(lo) or np.isnan(v) or v <= 0:
            continue
        mask = (edges[:-1] < h) & (edges[1:] > lo)
        n_hit = mask.sum()
        if n_hit > 0:
            vol_at_price[mask] += v / n_hit

    if vol_at_price.max() == 0:
        return

    # Normalise so widest bar = 1.0
    norm = vol_at_price / vol_at_price.max()
    bin_height = edges[1] - edges[0]

    # Highlight the Point of Control (POC) — highest-volume bin
    poc_idx = int(np.argmax(vol_at_price))
    bar_colors = [
        "rgba(255, 235, 59, 0.45)" if i == poc_idx else "rgba(41, 98, 255, 0.25)"
        for i in range(num_bins)
    ]

    # Choose an overlay axis number that won't collide with the axes
    # created by make_subplots (which uses xaxis, xaxis2, …, xaxis{n}).
    vp_axis_num = n_subplot_rows + 1  # e.g. 3 rows → xaxis4
    vp_xref = f"x{vp_axis_num}"  # trace reference: "x4"
    vp_layout_key = f"xaxis{vp_axis_num}"  # layout key: "xaxis4"

    # Add trace directly (without row/col) so Plotly doesn't override
    # the xaxis assignment back to "x".
    fig.add_trace(
        go.Bar(
            y=bin_centres,
            x=norm,
            orientation="h",
            marker_color=bar_colors,
            marker_line_width=0,
            width=bin_height * 0.9,
            name="Vol Profile",
            hovertemplate=("Price: $%{y:.2f}<br>" "Rel Volume: %{x:.1%}<extra></extra>"),
            showlegend=False,
            xaxis=vp_xref,
            yaxis="y",
        ),
    )

    # Secondary x-axis overlaid on the price subplot (invisible scale).
    # Applied AFTER the broad fig.update_xaxes() call so it isn't
    # overridden.
    fig.update_layout(
        **{
            vp_layout_key: dict(
                overlaying="x",
                side="top",
                range=[0, 5],  # bars fill ≤20% of chart width
                showgrid=False,
                showticklabels=False,
                zeroline=False,
                fixedrange=True,
                showspikes=False,
                anchor="y",
                automargin=False,
            )
        },
    )


__all__ = [
    "build_interactive_figure",
    "get_interactive_config",
    "get_post_script",
]
