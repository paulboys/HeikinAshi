# 3-Point Sequence Scoring Guide

## Overview

The **3-point sequence scoring** feature provides ATR-normalized quality filtering for divergence patterns. Instead of accepting any 3 consecutive pivot points, it:

1. **Scores** each candidate triple based on price magnitude (normalized by ATR) and RSI divergence
2. **Filters** by minimum ATR-normalized movement to avoid noise
3. **Returns** only the highest-conviction patterns above your threshold

## When to Use

✅ **Enable scoring when:**
- You're getting too many low-quality divergence signals
- You want to focus on the strongest setups only
- You're using EMA-derivative pivots (works best with smooth pivots)
- You need to rank multiple divergences by conviction

❌ **Disable scoring when:**
- You want to see all possible 3-point patterns
- You're using very strict tolerance parameters already
- You prefer manual filtering from a larger result set

## Quick Start

### Basic Usage (Recommended Settings)

```bash
stockcharts-rsi-divergence \
  --type bullish \
  --pivot-method ema-deriv \
  --min-swing-points 3 \
  --use-sequence-scoring \
  --min-sequence-score 1.0 \
  --min-magnitude-atr-mult 0.5 \
  --ema-price-span 7 \
  --ema-rsi-span 7
```

### Conservative (High-Quality Only)

```bash
stockcharts-rsi-divergence \
  --type all \
  --pivot-method ema-deriv \
  --min-swing-points 3 \
  --use-sequence-scoring \
  --min-sequence-score 2.0 \
  --min-magnitude-atr-mult 0.7 \
  --max-bar-gap 8
```

### Aggressive (More Signals)

```bash
stockcharts-rsi-divergence \
  --type all \
  --pivot-method ema-deriv \
  --min-swing-points 3 \
  --use-sequence-scoring \
  --min-sequence-score 0.5 \
  --min-magnitude-atr-mult 0.3 \
  --max-bar-gap 15
```

## Parameters

### Core Scoring Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--use-sequence-scoring` | `False` | Enable the scoring system |
| `--min-sequence-score` | `1.0` | Minimum score to accept a pattern |
| `--min-magnitude-atr-mult` | `0.5` | Minimum price move as multiple of ATR |
| `--atr-period` | `14` | Period for ATR calculation |
| `--max-bar-gap` | `10` | Max bars between price/RSI pivots |

### Score Interpretation

**Score Components:**
```
score = (price_span / ATR) + (RSI_delta / 10)
```

- **0.5 - 1.5**: Weak to moderate signal
- **1.5 - 3.0**: Moderate to strong signal  
- **3.0+**: Very strong, high-conviction signal

**Example from Real Data:**
```
MSFT: score=4.71 (very strong)
  Price 450.18→491.09→505.27 (ascending)
  RSI 70.97→69.37→65.01 (descending)
  
NVDA: score=2.47 (strong)
  Price 167.03→173.72→180.45 (ascending)
  RSI 75.44→71.11→65.77 (descending)
```

## How It Works

### 1. Find Pivot Candidates

Uses EMA-derivative (or swing) method to find pivot points:

```python
pivots = ema_derivative_pivots(df, price_span=7, rsi_span=7)
# Returns: price_highs, price_lows, rsi_highs, rsi_lows
```

### 2. Form Triple Sequences

Slides window of 3 consecutive pivots:
- For bearish: 3 consecutive price highs, 3 consecutive RSI highs
- For bullish: 3 consecutive price lows, 3 consecutive RSI lows

### 3. Map Price → RSI Pivots

Each price pivot mapped to nearest RSI pivot within `max_bar_gap`:
```python
# Example: price high on Sep 9 maps to RSI high on Sep 10
# Bar distance = 1, within max_bar_gap=10 ✓
```

### 4. Apply Filters

**Monotonicity Check:**
- Bearish: price must ascend (p1 < p2 < p3), RSI must descend (r1 > r2 > r3)
- Bullish: price must descend, RSI must ascend
- Tolerance: `sequence_tolerance_pct` allows small violations

**Magnitude Filter:**
- At least one price leg (p1→p2 or p2→p3) must exceed `min_magnitude_atr_mult * ATR`
- Prevents tiny, insignificant moves from passing

### 5. Score and Rank

```python
# Normalize price spans by ATR
normalized_price = (span12 + span23) / (ATR * 2)

# Scale RSI contribution
normalized_rsi = (r2-r1 + r3-r2) / 10  # for bullish

# Total score
score = normalized_price + normalized_rsi
```

Higher scores = stronger patterns. Returns top candidate above `min_sequence_score`.

## Tuning Guide

### Finding Too Few Signals?

**Loosen these:**
- `--min-sequence-score 0.5` (from 1.0)
- `--min-magnitude-atr-mult 0.3` (from 0.5)
- `--max-bar-gap 15` (from 10)
- `--sequence-tolerance-pct 0.01` (from 0.002)

**Example:**
```bash
stockcharts-rsi-divergence \
  --use-sequence-scoring \
  --min-sequence-score 0.5 \
  --min-magnitude-atr-mult 0.3 \
  --max-bar-gap 15
```

### Finding Too Many Low-Quality Signals?

**Tighten these:**
- `--min-sequence-score 2.0` (from 1.0)
- `--min-magnitude-atr-mult 0.7` (from 0.5)
- `--max-bar-gap 8` (from 10)

**Example:**
```bash
stockcharts-rsi-divergence \
  --use-sequence-scoring \
  --min-sequence-score 2.0 \
  --min-magnitude-atr-mult 0.7 \
  --max-bar-gap 8
```

### Alignment Issues?

If price/RSI pivots not aligning well:
- Increase `--max-bar-gap` (allows further-separated pivots)
- Use same EMA span for both: `--ema-price-span 7 --ema-rsi-span 7`
- Try longer lookback: `--lookback 120`

## Python API

```python
from stockcharts.indicators.divergence import detect_divergence, find_three_point_sequences

# High-level: integrated scoring
result = detect_divergence(
    df,
    pivot_method='ema-deriv',
    min_swing_points=3,
    use_sequence_scoring=True,
    min_sequence_score=1.0,
    min_magnitude_atr_mult=0.5,
    max_bar_gap=10,
    ema_price_span=7,
    ema_rsi_span=7
)

print(f"Bullish score: {result['bullish_score']:.2f}")
print(f"Details: {result['bullish_details']}")

# Low-level: direct sequence finding
from stockcharts.indicators.pivots import ema_derivative_pivots

pivots = ema_derivative_pivots(df, price_span=7, rsi_span=7)

candidates = find_three_point_sequences(
    df,
    price_idx=pivots['price_lows'],
    rsi_idx=pivots['rsi_lows'],
    kind='low',  # bullish divergence
    min_sequence_score=1.0,
    min_magnitude_atr_mult=0.5
)

for cand in candidates[:5]:  # top 5
    print(f"Score: {cand['score']:.2f}")
    print(f"Price: {cand['price_vals']}")
    print(f"RSI: {cand['rsi_vals']}")
```

## Performance Notes

- **Complexity**: O(n) for n pivots (far fewer than total bars)
- **Memory**: Minimal, operates on pivot indices only
- **Speed**: Adds ~10-50ms per stock for typical pivot counts
- **Vectorized**: ATR computed once via pandas rolling operations

## Best Practices

1. **Start with defaults** (`min_sequence_score=1.0`, `min_magnitude_atr_mult=0.5`)
2. **Use EMA-derivative pivots** for best results (smoother than swing)
3. **Match EMA spans** (`--ema-price-span 7 --ema-rsi-span 7`) for better alignment
4. **Review scores** in output to understand signal quality
5. **Backtest thresholds** on your watchlist to find optimal settings
6. **Combine with volume filter** (`--min-volume`) to avoid illiquid stocks

## Comparison: Standard vs Scoring

### Standard 3-Point Detection
```
AAPL: Price 234.35→254.04 (HH) | RSI 66.87→60.85 (LH)
MSFT: No divergence
NVDA: No divergence  
AMZN: No divergence
```
✗ Finds only 2-point patterns  
✗ Misses higher-quality 3-point setups

### With Sequence Scoring
```
AAPL: score=1.17 - Price 226.01→227.16→229.72 | RSI 68.71→68.71→60.41
MSFT: score=4.71 - Price 450.18→491.09→505.27 | RSI 70.97→69.37→65.01
NVDA: score=2.47 - Price 167.03→173.72→180.45 | RSI 75.44→71.11→65.77
AMZN: score=1.22 - Price 212.10→212.52→219.36 | RSI 61.90→61.98→57.89
```
✓ Finds true 3-point patterns  
✓ Ranks by conviction  
✓ Filters noise via ATR normalization

## Related Documentation

- [EMA Derivative Pivot Guide](EMA_DERIVATIVE_PIVOT_GUIDE.md) - Pivot detection method
- [3-Point Divergence Improvements](THREE_POINT_DIVERGENCE_IMPROVEMENTS.md) - Bar-index alignment
- [Parameter Guide](PARAMETER_GUIDE.md) - All CLI parameters
- [Trading Style Guide](TRADING_STYLE_GUIDE.md) - Strategy-specific settings

## Support

- **GitHub Issues**: https://github.com/paulboys/HeikinAshi/issues
- **Discussions**: https://github.com/paulboys/HeikinAshi/discussions
- **Examples**: See `examples/` directory for usage patterns
