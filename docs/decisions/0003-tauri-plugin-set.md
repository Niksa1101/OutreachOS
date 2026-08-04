# ADR-0003: Tauri plugin set — no `shell`, plus `clipboard-manager`

**Status:** Accepted — **supersedes Tech.md §2**, which assigns sidecar
management to Tauri and implies its sidecar plugin.

---

## Context

Tech.md §2 makes Tauri responsible for "spawning, supervising, and terminating
the Python backend." The idiomatic implementation is `tauri-plugin-shell`'s
sidecar API.

Three P0 requirements need control that API does not expose cleanly:

1. **stdin held open for the process lifetime** — it carries the token in, and
   its EOF is the shutdown signal.
2. **A Windows Job Object with `KILL_ON_JOB_CLOSE`** — the only mechanism that
   makes orphaned Python processes impossible when Tauri dies unexpectedly.
3. **`CREATE_NO_WINDOW`** — without it the packaged build flashes a console
   window on every launch.

Separately, the diagnostics screen offers `Copy to clipboard`. That screen
renders precisely when the user is already stuck, which makes an untested
capability there worse than it looks.

## Decision

Spawn the sidecar with `std::process::Command` directly. Rust still owns the
sidecar's entire lifecycle — that part of Tech.md §2 is unchanged — it simply
does not go through the plugin to do it.

Final plugin set: `dialog`, `store`, `window-state`, `single-instance`, `opener`,
`clipboard-manager`.

No `fs` plugin — file work happens in Rust commands, which is also why
`read_log_tail` takes a `"boot" | "backend"` discriminant rather than a path:
traversal is impossible by construction rather than prevented by validation.

No `log` plugin — Rust logs through `tracing` + `tracing-appender`, which is a
crate rather than a plugin and therefore does not affect the capability set.

## Alternatives considered

- **`tauri-plugin-shell` sidecar API.** Rejected: cannot deliver all three of the
  requirements above.
- **`navigator.clipboard.writeText` with no plugin.** It very likely works —
  `*.localhost` is potentially-trustworthy per spec, Chromium implements that,
  and a button click supplies the required transient activation. Rejected on cost
  asymmetry: the plugin is one line and one capability entry, while the failure
  mode is a dead button on the one screen that only appears when something is
  already broken, found by a user rather than by us.

## Consequences

- The sidecar executable needs **no target-triple suffix**. Tauri's `externalBin`
  bundling would require `outreachos-backend-x86_64-pc-windows-msvc.exe`; with
  manual spawn it ships as a plain resource resolved through `resource_dir()`.
- Job Object semantics mean there is no clean shutdown path when Tauri itself is
  killed. Stale `.oos-lock` files are therefore the normal case, not the
  exception, and the takeover path must be the well-tested one.

## References

Questionnaire Q37, Q38, Q49, Q79, Q83, Q103. Tech.md §2, §4.3.
