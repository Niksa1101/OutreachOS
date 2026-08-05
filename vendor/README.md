# `vendor/`

Third-party binaries that ship with the application but are never committed to
this repository.

## `ffmpeg/`

Static FFmpeg and FFprobe builds, fetched by `scripts/fetch-ffmpeg.ps1` (P1)
from a **pinned, checksummed release tag** — never a "latest" URL, because those
move and would invalidate the checksum.

Two properties are load-bearing and were decided deliberately:

- **GPL build, static executables.** ADR-0007 supersedes P0's LGPL choice: libx264
  is GPL-only and is the named CPU fallback in Tech.md §5. Source-offer compliance
  is handled now — the matching FFmpeg source tarball is archived under
  `vendor/ffmpeg/source/` by the fetch script.
- **Version pinned.** Filter behaviour changes between builds, and silent visual
  drift across a batch of 30 client-facing videos is the worst failure mode this
  application has. Upgrading requires a full golden-frame re-verification.

These are **not** a Python package asset. Tauri passes the directory containing
`ffmpeg.exe` and `ffprobe.exe` to the backend as a CLI argument — one argument
rather than two that could disagree. See
`docs/decisions/0004-backend-package-layout.md`.

License texts ship in `THIRD-PARTY-LICENSES.md` alongside the OFL font licenses.
