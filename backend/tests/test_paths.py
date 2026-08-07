"""Tests for frozen-build path resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from outreachos_backend.core.paths import backend_root, is_frozen, resource_path


def test_backend_root_points_at_alembic_in_dev() -> None:
    root = backend_root()
    assert (root / "alembic.ini").is_file()
    assert (root / "alembic" / "versions").is_dir()


def test_resource_path_joins_under_backend_root() -> None:
    assert resource_path("alembic", "env.py") == backend_root() / "alembic" / "env.py"


def test_backend_root_uses_meipass_when_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (tmp_path / "alembic").mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert is_frozen() is True
    assert backend_root() == tmp_path
