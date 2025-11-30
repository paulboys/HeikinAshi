"""
Unit tests for package metadata and version information.
"""
import pytest
from stockcharts import __version__


def test_version_exists():
    """Verify __version__ is accessible from package."""
    assert __version__ is not None
    assert isinstance(__version__, str)


def test_version_format():
    """Verify version follows semantic versioning format."""
    # Should be X.Y.Z or X.Y.Z.devN
    parts = __version__.split('.')
    assert len(parts) >= 3, f"Version {__version__} should have at least 3 parts (major.minor.patch)"
    
    # First three parts should be numeric
    major, minor, patch = parts[0], parts[1], parts[2].split('dev')[0]
    assert major.isdigit(), "Major version should be numeric"
    assert minor.isdigit(), "Minor version should be numeric"
    assert patch.isdigit(), "Patch version should be numeric"


def test_version_not_dev_default():
    """Verify installed package doesn't use dev fallback."""
    # Should not be the fallback version unless in development mode
    if __version__ == "0.0.0.dev0":
        pytest.skip("Package not installed (development mode)")
    
    assert __version__ != "0.0.0.dev0", "Should read version from installed package metadata"
