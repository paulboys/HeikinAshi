# Legacy Documentation Map

Original markdown files retained for historical reference. Their content has been consolidated into the new `docs/` structure.

| Legacy File | New Location |
|-------------|--------------|
| README.md | docs/overview.md (summary) |
| DISTRIBUTION.md | docs/overview.md (packaging section) |
| LIBRARY_GUIDE.md | docs/overview.md (architecture) |
| LIBRARY_COMPLETE.md | docs/overview.md (extended notes) |
| QUICK_REFERENCE.md | docs/quick_reference.md |
| SCREENER_GUIDE.md | docs/screener.md |
| SCREENER_IMPLEMENTATION.md | docs/screener.md (implementation) |
| TRADING_STYLE_GUIDE.md | docs/trading_styles.md |
| RSI_DIVERGENCE_GUIDE.md | docs/rsi_divergence.md |
| DIVERGENCE_MODULE_SUMMARY.md | docs/rsi_divergence.md (workflow) |
| DIVERGENCE_CHART_GUIDE.md | docs/rsi_divergence.md (plotting section) |
| PRECOMPUTED_DIVERGENCE_PATCH.md | docs/rsi_divergence.md (precomputed indices) |
| RSI_TOLERANCE_GUIDE.md | docs/rsi_divergence.md (tolerance section) |
| PARAMETER_GUIDE.md | docs/parameters.md |
| VOLUME_FILTERING_GUIDE.md | docs/volume.md |
| VOLUME_FILTER_SUMMARY.md | docs/volume.md |
| TODO_NEXT_STEPS.md | docs/roadmap.md |
| TRADING_STYLE_GUIDE.md | docs/trading_styles.md |

## Guidance
Keep legacy files for a few commits; remove or archive once consumers migrate.

## Removal Strategy (Optional)
1. Tag release before deletion.
2. Remove legacy root markdown files.
3. Update README references.
4. Communicate change in CHANGELOG.

## Suggestion
Add a short deprecation banner at top of each legacy file if removal planned.
