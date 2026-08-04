# `backend/`

The OutreachOS local backend: a FastAPI application spawned as a sidecar by
Tauri, bound to `127.0.0.1` on a port it allocates itself.

It is never started by the user, never reachable from another machine, and makes
no outbound network calls of any kind.

## Layout

```
src/outreachos_backend/
  core/                 config, db session, event bus, workspace paths, logging
  modules/
    video_composer/     router, service, models, schemas
  rendering/
    ffmpeg.py           binary resolution + process wrapper
    probe.py            FFprobe
    overlay_builder.py  Pillow asset generation
    steps/              composite step objects
    pipeline.py         filtergraph assembly
    queue/              worker pool, job state machine
alembic/                migrations, applied in-process at startup
tests/
```

`rendering/` and `core/`'s queue are **shared infrastructure**, not
Video Composer's property — future modules reuse the queue for scraping,
enrichment, and AI work.

FFmpeg binaries are **not** a Python package asset. They arrive as configuration:
Tauri passes the directory containing `ffmpeg.exe` and `ffprobe.exe` as a CLI
argument. See `docs/decisions/0004-backend-package-layout.md`.

## Development

```bash
uv sync
```

The backend is normally launched by Tauri. To run it standalone for curl and
pytest work:

```bash
pnpm dev:backend
```

Tauri never attaches to that standalone instance — it always spawns its own. A
second "external backend" lifecycle would be exercised only in dev and would
therefore drift from the one that ships.
