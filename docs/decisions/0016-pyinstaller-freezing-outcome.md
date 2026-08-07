# ADR-0016: PyInstaller freezing outcome

**Status:** Accepted — records PRD §9 risk 5 resolution for ticket 27

---

## Context

PRD §9 risk 5 named PyInstaller freezing FastAPI, uvicorn, and SQLAlchemy on
Windows as an open packaging risk, with hidden-imports tuning as the first path
and an embedded Python runtime as the fallback.

Ticket 27 had to prove the sidecar could:

1. Start without a system Python install
2. Bind an ephemeral port and serve the API
3. Run Alembic migrations from bundled `alembic/versions/`
4. Drive renders through FFmpeg passed as an external directory argument
   (ADR-0004 — FFmpeg is a Tauri resource, not a PyInstaller `datas` entry)

## Decision

**PyInstaller 6 `onedir` is viable.** No embedded-runtime fallback is required
for V1.

The freeze uses:

- Entry points: `outreachos_backend.__main__` (sidecar) and
  `outreachos_backend.render_entry` (headless render CLI smoke / ops)
- Explicit `datas` for `alembic.ini` and the full `alembic/` tree
- `collect_submodules("uvicorn")` and `collect_submodules("sqlalchemy")` plus
  explicit imports for Alembic runtime, pydantic-settings, and SQLAlchemy model
  modules referenced from `alembic/env.py`
- `backend_root()` / `resource_path()` in `core/paths.py` so migration script
  resolution works under `sys._MEIPASS`

Build command (manual release step, per PRD §8):

```powershell
pnpm build:sidecar
pnpm run build:installer   # ticket 28 — stages resources and runs tauri build
```

`scripts/build-backend.ps1` runs `pytest tests/test_frozen_sidecar.py` after
every freeze. That test boots the executable, verifies `/health` and migration
head, and runs `outreachos-render.exe render` against lavfi-generated fixtures
with `vendor/ffmpeg/`.

## Alternatives considered

- **`onefile`.** Rejected in ADR-0006 for cold-start cost and AV heuristics.
- **Embedded CPython runtime instead of PyInstaller.** Not needed — the first
  freeze passed with submodule collection and Alembic `datas` only.
- **Bundling FFmpeg inside PyInstaller `datas`.** Rejected in ADR-0004 — ~180 MB
  re-bundled on every backend re-freeze and mixed concerns with Python data
  files.

## Consequences

- Release builds depend on `uv sync --group dev` so PyInstaller is available;
  CI continues to skip the freeze (PRD §8: release builds manual).
- Tauri resources are staged under `src-tauri/bundle-resources/` by
  `scripts/stage-bundle-resources.ps1`, not copied directly from `backend/dist/`
  in `tauri.conf.json`. This keeps dev `tauri dev` free of a prior freeze.
- Any new package imported only through reflection (common with ASGI middleware
  or SQLAlchemy dialect plugins) may need an explicit `hiddenimports` line in
  `backend/outreachos-backend.spec`.
- If a future dependency makes freezing intractable, revisit the embedded-runtime
  fallback — it remains documented in ADR-0006.

## References

PRD §9 risk 5 · ADR-0004 · ADR-0006 · ADR-0007 · ticket 27 ·
`backend/outreachos-backend.spec` · `scripts/build-backend.ps1`
