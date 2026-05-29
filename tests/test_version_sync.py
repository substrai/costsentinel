"""Test that version is consistent across pyproject.toml and __init__.py."""

import re
from pathlib import Path

import costsentinel


def test_version_sync():
    """Verify pyproject.toml and __init__.py have the same version."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject_path.read_text()
    match = re.search(r'^version = "(.+)"', content, re.MULTILINE)
    assert match is not None, "Could not find version in pyproject.toml"
    pyproject_version = match.group(1)
    assert costsentinel.__version__ == pyproject_version, (
        f"Version mismatch: pyproject.toml={pyproject_version}, "
        f"__init__.py={costsentinel.__version__}"
    )


def test_version_is_valid_semver():
    """Verify version follows semver format."""
    version = costsentinel.__version__
    assert re.match(r"^\d+\.\d+\.\d+", version), (
        f"Version '{version}' does not follow semver format"
    )
