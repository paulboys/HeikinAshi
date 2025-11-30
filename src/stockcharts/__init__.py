"""StockCharts package initialization.

Provides public version constant for CLI and user introspection.
Version is read from package metadata (pyproject.toml).
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("stockcharts")
except PackageNotFoundError:
    # Package not installed, use fallback for development
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
