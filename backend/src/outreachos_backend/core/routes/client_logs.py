"""``POST /api/v1/client-logs``.

Q23 and Q64: the post-ready half of frontend error ingestion. Errors captured
once the backend exists land in the workspace's rolling log, next to everything
else that happened in that session. The pre-ready half goes through
``invoke("log_client_error")`` into ``boot.log`` — two sinks, chosen by boot
state.

Batched, because ``window.onerror`` on a broken render loop can fire far faster
than one request each. The frontend's loop guard is the other half of that
protection.

Named ``client-logs`` rather than Q23's original ``logs``: there is a server
log endpoint to confuse it with the moment anyone adds one.
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Body, status
from pydantic import BaseModel, Field

router = APIRouter(tags=["system"])
router.redirect_slashes = False

# A distinct logger so `[python] outreachos.client` is greppable, mirroring the
# `[client]` tag Rust writes into boot.log for the pre-ready path.
log = logging.getLogger("outreachos.client")

ClientLogLevel = Literal["warn", "error"]

#: A cap, not a target. Anything above this is a runaway loop rather than a
#: burst worth preserving, and accepting it would let a broken frontend fill
#: the log a user is meant to read.
MAX_ENTRIES_PER_BATCH = 50


class ClientLogEntry(BaseModel):
    level: ClientLogLevel
    message: str = Field(max_length=4000)
    source: str = Field(max_length=200, description="Which capture point produced it.")
    stack: str | None = Field(default=None, max_length=20_000)
    route: str | None = Field(default=None, max_length=500)
    occurred_at: str | None = Field(
        default=None,
        description="ISO-8601 UTC from the client clock. Kept separate from the "
        "server timestamp the log line carries, because the two can disagree.",
    )


class ClientLogBatch(BaseModel):
    entries: list[ClientLogEntry] = Field(max_length=MAX_ENTRIES_PER_BATCH)


class ClientLogAccepted(BaseModel):
    accepted: int


@router.post(
    "/client-logs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Record frontend errors in the workspace log",
)
def post_client_logs(batch: Annotated[ClientLogBatch, Body()]) -> ClientLogAccepted:
    for entry in batch.entries:
        level = logging.ERROR if entry.level == "error" else logging.WARNING
        log.log(
            level,
            "%s [%s] %s%s",
            entry.message,
            entry.source,
            f"route={entry.route} " if entry.route else "",
            f"\n{entry.stack}" if entry.stack else "",
        )

    return ClientLogAccepted(accepted=len(batch.entries))
