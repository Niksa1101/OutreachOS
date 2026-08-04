"""OpenAPI post-processing.

One job, from Q94: **replace FastAPI's declared 422 with our envelope.**

FastAPI declares ``HTTPValidationError`` for every route that validates
anything. ``install_error_handlers`` makes the server actually send
``ErrorEnvelope`` instead. Without this step the generated TypeScript describes
FastAPI's shape while the server sends ours — a typed client that is
confidently wrong about the most common error in the application, and wrong in
a way no test catches because both sides pass in isolation.

The rewrite is done on the finished schema rather than by declaring
``responses={422: ...}`` on every route, because FastAPI injects its own 422
*after* per-route responses are merged and would win.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from outreachos_backend.core.errors import ErrorEnvelope

__all__ = ["install_openapi_override"]

_ENVELOPE_NAME = ErrorEnvelope.__name__
_ENVELOPE_REF = f"#/components/schemas/{_ENVELOPE_NAME}"

# FastAPI's generated names. Removed from `components` once nothing references
# them, so `openapi-typescript` does not emit dead types.
_FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")

_ENVELOPE_RESPONSE: dict[str, Any] = {
    "description": "Error",
    "content": {"application/json": {"schema": {"$ref": _ENVELOPE_REF}}},
}


def install_openapi_override(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components[_ENVELOPE_NAME] = ErrorEnvelope.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        # `model_json_schema` inlines nested models into `$defs`; lift them so
        # the `$ref`s above resolve against `components/schemas`.
        for name, definition in components[_ENVELOPE_NAME].pop("$defs", {}).items():
            components.setdefault(name, definition)

        for operations in schema.get("paths", {}).values():
            for operation in operations.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.setdefault("responses", {})
                # Q28: the envelope is what a client gets for *any* failure, so
                # it is declared for all of them, not only the 422 FastAPI
                # invented.
                for status_code in ("401", "422", "500"):
                    if status_code == "422" and "422" not in responses:
                        # Routes with nothing to validate genuinely cannot 422.
                        continue
                    responses[status_code] = dict(_ENVELOPE_RESPONSE)

        for name in _FASTAPI_VALIDATION_SCHEMAS:
            components.pop(name, None)

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
