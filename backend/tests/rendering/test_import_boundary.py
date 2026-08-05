"""Q184: rendering/ must not import modules.* or core.db."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = (
    "outreachos_backend.modules",
    "outreachos_backend.core.db",
)


def test_rendering_does_not_import_forbidden_packages() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "outreachos_backend" / "rendering"
    violations: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_PREFIXES):
                        violations.append(f"{path}: import {alias.name}")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith(FORBIDDEN_PREFIXES)
            ):
                violations.append(f"{path}: from {node.module}")
    assert not violations, "Forbidden imports in rendering:\n" + "\n".join(violations)
