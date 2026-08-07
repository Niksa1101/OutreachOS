"""Shared FastAPI dependencies."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from outreachos_backend.core.workspace import WorkspaceLayout

__all__ = ["WorkspaceDep", "get_workspace"]


def get_workspace(request: Request) -> WorkspaceLayout:
    return WorkspaceLayout(root=Path(request.app.state.runtime.report.workspace_path))


WorkspaceDep = Annotated[WorkspaceLayout, Depends(get_workspace)]
