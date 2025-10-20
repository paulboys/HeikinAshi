# Deprecation Notice (Legacy Markdown Cleanup)

## Summary
Legacy standalone markdown documentation files at the repository root have been removed in favor of consolidated topical documents under `docs/`.

## Removed Files
```
DIVERGENCE_CHART_GUIDE.md
DIVERGENCE_MODULE_SUMMARY.md
DISTRIBUTION.md
LIBRARY_COMPLETE.md
LIBRARY_GUIDE.md
PARAMETER_GUIDE.md
PRECOMPUTED_DIVERGENCE_PATCH.md
QUICK_REFERENCE.md
RSI_DIVERGENCE_GUIDE.md
RSI_TOLERANCE_GUIDE.md
SCREENER_GUIDE.md
SCREENER_IMPLEMENTATION.md
TODO_NEXT_STEPS.md
TRADING_STYLE_GUIDE.md
VOLUME_FILTERING_GUIDE.md
VOLUME_FILTER_SUMMARY.md
```

## Replacement Mapping
See `docs/legacy.md` for the authoritative mapping from each legacy file to the new consolidated location:
- Overview & Architecture → `docs/overview.md`
- Heiken Ashi Screener → `docs/screener.md`
- RSI Divergence → `docs/rsi_divergence.md`
- Parameters → `docs/parameters.md`
- Volume Filtering → `docs/volume.md`
- Trading Styles → `docs/trading_styles.md`
- Quick Commands → `docs/quick_reference.md`
- Roadmap / Next Steps → `docs/roadmap.md`

## Rationale
1. Reduce duplication and drift.
2. Improve discoverability via a single structured docs hub.
3. Simplify maintenance and future enhancements.

## Guidance for Consumers
- Update any external references (wikis, READMEs in downstream repos) to point to new `docs/` paths.
- If you pinned deep links to removed files, change them to consolidated equivalents.

## Version Tag Recommendation
Consider tagging a release before and after this cleanup:
- `vX.Y.Z-legacy-docs` (last version with individual files)
- `vX.Y.Z-docs-consolidated` (first version post-cleanup)

## Next Potential Improvements
- Add CHANGELOG entry summarizing documentation shift.
- Provide hosted documentation (e.g., GitHub Pages) generated from `docs/`.

## Contact
For questions about this migration, open an issue referencing this notice.
