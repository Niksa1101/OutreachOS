"""Workspace layout on disk.

Q80 puts *validation* in Rust — it has to run before the sidecar exists, on the
picker. What lives here is the part that runs after: creating the directory
tree, idempotently, on every boot (Q82).

Every boot rather than only the first, because the alternative is trusting that
nothing between the last boot and this one moved, renamed, or synced away a
directory. Creating three directories that already exist costs three failed
syscalls.
"""

from dataclasses import dataclass
from pathlib import Path

__all__ = ["WorkspaceLayout", "prepare_workspace"]

DATABASE_FILENAME = "outreachos.db"
LOG_FILENAME = "outreachos.log"
LOCK_FILENAME = ".oos-lock"


@dataclass(frozen=True)
class WorkspaceLayout:
    """DB.md §1's tree, resolved against one workspace root."""

    root: Path

    @property
    def database(self) -> Path:
        return self.root / DATABASE_FILENAME

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def log_file(self) -> Path:
        return self.logs / LOG_FILENAME

    @property
    def lock_file(self) -> Path:
        return self.root / LOCK_FILENAME


def prepare_workspace(root: Path) -> WorkspaceLayout:
    """Resolve the workspace and create its directory tree.

    The path is resolved rather than taken as given so that a relative
    ``--workspace`` (only reachable when running the sidecar standalone) and
    the canonical form Rust stores in ``workspace.json`` cannot end up
    describing the same directory under two different strings — which is what
    would stop the lock file in ``.oos-lock`` from matching itself.
    """
    layout = WorkspaceLayout(root=root.resolve())

    # DB.md §1: cache/ has three subdirectories, but they are P1's to create —
    # the ones here are the ones something in P0 actually writes into.
    for directory in (layout.root, layout.cache, layout.outputs, layout.logs):
        directory.mkdir(parents=True, exist_ok=True)

    return layout
