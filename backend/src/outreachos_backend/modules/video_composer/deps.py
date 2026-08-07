"""Video Composer request dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from outreachos_backend.core.deps import WorkspaceDep, get_workspace
from outreachos_backend.core.errors import ApiError, ApiErrorCode
from outreachos_backend.core.events import EventBus
from outreachos_backend.rendering.binaries import Binaries, resolve_binaries
from outreachos_backend.rendering.queue.pool import WorkerPool

__all__ = [
    "BinariesDep",
    "EventBusDep",
    "WorkerPoolDep",
    "WorkspaceDep",
    "get_binaries",
    "get_event_bus",
    "get_worker_pool",
    "get_workspace",
]


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


def get_event_bus(request: Request) -> EventBus:
    event_bus: EventBus = request.app.state.event_bus
    return event_bus


def get_worker_pool(request: Request) -> WorkerPool[str, Session] | None:
    """``None`` in test apps that never call ``__main__._serve`` to wire one up.

    ``generate_videos`` treats a missing pool as "nothing to wake" rather than
    raising, so a router test that only exercises enqueue-and-return still
    works without constructing a real pool.
    """
    return getattr(request.app.state, "worker_pool", None)


BinariesDep = Annotated[Binaries, Depends(get_binaries)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
WorkerPoolDep = Annotated["WorkerPool[str, Session] | None", Depends(get_worker_pool)]
