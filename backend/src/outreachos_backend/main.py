"""ASGI entry point, and the module the schema dump imports.

Q89: the OpenAPI spec is produced **in-process, without booting the sidecar**::

    python -c "import json; from outreachos_backend.main import app; \\
               print(json.dumps(app.openapi()))"

That is what ``scripts/gen-api-types.mjs`` runs. Booting a server in CI to
fetch a spec makes the local script slower and the CI job fragile for no
benefit, so this module exists to give the spec a home that needs no workspace,
no token, and no port.

The application actually served at runtime is built by ``__main__`` with
``dev=`` resolved from the launch arguments, and this instance is never used
for that.
"""

from outreachos_backend.core.app import create_app

__all__ = ["app"]

app = create_app()
