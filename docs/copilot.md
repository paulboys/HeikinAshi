# Copilot Guide

This project welcomes AI assistance to accelerate development while maintaining quality. Use these prompt patterns and expectations.

## Prompt Patterns
- "Write unit tests for `indicators/divergence.py` covering 2- and 3-point cases. Use small synthetic OHLC fixtures."
- "Create integration tests for `stockcharts-rsi-divergence` CLI that write outputs to a temp dir and validate CSV headers. Mock yfinance downloads."
- "Add MkDocs section to `docs/index.md` showing 'Try It' commands for screening and plotting."
- "Refactor helper functions in `pivots.py` to improve testability without changing public APIs."

## Expectations
- Tests first: propose tests, then implement minimal code to pass.
- Mock external services: do not perform network calls in tests.
- Keep patches surgical: avoid formatting unrelated files.
- Update docs when adding flags or changing behavior.

## Common Mocks
- `yfinance.download`: return a deterministic DataFrame with columns `Open,High,Low,Close,Volume`.
- File system: use `tempfile.TemporaryDirectory()` in tests; avoid writing outside temp paths.

## Checklists
- [ ] Unit tests added
- [ ] Integration tests added/mocked
- [ ] Docs updated
- [ ] CI passes locally

## Useful Commands
```bash
pytest -q --maxfail=1 --disable-warnings
mkdocs build --strict
mkdocs serve
```
