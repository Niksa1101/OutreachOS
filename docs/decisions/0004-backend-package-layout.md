# ADR-0004: Backend package layout and FFmpeg location

**Status:** Accepted — **supersedes Tech.md §4.3**, which shows the backend tree
rooted at `backend/app/` with `vendor/ffmpeg/` nested inside it.

---

## Context

Tech.md §4.3 specifies:

```
backend/app/
  core/  modules/  rendering/  vendor/ffmpeg/
```

Two problems.

**The import root.** `app` is a common enough top-level package name that a
transitive dependency could collide with it, and PyInstaller flattens the module
namespace in frozen builds — precisely where such a collision would be hardest to
diagnose.

**FFmpeg's home.** Placing the binaries inside the Python package makes them a
package asset, which means PyInstaller re-bundles ~180 MB on every re-freeze and
the same path resolver has to serve both Python's own data files and third-party
executables.

## Decision

**Layout:** `backend/src/outreachos_backend/`, a `src` layout with `hatchling` as
the build backend. `uv sync` installs it editable, which guarantees tests import
the installed package rather than whatever happens to be in the working
directory.

**FFmpeg:** a top-level `vendor/ffmpeg/` at the repository root, gitignored,
populated by `scripts/fetch-ffmpeg.ps1` from a pinned, checksummed LGPL release.
It ships as a **Tauri resource**, and Tauri passes the _directory_ to the backend
as a CLI argument.

The directory, not the executable: P1 needs `ffprobe.exe` as well, and one
argument cannot disagree with itself the way two can.

This draws a clean seam. `resource_path()` handles Python's own data files
(`alembic.ini`, `versions/`) and resolves `sys._MEIPASS`. FFmpeg arrives as
configuration and never touches that helper.

## Alternatives considered

- **Flat layout, `backend/outreachos_backend/`.** One less directory level, but
  loses the src-layout guarantee that tests exercise the installed package.
- **Keep `app` as the package name.** Rejected for the frozen-build collision
  risk; the rename is free now and expensive later.
- **FFmpeg inside the PyInstaller bundle as `datas`.** Rejected: re-bundles
  180 MB per freeze and conflates two unrelated kinds of resource.

## Consequences

- Dev resolves `<repo>/vendor/ffmpeg/`; release resolves `resource_dir()/ffmpeg/`.
  Same `cfg!(debug_assertions)` branch that resolves the sidecar itself.
- `.gitignore` targets `vendor/ffmpeg/*`, not a path under `backend/`.
- Licensing obligations ship in `THIRD-PARTY-LICENSES.md` alongside the OFL fonts.

## References

Questionnaire Q52, Q98, Q115. Tech.md §4.3, §5.
