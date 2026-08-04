# `core/boot`

Everything that has to work **before** there is a backend.

The rest of `core/` assumes a sidecar: `core/api` needs a port and a token,
`core/sse` needs a live stream. This directory is what runs when neither exists
yet — first paint, the workspace picker, the diagnostics screen.

The split mirrors the one on the Rust side (Q62/Q64): two log sinks, chosen by
boot state. Before ready, errors go through `invoke("log_client_error")` into
`%LOCALAPPDATA%\OutreachOS\logs\boot.log`. After ready, they go to
`POST /api/v1/client-logs` and land in the workspace log.

| File                    | Role                                                                 |
| ----------------------- | -------------------------------------------------------------------- |
| `clientErrors.ts`       | `window.onerror` + `unhandledrejection` capture, with the loop guard |
| `BootErrorBoundary.tsx` | React error boundary; also reveals the window on mount (Q77)         |
| `appReady.ts`           | The `invoke("app_ready")` call that races Rust's 3s watchdog         |
| `bootState.ts`          | Reducer over Rust's `boot://state` snapshots (checkpoint 3)          |

Nothing here may import `core/api` or `core/sse`. That is the whole point of
the directory, and it is the one boundary ESLint cannot express — `core` may
import `core`.
