# Changelog
All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
- (placeholder) Add MACD divergence support
- (placeholder) Average volume filter (20-day)

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

[Unreleased]: https://github.com/paulboys/HeikinAshi/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/paulboys/HeikinAshi/releases/tag/v0.4.0
