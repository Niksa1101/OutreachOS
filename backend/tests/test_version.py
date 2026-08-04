"""The package imports, and its version matches the authoritative one.

``_version.py`` is generated from the root ``package.json`` by
``scripts/sync-version.mjs``. This test is the backend half of the guarantee that
the four version strings in this repository cannot silently drift apart; the CI
``sync-version:check`` job is the other half.
"""

import json
import re
import tomllib
from pathlib import Path

import outreachos_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _authoritative_version() -> str:
    package_json = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    version = package_json["version"]
    assert isinstance(version, str)
    return version


def test_package_imports_and_exposes_a_semver() -> None:
    assert SEMVER.match(outreachos_backend.__version__), (
        f"__version__ is not a plain semver string: {outreachos_backend.__version__!r}"
    )


def test_runtime_version_matches_root_package_json() -> None:
    assert outreachos_backend.__version__ == _authoritative_version(), (
        "backend/_version.py has drifted from the root package.json. Run `pnpm sync-version`."
    )


def test_pyproject_version_matches_root_package_json() -> None:
    pyproject = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == _authoritative_version(), (
        "backend/pyproject.toml has drifted from the root package.json. Run `pnpm sync-version`."
    )
