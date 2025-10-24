# Changelog
All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
- (placeholder) Add MACD divergence support
- (placeholder) Average volume filter (20-day)

## [0.5.0] - 2025-10-24
### Added
- **EMA-Derivative Pivot Detection**: New pivot method using EMA smoothing and slope sign changes
  - More robust than window-based swing detection for noisy data
  - Simpler: 2 parameters (price_span, rsi_span) vs 6+ for ZigZag
  - `--pivot-method ema-deriv` with `--ema-price-span` and `--ema-rsi-span` flags
- **3-Point Divergence Detection**: Enhanced confirmation with 3 consecutive swing points
  - `--min-swing-points {2,3}` parameter (default: 2)
  - Bar-index based alignment (handles weekends/holidays correctly)
  - Sequence tolerance parameters for flexible pattern matching
- **Advanced Tolerance Parameters**:
  - `--index-proximity-factor`: Bar gap tolerance multiplier (default: 2)
  - `--sequence-tolerance-pct`: Price sequence tolerance for 3-point (default: 0.002 = 0.2%)
  - `--rsi-sequence-tolerance`: Extra RSI tolerance for 3-point patterns (default: 0.0)
- **Breakout Filtering**: Filter out stale or failed divergence signals
  - `--exclude-breakouts`: Remove divergences where price already moved past threshold
  - `--exclude-failed-breakouts`: Remove divergences with attempted but reversed breakouts
  - Configurable thresholds for both filters
- **Documentation**:
  - `THREE_POINT_DIVERGENCE_IMPROVEMENTS.md`: Technical details on 3-point improvements
  - `EMA_DERIVATIVE_PIVOT_GUIDE.md`: Complete guide to EMA-derivative method
  - Parameter tuning guides for different trading styles

### Changed
- **Pivot Detection Architecture**: Refactored to support pluggable pivot methods
  - Created `src/stockcharts/indicators/pivots.py` module
  - Updated `detect_divergence()` to accept multiple pivot methods
- **Alignment Logic**: Switched from calendar days to bar-index distance
  - More reliable across market holidays and weekends
  - Configurable proximity factor for flexibility

### Removed
- **ZigZag Module**: Removed `src/stockcharts/indicators/zigzag.py`
  - Overly complex with poor results
  - Replaced by simpler, more effective EMA-derivative method
  - Reduced codebase by ~200 lines

### Fixed
- Weekend/holiday alignment issues in swing point pairing
- Over-strict monotonic requirements for 3-point patterns
- Missing 3-point divergences due to tight tolerance

### Performance
- EMA-derivative method: O(n) complexity, faster than nested window loops
- Bar-index mapping: O(n) preprocessing, O(1) lookup

## [0.4.1] - 2025-10-20
### Changed
- Version bump to test automated PyPI publish workflow trigger.
- Verified packaging integrity after tolerance and documentation consolidation changes.

### CI/CD
- Tag-based publish workflow executed with PyPI token secret.

### Notes
- No functional code changes beyond version increment; this is a release process validation.

## [0.4.0] - 2025-10-19
### Added
- Consolidated documentation into `docs/` directory (overview, screener, divergence, parameters, volume, trading styles, quick reference, roadmap, legacy mapping, deprecation notice).
- MkDocs site with Material theme and GitHub Pages deployment workflow.
- RSI divergence tolerance (0.5 point thresholds) to reduce false positives (e.g., PLTR case).
- Volume filter parameter (`--min-volume`) for RSI divergence screener.
- Precomputed divergence indices to ensure chart marker alignment.
- Input filter (`--input-filter`) to intersect screener outputs.

### Changed
- README updated with Hosted Documentation section and consolidated doc references.
- Divergence detection logic now requires minimum RSI difference to signal.

### Removed
- Legacy root markdown files (replaced by consolidated docs).

### Fixed
- False bearish divergence detection where RSI made a slightly higher high.
- Heiken Ashi screener color change edge cases (accurate bullish/bearish identification).

### Documentation
- Added `DEPRECATION_NOTICE.md` and `legacy.md` mapping old to new files.

## [0.3.0] - 2025-09-XX
### Added
- Initial RSI divergence screener and chart plotting.
- Heiken Ashi NASDAQ screener.

[Unreleased]: https://github.com/paulboys/HeikinAshi/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/paulboys/HeikinAshi/releases/tag/v0.4.1
[0.4.0]: https://github.com/paulboys/HeikinAshi/releases/tag/v0.4.0
