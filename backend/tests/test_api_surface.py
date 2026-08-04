"""The P0 endpoint surface, exercised through the real ASGI stack.

Q88: four endpoints. `/settings` joins in checkpoint 5 when there is a database
behind it.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_BOOT_ID, TEST_TOKEN

# --- authentication (Q43) --------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/health"), ("POST", "/client-logs")],
)
async def test_no_exemptions_from_the_token(
    anonymous_client: AsyncClient, method: str, path: str
) -> None:
    # Q43 includes `/health` deliberately: it leaks `workspace_path` and
    # therefore a username, so it should not be open regardless of how
    # convenient an unauthenticated liveness probe would be.
    #
    # The method has to match the route. Starlette resolves the route before
    # the dependency tree, so a wrong method returns 405 without ever reaching
    # the token check — which would make this pass for the wrong reason.
    response = await anonymous_client.request(method, path, json={"entries": []})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_a_wrong_token_of_the_right_length_is_rejected(
    anonymous_client: AsyncClient,
) -> None:
    # Same length as the real token, so `compare_digest` is doing the work
    # rather than a length check short-circuiting it.
    response = await anonymous_client.get(
        "/health", headers={"Authorization": "Bearer " + "b" * len(TEST_TOKEN)}
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Basic " + TEST_TOKEN, TEST_TOKEN, "bearer"],
)
async def test_a_malformed_authorization_header_is_rejected(
    anonymous_client: AsyncClient, header: str
) -> None:
    response = await anonymous_client.get("/health", headers={"Authorization": header})
    assert response.status_code == 401


async def test_the_scheme_comparison_is_case_insensitive(anonymous_client: AsyncClient) -> None:
    # RFC 7235 makes the scheme case-insensitive, and clients do vary.
    response = await anonymous_client.get(
        "/health", headers={"Authorization": f"bearer {TEST_TOKEN}"}
    )
    assert response.status_code == 200


# --- /health (Q36, Q113) ---------------------------------------------------


async def test_health_reports_the_boot_report(client: AsyncClient) -> None:
    body = (await client.get("/health")).json()

    assert body["status"] == "ok"
    # Q36: makes "did the sidecar silently restart?" answerable from one field
    # rather than inferred from a 401.
    assert body["boot_id"] == TEST_BOOT_ID


async def test_health_carries_everything_the_diagnostics_screen_needs(
    client: AsyncClient,
) -> None:
    # Q104/Q113: that screen must be DB-free, and this payload is the only
    # thing standing between it and a session it must not take. A field going
    # missing here turns into a blank row on the screen that renders when the
    # user is already stuck.
    body = (await client.get("/health")).json()

    for field in (
        "status",
        "boot_id",
        "backend_version",
        "app_version",
        "workspace_path",
        "boot_log_path",
        "backend_log_path",
        "migration_head",
        "migration_current",
        "backup_path",
        "detail",
        "started_at",
    ):
        assert field in body, f"/health is missing {field}"


# --- trailing slashes (Q95) ------------------------------------------------


@pytest.mark.parametrize("path", ["/health/", "/client-logs/"])
async def test_a_trailing_slash_404s_rather_than_redirecting(
    client: AsyncClient, path: str
) -> None:
    # The CORS specification forbids following redirects during preflight, so a
    # trailing-slash redirect surfaces as an opaque preflight failure rather
    # than as the routing mistake it is.
    response = await client.request("GET", path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- /client-logs (Q64) ----------------------------------------------------


async def test_client_logs_accepts_a_batch(client: AsyncClient) -> None:
    response = await client.post(
        "/client-logs",
        json={
            "entries": [
                {"level": "error", "message": "boom", "source": "window.onerror"},
                {"level": "warn", "message": "hmm", "source": "error-boundary"},
            ]
        },
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": 2}


async def test_an_empty_batch_is_accepted(client: AsyncClient) -> None:
    # A flush with nothing queued is normal, not an error. Rejecting it would
    # make the client's error reporter itself a source of errors.
    response = await client.post("/client-logs", json={"entries": []})
    assert response.status_code == 202
    assert response.json() == {"accepted": 0}


async def test_an_oversized_batch_is_refused(client: AsyncClient) -> None:
    # A runaway `window.onerror` loop must not be able to fill the log a user
    # is meant to read.
    response = await client.post(
        "/client-logs",
        json={
            "entries": [
                {"level": "error", "message": f"{index}", "source": "loop"} for index in range(51)
            ]
        },
    )
    assert response.status_code == 422


# --- the error envelope (Q28, Q94) -----------------------------------------


async def test_a_validation_failure_uses_our_envelope_not_fastapis(
    client: AsyncClient,
) -> None:
    response = await client.post("/client-logs", json={"entries": [{"level": "nope"}]})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    # FastAPI's own shape is a bare top-level `detail` list. If that is what
    # came back, the exception handler is not installed.
    assert "detail" not in body


async def test_an_unmatched_route_returns_the_envelope(client: AsyncClient) -> None:
    response = await client.get("/no-such-endpoint")
    assert response.status_code == 404
    assert set(response.json()["error"]) >= {"code", "message"}
