# OutreachOS

A modular desktop workspace for outbound sales. Version 1 ships exactly one
module: **Video Composer** — generate personalized outreach videos in batches by
overlaying one reusable talking-head video onto many website screen recordings.

The application makes **zero network calls of any kind**. Not for telemetry, not
for updates, not for anything.

**Target platform:** Windows 11. Code is written cross-platform-clean.

---

## Specification

Three documents are the locked contract. They are never edited to reflect a code
change — see [`docs/decisions/`](docs/decisions/).

| Document             | Covers                                  |
| -------------------- | --------------------------------------- |
| [`PRD.md`](PRD.md)   | Scope, phases, behavioral specification |
| [`Tech.md`](Tech.md) | Technology stack, versions, rationale   |
| [`DB.md`](DB.md)     | Schema, JSON contracts, state enums     |

---

## Prerequisites

| Tool             | Version                       | Notes                                                                        |
| ---------------- | ----------------------------- | ---------------------------------------------------------------------------- |
| Node.js          | 22 (see `.nvmrc`)             |                                                                              |
| pnpm             | 11+                           | `corepack enable`, or `npm install -g pnpm`                                  |
| Python           | 3.12 (see `.python-version`)  | `uv python install 3.12`                                                     |
| uv               | 0.11+                         | Install standalone — a pip-installed uv behind a pyenv shim will be shadowed |
| Rust             | stable-x86_64-pc-windows-msvc | `winget install Rustlang.Rustup`                                             |
| MSVC Build Tools | 2022, C++ workload            | Required by Rust's MSVC toolchain for `link.exe`                             |
| WebView2         | Evergreen runtime             | Ships with Windows 11                                                        |

```powershell
winget install --id Rustlang.Rustup -e
```

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--wait --quiet --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

> **WebView2 note:** the frontend targets `esnext` because Windows 11 ships an
> evergreen WebView2 runtime. If this ever has to run against an enterprise
> fixed-version runtime, lower `build.target` in `frontend/vite.config.ts`.

---

## Setup

```bash
pnpm install
```

```bash
uv sync --directory backend
```

---

## Commands

| Command             | Does                                                 |
| ------------------- | ---------------------------------------------------- |
| `pnpm lint`         | ESLint + Ruff                                        |
| `pnpm typecheck`    | `tsc --noEmit` + mypy strict                         |
| `pnpm test`         | Vitest + pytest                                      |
| `pnpm build`        | Typecheck and build the frontend                     |
| `pnpm format`       | Prettier (TS/JS/MD) + Ruff format (Python)           |
| `pnpm sync-version` | Propagate the root `package.json` version everywhere |

Each of these has `:js` and `:py` variants for running one side alone.

The root `package.json` **version is authoritative**. `pnpm version minor` bumps
and tags in one command; `tauri.conf.json` reads it natively; `sync-version`
propagates it to `Cargo.toml`, `backend/pyproject.toml`, and `_version.py`. CI
fails if any of them drift.

---

## Layout

```
frontend/     React 19 + TypeScript + Vite       core/ and modules/, isolation enforced by ESLint
src-tauri/    Tauri 2 shell (checkpoint 2)       thin: window, sidecar lifecycle, native dialogs
backend/      FastAPI sidecar                    all domain logic lives here
vendor/       Pinned FFmpeg binaries             gitignored, fetched by script
scripts/      Repo tooling
docs/         Decision records and verification checklist
```

Rust is deliberately thin — a shell, not a third business-logic layer. The
frontend never executes FFmpeg; Python owns all rendering.

---

## Conventions

Conventional Commits with module scopes: `core`, `shell`, `backend`, `ui`,
`tokens`, `db`, `ci`, `docs`, `deps`, `build`. `video-composer` appears from P2.

Design tokens are the only source of visual values — hardcoded colors and
spacing are a review failure. shadcn provides primitives; check its registry
before writing any component.
