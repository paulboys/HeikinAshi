# Building and Distributing StockCharts

Guide for maintainers on how to build, test, and distribute the StockCharts Python library.

## Prerequisites

- Python 3.9+
- pip and setuptools
- Git
- (Optional) Account on PyPI for publishing

## Local Development Setup

### 1. Clone the Repository

```powershell
git clone https://github.com/paulboys/HeikinAshi.git
cd HeikinAshi
```

### 2. Create Development Environment

```powershell
# Using conda
conda create -n stockcharts-dev python=3.12 -y
conda activate stockcharts-dev

# Or using venv
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install in Editable Mode

```powershell
pip install -e .
```

This installs the package in "editable" mode, meaning changes to the source code are immediately reflected without reinstalling.

### 4. Verify Installation

```powershell
# Test CLI commands
stockcharts-screen --help
stockcharts-plot --help

# Test Python API
python -c "from stockcharts.screener.screener import screen_nasdaq; print('OK')"
```

## Project Structure

```
StockCharts/
├── src/
│   └── stockcharts/          # Main package source
│       ├── __init__.py
│       ├── cli.py            # CLI entry points
│       ├── charts/           # Heiken Ashi calculations
│       ├── data/             # Data fetching
│       └── screener/         # Screening logic
├── scripts/                  # Legacy standalone scripts
├── tests/                    # Unit tests
├── pyproject.toml           # Package configuration
├── README.md                # User-facing documentation
└── LIBRARY_GUIDE.md         # Comprehensive usage guide
```

## Running Tests

### Manual Testing

```powershell
# Test NASDAQ ticker fetching
python -c "from stockcharts.screener.nasdaq import get_nasdaq_tickers; print(f'Found {len(get_nasdaq_tickers())} tickers')"

# Test screening with limited set
stockcharts-screen --color green --period 1d --debug

# Test chart generation
stockcharts-plot --input results/nasdaq_screen.csv
```

### Unit Tests (Future)

```powershell
pytest tests/
```

## Building the Package

### 1. Update Version Number

Edit `pyproject.toml`:

```toml
[project]
name = "stockcharts"
version = "0.2.0"  # Increment this
```

### 2. Build Distribution Files

```powershell
# Install build tools
pip install build

# Create distribution packages
python -m build
```

This creates:
- `dist/stockcharts-0.2.0.tar.gz` (source distribution)
- `dist/stockcharts-0.2.0-py3-none-any.whl` (wheel distribution)

### 3. Verify Build

```powershell
# List contents of wheel
python -m zipfile -l dist/stockcharts-0.2.0-py3-none-any.whl

# Install from local wheel to test
pip install dist/stockcharts-0.2.0-py3-none-any.whl
```

## Publishing to PyPI

### Test on TestPyPI First

1. **Create account** on [TestPyPI](https://test.pypi.org/)

2. **Configure credentials** in `~/.pypirc`:
   ```ini
   [testpypi]
   username = __token__
   password = pypi-XXXXXXXXXXXX
   ```

3. **Upload to TestPyPI**:
   ```powershell
   pip install twine
   python -m twine upload --repository testpypi dist/*
   ```

4. **Test installation**:
   ```powershell
   pip install --index-url https://test.pypi.org/simple/ stockcharts
   ```

### Publish to PyPI

1. **Create account** on [PyPI](https://pypi.org/)

2. **Configure credentials** in `~/.pypirc`:
   ```ini
   [pypi]
   username = __token__
   password = pypi-XXXXXXXXXXXX
   ```

3. **Upload to PyPI**:
   ```powershell
   python -m twine upload dist/*
   ```

4. **Verify**:
   ```powershell
   pip install stockcharts
   stockcharts-screen --help
   ```

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):

- **0.1.0**: Initial release
- **0.1.1**: Bug fixes (patch)
- **0.2.0**: New features, backward compatible (minor)
- **1.0.0**: First stable release
- **2.0.0**: Breaking changes (major)

## Release Checklist

Before each release:

- [ ] Update version in `pyproject.toml`
- [ ] Update `README.md` with new features
- [ ] Update `LIBRARY_GUIDE.md` if API changed
- [ ] Test CLI commands (`stockcharts-screen`, `stockcharts-plot`)
- [ ] Test Python API imports
- [ ] Run manual screening test with real data
- [ ] Build distribution files (`python -m build`)
- [ ] Create Git tag: `git tag v0.2.0`
- [ ] Push tag: `git push origin v0.2.0`
- [ ] Upload to TestPyPI (optional)
- [ ] Upload to PyPI
- [ ] Create GitHub release with notes

## GitHub Releases

1. Go to repository on GitHub
2. Click "Releases" → "Draft a new release"
3. Choose tag (e.g., `v0.2.0`)
4. Write release notes:
   ```markdown
   ## What's New in 0.2.0
   
   ### Features
   - Added CLI entry points (`stockcharts-screen`, `stockcharts-plot`)
   - Enhanced volume filtering
   
   ### Bug Fixes
   - Fixed FTP ticker fetching
   
   ### Documentation
   - Added comprehensive LIBRARY_GUIDE.md
   
   ## Installation
   ```
   pip install stockcharts
   ```
   ```
5. Attach `dist/*.tar.gz` and `dist/*.whl` files
6. Publish release

## Maintaining the Package

### Updating Dependencies

Edit `pyproject.toml`:

```toml
dependencies = [
  "yfinance>=0.2.40",  # Update version
  "pandas>=2.1.0",
  "matplotlib>=3.8.0"
]
```

Then rebuild:
```powershell
pip install -e .
python -m build
```

### Adding New Features

1. Create feature branch:
   ```powershell
   git checkout -b feature/new-indicator
   ```

2. Implement changes in `src/stockcharts/`

3. Test locally:
   ```powershell
   pip install -e .
   # Test your changes
   ```

4. Commit and push:
   ```powershell
   git add .
   git commit -m "Add new technical indicator"
   git push origin feature/new-indicator
   ```

5. Create pull request on GitHub

6. After merge, create new release

### Hotfix Process

For urgent bug fixes:

1. Create hotfix branch from main:
   ```powershell
   git checkout -b hotfix/0.2.1 main
   ```

2. Fix bug and test

3. Bump patch version in `pyproject.toml` (0.2.0 → 0.2.1)

4. Commit and merge to main

5. Create release:
   ```powershell
   git tag v0.2.1
   git push origin v0.2.1
   python -m build
   python -m twine upload dist/*
   ```

## Common Issues

### "Command not found: stockcharts-screen"

**Cause**: CLI entry points not installed

**Fix**:
```powershell
pip install --force-reinstall -e .
```

### "Module not found: stockcharts"

**Cause**: Package not installed or wrong environment

**Fix**:
```powershell
# Check which Python is active
python --version
which python  # or 'where python' on Windows

# Reinstall in correct environment
pip install -e .
```

### Build Errors

**Cause**: Missing build tools

**Fix**:
```powershell
pip install --upgrade pip setuptools wheel build
python -m build
```

### Upload Errors (403 Forbidden)

**Cause**: Incorrect PyPI credentials or version already exists

**Fix**:
- Check `~/.pypirc` credentials
- Increment version in `pyproject.toml`
- Delete old files from `dist/` folder

## CI/CD (Future)

Consider setting up GitHub Actions for automated testing and deployment:

`.github/workflows/test.yml`:
```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.12
      - run: pip install -e .
      - run: stockcharts-screen --help
      - run: pytest tests/
```

`.github/workflows/publish.yml`:
```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install build twine
      - run: python -m build
      - run: python -m twine upload dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
```

## Resources

- [Python Packaging Guide](https://packaging.python.org/)
- [setuptools Documentation](https://setuptools.pypa.io/)
- [PyPI Help](https://pypi.org/help/)
- [Semantic Versioning](https://semver.org/)
- [Git Tagging](https://git-scm.com/book/en/v2/Git-Basics-Tagging)

## Support

For issues or questions:
- Open an issue on GitHub: https://github.com/paulboys/HeikinAshi/issues
- Check existing documentation in the repository
