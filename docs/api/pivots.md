# Pivot Detection

::: stockcharts.indicators.pivots
    options:
      show_root_heading: true
      heading_level: 2

---

## EMA-Derivative Method (Merged Guide)

Replaces earlier ZigZag approach for cleaner, parameter-light pivot extraction.

### Logic
1. Smooth series with EMA (price & RSI).
2. Compute first derivative (rate of change).
3. Sign change identifies pivot (negative→positive = low, positive→negative = high).

### Advantages
- Minimal parameters (span only).
- Robust against noise.
- Symmetric application to price & RSI.
- Linear complexity.

### Span Selection
| Span | Sensitivity | Use Case |
|------|-------------|----------|
| 3-4  | High        | Intraday/fast scans |
| 5-6  | Balanced    | Swing trading (default) |
| 7-9  | Smooth      | Position trading |
| 10+  | Very Smooth | Major turns only |

### CLI Flags
```
--pivot-method ema-deriv --ema-price-span N --ema-rsi-span N
```

### Example
```
stockcharts-rsi-divergence --type bullish --pivot-method ema-deriv --ema-price-span 7 --ema-rsi-span 7
```

### Future Enhancements
Adaptive spans, derivative thresholding, multi-span confirmation.
