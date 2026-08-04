"""The API error envelope.

Q28: every failure leaves this process as ``{"error": {"code", "message",
"details?"}}``. Q67 closes the code set and adds ``unauthorized``, which is
emitted in P0 by the token dependency and therefore belongs from the start.

Q94 adds the part that is easy to skip and expensive to miss: FastAPI declares
its own ``HTTPValidationError`` for 422 automatically. Installing a
``RequestValidationError`` handler that emits *this* envelope, without also
overriding the declared 422 model, produces generated TypeScript that describes
FastAPI's shape while the server sends ours — a typed client that is
confidently wrong about the most common error. The override lives in
``openapi.py``.
"""

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

__all__ = [
    "ApiError",
    "ApiErrorCode",
    "ErrorBody",
    "ErrorEnvelope",
    "install_error_handlers",
]

log = logging.getLogger(__name__)


class ApiErrorCode(StrEnum):
    """Why a *request* failed.

    Q124: this is one of **two** enums and they never share a value. The other
    is the diagnostics code set in ``src-tauri/src/diagnostics.rs``, which
    describes why the *application* cannot run. Nothing is ever both, and the
    temptation to reach across arrives around P4 — hence the comment on each.
    """

    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    WORKSPACE_ERROR = "workspace_error"
    UNAUTHORIZED = "unauthorized"
    INTERNAL_ERROR = "internal_error"


class ErrorBody(BaseModel):
    code: ApiErrorCode
    message: str = Field(description="Plain language, written for a user.")
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    """Raise this rather than ``HTTPException`` — it carries the code."""

    def __init__(
        self,
        code: ApiErrorCode,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def _envelope(
    status_code: int,
    code: ApiErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


# Q67's closed set, mapped from the HTTP status codes Starlette raises on its
# own (404 from an unmatched route, 405 from a wrong method).
_STATUS_TO_CODE: dict[int, ApiErrorCode] = {
    status.HTTP_401_UNAUTHORIZED: ApiErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ApiErrorCode.UNAUTHORIZED,
    status.HTTP_404_NOT_FOUND: ApiErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ApiErrorCode.CONFLICT,
    status.HTTP_422_UNPROCESSABLE_CONTENT: ApiErrorCode.VALIDATION_ERROR,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, ApiErrorCode.INTERNAL_ERROR)
        return _envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic puts the offending input in `ctx`, which can hold arbitrary
        # non-serialisable objects. A serialisation failure *inside* the error
        # handler produces a 500 that hides the 422 it was reporting, so the
        # errors go through `jsonable_encoder` rather than straight to JSON.
        return _envelope(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ApiErrorCode.VALIDATION_ERROR,
            "The request body or parameters did not validate.",
            {"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # The stack goes to the log; the client gets a code and a sentence.
        # A local-only backend still has no reason to put a traceback in a
        # response body that ends up in a screenshot.
        log.exception("unhandled error serving %s %s", request.method, request.url.path)
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ApiErrorCode.INTERNAL_ERROR,
            "The backend hit an unexpected error. See the log for details.",
        )
