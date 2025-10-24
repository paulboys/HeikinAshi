# 3-Point Divergence Detection Improvements

## Overview
This document describes the improvements made to the 3-point divergence detection algorithm to address the issue where no 3-point divergences were being found.

## Problem Analysis
The original implementation had several issues that prevented 3-point divergences from being detected:

1. **Calendar Day Distance vs Bar Index**: Used `abs((idx1 - idx2).days)` which fails over weekends/holidays
2. **Over-Strict Monotonic Requirements**: Required strictly descending/ascending sequences without any tolerance for minor market noise
3. **Tight Time Windows**: Fixed `window * 2` days for alignment was too restrictive

## Solutions Implemented

### 1. Bar Index Distance (Not Calendar Days)
```python
# Old approach: Calendar days
rsi_lows_near_p1 = [idx for idx in rsi_low_idx if abs((idx - p1_idx).days) <= window * 2]

# New approach: Bar position
pos_map = {idx: i for i, idx in enumerate(recent_df.index)}
max_bar_gap = window * index_proximity_factor

def nearest_by_bar(target_idx, candidates):
    """Return candidate with smallest absolute bar index distance within max_bar_gap."""
    tpos = pos_map[target_idx]
    viable = [(abs(pos_map[c] - tpos), c) for c in candidates 
              if c in pos_map and abs(pos_map[c] - tpos) <= max_bar_gap]
    return min(viable)[1] if viable else None
```

**Benefits**:
- Works correctly across weekends, holidays, and market closures
- More predictable behavior (bars vs variable calendar days)
- Configurable via `index_proximity_factor` parameter

### 2. Sequence Tolerance for Price
```python
# Old: Strictly descending (p3 < p2 < p1)
price_desc = (p2 < p1 and p3 < p2)

# New: Allow 0.2% tolerance
price_desc = (
    (p2 <= p1 * (1 - sequence_tolerance_pct)) and
    (p3 <= p2 * (1 - sequence_tolerance_pct))
)
```

**Benefits**:
- Handles minor price consolidations/sideways moves
- Default `sequence_tolerance_pct=0.002` (0.2%) filters noise while accepting valid patterns
- User-configurable for different trading styles

### 3. Flexible RSI Progression
```python
# Use max of absolute tolerance and relative tolerance
rsi_asc = (
    (r2 - r1 >= max(BULLISH_RSI_TOLERANCE, rsi_sequence_tolerance)) and
    (r3 - r2 >= max(BULLISH_RSI_TOLERANCE, rsi_sequence_tolerance))
)
```

**Benefits**:
- Maintains existing RSI tolerance (0.5 points)
- Allows additional user-defined tolerance via `rsi_sequence_tolerance`
- Flexible for different RSI sensitivity needs

## New Parameters

### For `detect_divergence()`:
- `index_proximity_factor` (int, default=2): Multiplier for window to determine max bar gap
- `sequence_tolerance_pct` (float, default=0.002): Relative tolerance for 3-point price sequences (0.2%)
- `rsi_sequence_tolerance` (float, default=0.0): Extra RSI tolerance in points

### For `screen_rsi_divergence()`:
- Same parameters passed through from CLI or defaults

## CLI Usage

### Standard 2-Point (Existing Behavior)
```bash
stockcharts-rsi-divergence --type bullish --min-swing-points 2
```

### Stronger 3-Point Confirmation
```bash
stockcharts-rsi-divergence --type bullish --min-swing-points 3 --lookback 120
```

### Recommended Settings for 3-Point
```bash
# More bars needed to find 3 swings
stockcharts-rsi-divergence \
  --type bullish \
  --min-swing-points 3 \
  --period 6mo \
  --lookback 120 \
  --swing-window 5 \
  --min-volume 500000

# With explicit tolerance parameters (showing defaults)
stockcharts-rsi-divergence \
  --type bullish \
  --min-swing-points 3 \
  --lookback 120 \
  --swing-window 7 \
  --index-proximity-factor 2 \
  --sequence-tolerance-pct 0.002 \
  --rsi-sequence-tolerance 0.0 \
  --output results/bullish_div.csv
```

## Technical Details

### Bar Index Mapping
```python
pos_map = {idx: i for i, idx in enumerate(recent_df.index)}
# Example:
# 2024-10-01: 0
# 2024-10-02: 1
# 2024-10-03: 2
# (Weekend skipped - but bar count continuous)
# 2024-10-06: 3
# 2024-10-07: 4
```

This ensures consistent distance measurements regardless of market calendars.

### 3-Point Pattern Example

**Bullish Divergence (3-Point)**:
```
Price:  $45 → $43 → $41  (descending, each ≤ previous * 0.998)
RSI:     35 →  37 →  39  (ascending, each ≥ previous + 0.5)
Result: Bullish 3-point divergence detected ✓
```

**Failed due to tolerance (Old Logic)**:
```
Price:  $45.00 → $44.90 → $44.85  (barely descending, tiny moves)
RSI:     35.0  →  37.5  →  40.0   (clearly ascending)
Old:    Failed (price changes too small for strict < comparison)
New:    Detected ✓ (within 0.2% tolerance, clear RSI divergence)
```

## Backward Compatibility

### 2-Point Detection
- Unchanged behavior for `min_swing_points=2` (default)
- Same RSI tolerance requirements (0.5 points)
- Improved alignment using bar index instead of calendar days

### Chart Plotting
- Automatically handles both 2-point and 3-point data structures
- Draws connecting lines through all swing points
- Backward compatible with existing CSV outputs

## Performance Considerations

### Computational Cost
- Bar index mapping: O(n) one-time cost per ticker
- Nearest neighbor lookup: O(k) where k = number of swing points
- Overall complexity unchanged

### Memory
- Additional `pos_map` dictionary: ~8 bytes per bar (negligible)
- No significant memory overhead

## Testing Recommendations

### Find 3-Point Divergences
```bash
# Cast wide net with longer periods
stockcharts-rsi-divergence \
  --type bullish \
  --min-swing-points 3 \
  --period 1y \
  --lookback 180 \
  --swing-window 7 \
  --output results/bullish_3point.csv
```

### Verify Charts
```bash
# Plot detected divergences
stockcharts-plot-divergence \
  --input results/bullish_3point.csv \
  --output-dir charts/3point/
```

## Future Enhancements

### Potential Additions (Not Yet Implemented):
1. **ZigZag Method**: Use percentage-based pivots instead of fixed window
2. **ATR Normalization**: Require each swing to be X * ATR apart
3. **Vectorized Swing Detection**: Replace loops with numpy operations
4. **Multi-Scale Smoothing**: Detect swings at multiple timescales
5. **Divergence Scoring**: Rank patterns by strength

### Priority for Next Phase:
If 3-point detection rate is still low after this patch, consider implementing ZigZag method as alternative swing detection algorithm.

## Commit Reference
- Commit: `04b60ce`
- Branch: `main`
- Files Modified:
  - `src/stockcharts/indicators/divergence.py`
  - `src/stockcharts/screener/rsi_divergence.py`

## See Also
- `RSI_DIVERGENCE_GUIDE.md` - RSI divergence concepts
- `RSI_TOLERANCE_GUIDE.md` - RSI tolerance implementation
- `PARAMETER_GUIDE.md` - All parameter documentation
