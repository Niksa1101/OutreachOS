# `vendor/`

Third-party binaries that ship with the application but are never committed to
this repository.

## `ffmpeg/`

Static FFmpeg and FFprobe builds, fetched by `scripts/fetch-ffmpeg.ps1` (P1)
from a **pinned, checksummed release tag** — never a "latest" URL, because those
move and would invalidate the checksum.

Two properties are load-bearing and were decided deliberately:

- **LGPL build, not GPL.** Invoking FFmpeg as a subprocess is defensible
  aggregation, but distributing a GPL binary inside the installer carries a
  source-offer obligation the LGPL shared build simply does not. This is baked
  into the pinned URL, so it is expensive to reverse later.
- **Version pinned.** Filter behaviour changes between builds, and silent visual
  drift across a batch of 30 client-facing videos is the worst failure mode this
  application has. Upgrading requires a full golden-frame re-verification.

These are **not** a Python package asset. Tauri passes the directory containing
`ffmpeg.exe` and `ffprobe.exe` to the backend as a CLI argument — one argument
rather than two that could disagree. See
`docs/decisions/0004-backend-package-layout.md`.

License texts ship in `THIRD-PARTY-LICENSES.md` alongside the OFL font licenses.
