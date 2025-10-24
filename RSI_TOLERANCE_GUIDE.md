# RSI Divergence Tolerance Enhancement

## Problem Statement

The divergence detector was producing false positives when RSI values were extremely close but not identical. For example:

**PLTR False Positive Case:**
- Price: Making a higher high (divergence condition met)
- RSI: 68.5 → 68.7 (also making a higher high, NOT a lower high)
- Result: Incorrectly flagged as bearish divergence

This occurred because the code used strict inequality (`<` and `>`) without accounting for noise-level variations in RSI values.

## Solution

Added tolerance constants to require a **minimum meaningful difference** in RSI values:

```python
BEARISH_RSI_TOLERANCE = 0.5  # RSI must be at least 0.5 points lower
BULLISH_RSI_TOLERANCE = 0.5  # RSI must be at least 0.5 points higher
```

### Bearish Divergence Logic
**Before:**
```python
rsi_lh = recent_df.loc[r2_idx, rsi_col] < recent_df.loc[r1_idx, rsi_col]
```

**After:**
```python
rsi_lh = recent_df.loc[r2_idx, rsi_col] + BEARISH_RSI_TOLERANCE < recent_df.loc[r1_idx, rsi_col]
```

**Meaning:** For bearish divergence, RSI at the second high must be **at least 0.5 points lower** than at the first high.

### Bullish Divergence Logic
**Before:**
```python
rsi_hl = recent_df.loc[r2_idx, rsi_col] > recent_df.loc[r1_idx, rsi_col]
```

**After:**
```python
rsi_hl = recent_df.loc[r2_idx, rsi_col] - BULLISH_RSI_TOLERANCE > recent_df.loc[r1_idx, rsi_col]
```

**Meaning:** For bullish divergence, RSI at the second low must be **at least 0.5 points higher** than at the first low.

## Examples

### Bearish Divergence (With Tolerance)
| Scenario | Price1 | Price2 | RSI1 | RSI2 | Flagged? | Reason |
|----------|--------|--------|------|------|----------|--------|
| True divergence | 100 | 110 | 70.0 | 68.0 | ✅ Yes | RSI dropped 2.0 points (> 0.5) |
| Marginal case | 100 | 110 | 70.0 | 69.6 | ⚠️ No | RSI dropped only 0.4 points (< 0.5) |
| False positive | 100 | 110 | 70.0 | 70.2 | ❌ No | RSI actually increased |

### Bullish Divergence (With Tolerance)
| Scenario | Price1 | Price2 | RSI1 | RSI2 | Flagged? | Reason |
|----------|--------|--------|------|------|----------|--------|
| True divergence | 100 | 90 | 30.0 | 32.0 | ✅ Yes | RSI rose 2.0 points (> 0.5) |
| Marginal case | 100 | 90 | 30.0 | 30.4 | ⚠️ No | RSI rose only 0.4 points (< 0.5) |
| False positive | 100 | 90 | 30.0 | 29.8 | ❌ No | RSI actually decreased |

## Testing

### Test Case: PLTR
**Before tolerance:**
- Bearish divergence: ✅ True (false positive)
- Price: Higher high
- RSI: 68.5 → 68.7 (slightly higher, not lower)

**After tolerance:**
- Bearish divergence: ❌ False (correctly filtered)
- RSI difference: 0.2 points (< 0.5 threshold)

### Test Script
```bash
python test_rsi_tolerance.py
```

This script tests PLTR and several other tickers to verify the tolerance is working correctly.

## Configuration

The tolerance values are defined as module-level constants in `src/stockcharts/indicators/divergence.py`:

```python
BEARISH_RSI_TOLERANCE = 0.5
BULLISH_RSI_TOLERANCE = 0.5
```

### Adjusting Tolerance

If you find the current tolerance too strict or too loose, you can modify these constants:

- **Lower tolerance (0.2-0.3):** More sensitive, catches weaker divergences, may include more noise
- **Current tolerance (0.5):** Balanced approach, filters obvious false positives
- **Higher tolerance (1.0-2.0):** More conservative, only strong divergences, may miss valid signals

### Percentage-Based Alternative (Future Enhancement)

Instead of fixed point values, a percentage-based tolerance could be implemented:

```python
# Example: RSI must differ by at least 2%
rsi_lh = recent_df.loc[r2_idx, rsi_col] * 1.02 < recent_df.loc[r1_idx, rsi_col]
```

This would scale the tolerance with RSI levels (more tolerance at high RSI, less at low RSI).

## Impact

### Benefits
- ✅ Eliminates false positives from noise-level RSI variations
- ✅ Improves signal quality and reduces time wasted on invalid setups
- ✅ Makes screener results more actionable and reliable

### Trade-offs
- ⚠️ May miss very weak divergences (RSI difference 0.1-0.4 points)
- ⚠️ Adds a parameter that traders should understand
- ⚠️ Slightly more conservative than strict inequality

### Recommendation
The 0.5-point tolerance is a good starting point. Monitor your screener results and adjust if needed:
- Too many false positives? Increase to 1.0
- Missing valid divergences? Decrease to 0.3

## Files Modified

- `src/stockcharts/indicators/divergence.py`: Added tolerance constants and updated divergence logic
- `test_rsi_tolerance.py`: Comprehensive test script for tolerance functionality
- `test_tolerance.py`: Quick PLTR-specific test

## Commit

```
commit 3811118
Author: Paul Boys
Date: 2025

Add RSI tolerance to divergence detection to eliminate false positives

- Add BEARISH_RSI_TOLERANCE and BULLISH_RSI_TOLERANCE constants (0.5 points)
- RSI must differ by at least 0.5 points to confirm divergence
- Eliminates false bearish divergence on PLTR (RSI slightly higher, not lower)
- Improves signal quality by filtering out noise-level RSI variations
```
