"""Video Composer request dependencies."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from outreachos_backend.core.errors import ApiError, ApiErrorCode
from outreachos_backend.core.workspace import WorkspaceLayout
from outreachos_backend.rendering.binaries import Binaries, resolve_binaries

__all__ = ["BinariesDep", "WorkspaceDep", "get_binaries", "get_workspace"]


def get_workspace(request: Request) -> WorkspaceLayout:
    return WorkspaceLayout(root=Path(request.app.state.runtime.report.workspace_path))


def get_binaries(request: Request) -> Binaries:
    ffmpeg_dir = request.app.state.runtime.ffmpeg_dir
    try:
        return resolve_binaries(ffmpeg_dir)
    except Exception as exc:
        raise ApiError(
            ApiErrorCode.INTERNAL_ERROR,
            "FFmpeg is not available. Check that the bundled FFmpeg binaries are installed.",
            status_code=503,
        ) from exc


WorkspaceDep = Annotated[WorkspaceLayout, Depends(get_workspace)]
BinariesDep = Annotated[Binaries, Depends(get_binaries)]
