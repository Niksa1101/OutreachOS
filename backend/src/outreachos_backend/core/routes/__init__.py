"""The ``/api/v1`` router tree.

Q88: four endpoints in P0 — ``/health``, ``/events``, ``/client-logs``, and
``/settings``. They live under ``core/`` rather than in a module because they
are shared infrastructure: every future module reuses this transport, and none
of them owns it.

Two conventions are set here and inherited by every router added later.

**Authentication is applied to the router, not the endpoint** (Q43). A new
route is authenticated because it was added to this tree, not because someone
remembered a decorator.

**``redirect_slashes = False``** (Q95). The CORS specification forbids
following redirects during preflight, so a trailing-slash redirect surfaces as
an opaque preflight failure. It is set on the ``APIRouter`` as well as on
``app.router`` because routers carry their own flag, and the constructor kwarg
is not reliably exposed across FastAPI versions.
"""

from fastapi import APIRouter

from outreachos_backend.core.routes import client_logs, events, health, settings
from outreachos_backend.core.security import RequireToken

__all__ = ["api_v1_router"]

api_v1_router = APIRouter(prefix="/api/v1", dependencies=[RequireToken])
api_v1_router.redirect_slashes = False

api_v1_router.include_router(health.router)
api_v1_router.include_router(events.router)
api_v1_router.include_router(client_logs.router)
api_v1_router.include_router(settings.router)
