"""Workspace and frozen-build path resolution.

ADR-0004: Python data files (``alembic.ini``, ``alembic/versions/``) resolve
through this helper under ``sys._MEIPASS`` in a PyInstaller build. FFmpeg
binaries are **not** package assets — Tauri passes the directory as a CLI
argument instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["backend_root", "is_frozen", "resource_path"]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def backend_root() -> Path:
    """Directory containing ``alembic.ini`` and the ``alembic/`` tree."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[3]


def resource_path(*parts: str | Path) -> Path:
    """Resolve a path to bundled application data files."""
    return backend_root().joinpath(*parts)
