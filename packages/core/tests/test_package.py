"""Smoke tests for the installable core package."""

from slidelegible import __version__


def test_package_exposes_version() -> None:
    assert __version__
