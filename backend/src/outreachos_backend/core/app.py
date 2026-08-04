"""FastAPI application factory.

Everything runtime-specific — the token, the boot report, the event bus — is
attached to ``app.state`` by ``__main__``. The factory itself takes only what
changes the *shape* of the application, so ``main.app`` can be constructed for
schema generation without a workspace, a token, or a running process (Q89).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from outreachos_backend._version import __version__
from outreachos_backend.core.errors import install_error_handlers
from outreachos_backend.core.openapi import install_openapi_override
from outreachos_backend.core.routes import api_v1_router

__all__ = ["create_app"]

log = logging.getLogger(__name__)

#: Q73: the webview's own origins. Both schemes, because Tauri serves the
#: production bundle over a custom protocol that resolves as `https` on some
#: Windows configurations and `http` on others.
_WEBVIEW_ORIGINS = ("http://tauri.localhost", "https://tauri.localhost")

#: Q73: **both** dev origins. `localhost` and `127.0.0.1` are distinct origins
#: and Vite will hand you either depending on how the webview resolves
#: `devUrl`. Allowing one and not the other produces a preflight failure that
#: looks like a CORS misconfiguration but is actually a hostname mismatch.
#: 1420 must match `build.devUrl` in tauri.conf.json.
_DEV_ORIGINS = ("http://localhost:1420", "http://127.0.0.1:1420")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    import asyncio

    bus = getattr(app.state, "event_bus", None)
    if bus is not None:
        # Publishing is thread-safe (P4's render worker runs off-loop), which
        # means the bus needs to know which loop owns the subscriber queues.
        bus.attach_loop(asyncio.get_running_loop())

    log.info("API accepting requests")
    yield
    log.info("API shutting down")


def create_app(*, dev: bool = False) -> FastAPI:
    app = FastAPI(
        title="OutreachOS Backend",
        version=__version__,
        description=(
            "Local-only API for the OutreachOS desktop application. Bound to "
            "127.0.0.1 on an ephemeral port and authenticated with a shared "
            "secret generated per launch."
        ),
        # Q44: the interactive surface exists in dev and is absent from
        # packaged builds. Q57 keeps this separate from log verbosity — an
        # advanced user debugging a packaged build should get a verbose log,
        # not a live OpenAPI surface.
        docs_url="/docs" if dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if dev else None,
        lifespan=_lifespan,
    )

    # Q95: the form guaranteed to work across FastAPI versions. The constructor
    # kwarg is not reliably exposed. Pleasant side effect: a mistyped path now
    # returns a clean 404 instead of a redirect the preflight silently refuses
    # to follow.
    app.router.redirect_slashes = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[*_WEBVIEW_ORIGINS, *(_DEV_ORIGINS if dev else ())],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["authorization", "content-type"],
        # Q73: not merely safe, load-bearing. This is what keeps the allowlist
        # honest if anyone later reaches for `*` — the browser refuses the
        # combination outright.
        allow_credentials=False,
        max_age=600,
    )

    install_error_handlers(app)
    app.include_router(api_v1_router)
    install_openapi_override(app)

    return app
