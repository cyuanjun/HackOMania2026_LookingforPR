"""Minimal compatibility shim for environments without setuptools' pkg_resources.

This project only needs `parse_version` for tensorflow_hub import checks.
"""

from __future__ import annotations

from packaging.version import parse as parse_version  # re-export

