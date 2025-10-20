# Release v0.4.0

Date: 2025-10-19
Tag: v0.4.0

## Highlights
Consolidated documentation, MkDocs site launch, improved RSI divergence accuracy, and enhanced screening filters.

## Added
- Consolidated documentation into `docs/` directory (overview, screener, divergence, parameters, volume, trading styles, quick reference, roadmap, legacy mapping, deprecation notice).
- MkDocs site with Material theme and GitHub Pages deployment workflow.
- RSI divergence tolerance (0.5 point thresholds) to reduce false positives (e.g., PLTR case).
- Volume filter parameter (`--min-volume`) for RSI divergence screener.
- Precomputed divergence indices to ensure chart marker alignment.
- Input filter (`--input-filter`) to intersect screener outputs.

## Changed
- README updated with Hosted Documentation section and consolidated doc references.
- Divergence detection logic now requires minimum RSI difference to signal.

## Removed
- Legacy root markdown files (replaced by consolidated docs).

## Fixed
- False bearish divergence detection where RSI made a slightly higher high.
- Heiken Ashi screener color change edge cases (accurate bullish/bearish identification).

## Documentation
- Added `DEPRECATION_NOTICE.md` and `legacy.md` mapping old to new files.

## Upgrade Notes
After upgrading to 0.4.0:
- Use consolidated docs under `docs/` or visit the published site.
- Adjust RSI tolerance in `divergence.py` if you need more/less strict divergence filtering.
- Leverage `--min-volume` and `--input-filter` for higher-quality, multi-factor screens.

## Links
- Changelog: CHANGELOG.md
- Repository: https://github.com/paulboys/HeikinAshi
- Docs Site: https://paulboys.github.io/HeikinAshi/
