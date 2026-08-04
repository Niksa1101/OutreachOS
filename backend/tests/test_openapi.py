"""The OpenAPI schema is what the generated TypeScript client believes.

Q94: FastAPI declares `HTTPValidationError` for 422 automatically, and
`install_error_handlers` makes the server send `ErrorEnvelope` instead. Without
the override the generated types describe FastAPI's shape while the server
sends ours — a typed client that is confidently wrong about the most common
error in the application, and wrong in a way no test catches because both sides
pass in isolation.
"""

from typing import Any

from fastapi import FastAPI

ENVELOPE_REF = "#/components/schemas/ErrorEnvelope"


def schema(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


def test_the_envelope_is_declared_as_a_component(app: FastAPI) -> None:
    components = schema(app)["components"]["schemas"]
    assert "ErrorEnvelope" in components

    # The nested body has to be reachable too, or `openapi-typescript` emits a
    # dangling reference and the generated file will not compile.
    envelope = components["ErrorEnvelope"]
    assert "$defs" not in envelope, "nested definitions must be lifted into components"
    assert "ErrorBody" in components


def test_fastapis_own_validation_schemas_are_gone(app: FastAPI) -> None:
    components = schema(app)["components"]["schemas"]
    assert "HTTPValidationError" not in components
    assert "ValidationError" not in components


def test_every_declared_422_points_at_our_envelope(app: FastAPI) -> None:
    found = 0
    for operations in schema(app)["paths"].values():
        for operation in operations.values():
            response = operation.get("responses", {}).get("422")
            if response is None:
                continue
            found += 1
            assert response["content"]["application/json"]["schema"]["$ref"] == ENVELOPE_REF

    assert found > 0, "no operation declares a 422; the override was not exercised"


def test_the_unauthorized_response_is_declared_everywhere(app: FastAPI) -> None:
    # Q67 puts `unauthorized` in the closed set because P0's token dependency
    # emits it — and Q43 applies it to every route with no exemptions, so every
    # operation can genuinely return it.
    for path, operations in schema(app)["paths"].items():
        for method, operation in operations.items():
            assert "401" in operation["responses"], f"{method.upper()} {path} omits 401"


def test_the_events_stream_is_absent_from_the_schema(app: FastAPI) -> None:
    # Q114: a stream has no response body OpenAPI can describe, and a generated
    # type claiming it returns `string` would be worse than none. Its vocabulary
    # is hand-written with a parity test instead.
    assert "/api/v1/events" not in schema(app)["paths"]


def test_the_documented_endpoints_are_the_ones_q88_names(app: FastAPI) -> None:
    # `/settings` joins in checkpoint 5, when there is a database behind it.
    assert set(schema(app)["paths"]) == {"/api/v1/health", "/api/v1/client-logs"}


def test_the_schema_is_cached_rather_than_rebuilt(app: FastAPI) -> None:
    # `gen-api-types` and `/openapi.json` must not be able to disagree, and a
    # rebuild that produced a different dict each call would make the CI
    # staleness check flap.
    assert app.openapi() is app.openapi()
