"""
AttentionX Python startup bootstrap.

This makes the repository root importable as the `attentionx` package so
absolute imports like `attentionx.backend.config` work in both:
- the local workspace layout, and
- flat deployment layouts such as `/app/backend/...`.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def _bootstrap_attentionx_package() -> None:
    package = sys.modules.get("attentionx")
    if package is None:
        package = types.ModuleType("attentionx")
        package.__path__ = [str(PROJECT_ROOT)]
        package.__package__ = "attentionx"
        sys.modules["attentionx"] = package
    else:
        package_path = list(getattr(package, "__path__", []))
        if str(PROJECT_ROOT) not in package_path:
            package_path.insert(0, str(PROJECT_ROOT))
            package.__path__ = package_path

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))


_bootstrap_attentionx_package()