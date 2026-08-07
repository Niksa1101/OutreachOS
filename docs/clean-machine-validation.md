# Clean-machine validation (ticket 29)

Record of packaged-build validation on a Windows machine that has never seen
this project — no Python, no FFmpeg on PATH, no development tooling.

**Last updated:** 2026-08-07  
**Packaged build tested:** *(not yet run — blocked on tickets 27–28)*

---

## Scope

Ticket 29 validates the installer end-to-end and completes diagnostics coverage
for failure modes that only exist in a packaged build:

| Failure | Diagnostic code | Retry | Choose Workspace |
|---|---|---|---|
| Sidecar won't launch | `sidecar_spawn_failed` | Yes | No |
| Port bind fails | `port_bind_failed` | Yes | No |
| Bundled FFmpeg missing | `ffmpeg_missing` | Yes | No |
| Bundled FFmpeg unrunnable | `ffmpeg_unrunnable` | Yes | No |
| Workspace folder missing | `workspace_missing` | Yes | Yes |
| Workspace folder unwritable | `workspace_unwritable` | Yes | Yes |

---

## Code changes landed for ticket 29

Before the first clean-machine run, the following gaps were closed in code:

1. **`ffmpeg_missing` / `ffmpeg_unrunnable`** — the backend now probes bundled
   FFmpeg during boot. A missing or unrunnable binary sets `status: degraded` on
   `/health` instead of reaching Campaigns with a dead render worker.
2. **`port_bind_failed`** — when Python cannot bind `127.0.0.1:0`, it writes a
   `port_bind_failed` marker to stderr. Rust maps that to a named diagnostic
   instead of a generic `handshake_timeout`.
3. **Presentation + tests** — every diagnostic code has user-facing copy, action
   sets (`Retry` / `Choose Workspace` only where they help), and automated
   contract tests in Rust, Python, and Vitest.

Logs on a failed start:

- **Pre-backend failures** (spawn, workspace validation): `%LOCALAPPDATA%\OutreachOS\logs\boot.log`
- **After the sidecar starts** (including FFmpeg / migration / port bind):
  `<workspace>\logs\outreachos.log` — both are readable from the diagnostics screen.

---

## Clean-machine test run

> Fill this section after running the installer from ticket 28 on a VM or spare
> machine with no dev dependencies.

| Step | Result | Notes |
|---|---|---|
| Installer builds (`pnpm run build:installer`) | | |
| Installs without Python / FFmpeg / dev tools | | |
| First launch → workspace picker | | |
| Workspace init → database created | | |
| Reaches Campaigns screen | | |
| `boot.log` written on failure | | |
| `outreachos.log` written after sidecar starts | | |

### Injected failure checks (optional, on same VM)

| Scenario | Expected code | Observed | Pass |
|---|---|---|---|
| Rename/remove sidecar exe | `sidecar_spawn_failed` | | |
| Block FFmpeg exe (rename one binary) | `ffmpeg_missing` or `ffmpeg_unrunnable` | | |
| Point workspace at removed folder | `workspace_missing` | | |
| Point workspace at read-only folder | `workspace_unwritable` | | |

---

## Findings and follow-ups

*(Record anything that broke, had to change, or needs a new ticket.)*

| # | Finding | Resolution |
|---|---|---|
| | | |

---

## Related

- [`Tickets/29-clean-machine-validation.md`](../Tickets/29-clean-machine-validation.md)
- [`Tickets/28-windows-installer-sidecar-lifecycle.md`](../Tickets/28-windows-installer-sidecar-lifecycle.md)
- [`Tickets/27-pyinstaller-sidecar-ffmpeg.md`](../Tickets/27-pyinstaller-sidecar-ffmpeg.md)
- PRD §6.8 — startup failure surfaces
