# Contributing Guide

Thank you for contributing to StockCharts! This guide outlines our expectations to keep the codebase stable, testable, and well-documented.

## Development Workflow
- Create a feature branch from `main`.
- Write tests first for new logic (unit tests), then integration tests for CLI flows.
- Keep changes minimal and focused; avoid unrelated refactors.
- Update docs and changelog when you add user-facing features.

## Testing
- Run `pytest` locally. CI runs tests with coverage.
- Unit tests: focus on pure functions like `indicators/divergence.py` and `indicators/pivots.py`.
- Integration tests: validate CLI commands (`stockcharts-rsi-divergence`, `stockcharts-plot-divergence`) using temp files.
- Mock external services (e.g., yfinance) using `pytest-mock` or `responses`.

## Style & Structure
- Follow existing code style; no large reformatting.
- Prefer composition and small helpers over deep inheritance.
- Keep fixtures under `tests/fixtures/`; examples belong in `examples/`.

## Documentation
- Update `docs/` and `mkdocs.yml` for new flags or features.
- Add usage examples and “Try it” commands.
- Build docs locally: `mkdocs build`.

## Pull Request Checklist
- [ ] Tests added/updated (unit and/or integration)
- [ ] Docs updated in `docs/`
- [ ] Changelog entry added (if user-facing)
- [ ] CI passes locally (`pytest`, `mkdocs build --strict`)

## Releasing
- **Semantic versioning** (MAJOR.MINOR.PATCH): Breaking changes bump major, features bump minor, fixes bump patch.
- **Single source of truth**: Version is defined only in `pyproject.toml`. The package reads it via `importlib.metadata`.
- To bump version: Edit `version = "X.Y.Z"` in `pyproject.toml` only. Do not edit `__init__.py`.
- Tag releases with `git tag vX.Y.Z` after merging; PyPI publish is handled via GitHub Actions.
- Verify version: `python -c "from stockcharts import __version__; print(__version__)"` or `stockcharts-screen --version`.

## Questions
Open a GitHub issue or start a discussion. We appreciate your help!