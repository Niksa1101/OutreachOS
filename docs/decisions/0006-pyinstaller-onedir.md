# ADR-0006: PyInstaller `onedir`, not `onefile`

**Status:** Accepted — **supersedes Tech.md §4 and PRD §7 (P6)**, both of which
describe the backend as "a single sidecar executable."

---

## Context

`onefile` produces one `.exe`, which is what "single sidecar executable"
describes. It achieves that by extracting the entire bundle to `%TEMP%` on every
launch.

Two consequences matter here:

1. **Cold start.** The extraction cost is paid on every single launch, and it
   scales with bundle size. It is the dominant term in sidecar startup time.
2. **Antivirus.** Self-extracting-to-temp-then-executing is the shape AV
   heuristics flag hardest — on a corporate machine this is a real risk of the
   sidecar simply not starting.

The handshake budget (10s for the control line, 20s for `/health`) was sized
generously specifically to absorb `onefile` cold starts on a machine with
aggressive AV scanning. That is treating the symptom.

## Decision

Build with `onedir`. The sidecar ships as `outreachos-backend.exe` alongside its
`_internal/` directory, both under a Tauri resource directory.

## Alternatives considered

- **`onefile`** (Tech.md as written). Rejected for startup cost and AV
  behaviour. Its only advantage is tidiness inside a directory the user never
  opens.
- **Embedded Python runtime instead of PyInstaller.** Retained as PRD §9 risk 5's
  fallback if freezing FastAPI/uvicorn/SQLAlchemy proves intractable in P6.

## Consequences

- The release-mode sidecar resolver targets
  `resource_dir()/backend/outreachos-backend.exe`, not a single loose file. This
  had to be decided in P0 rather than P6, because the resolver is written in
  checkpoint 3 and rewriting it later would also mean redoing the bundler config.
- The 10s / 20s handshake budgets become generous rather than tight. They are
  kept as-is — a budget that is comfortable on a slow machine is not a cost.
- Installer size is marginally larger; startup is substantially faster.

## References

Questionnaire Q76, Q79, Q98. Tech.md §4; PRD §7 (P6), §9 risk 5.
