# P0 Specification Interview — 126 items

The complete record of the questions resolved before any P0 code was written,
across six rounds. Each entry gives the question, the decision, and — where the
answer deviated from the recommendation — the reasoning verbatim. **The
rationales are the point of this document.** A decision without its rationale
cannot be re-evaluated later; it can only be obeyed or overturned blindly.

Items that *elaborate* the locked specs live here. Items that *contradict* one
also carry an ADR that names the superseded section. See [`README.md`](README.md).

Notation: `▲` marks a deviation from the recommended option. `′` marks a variant
of an option rather than a clean choice.

---

## Round 1 — Repository, sidecar, workspace, frontend, design, CI (Q1–Q30)

### A. Repository & toolchain

**Q1 — Repo root layout.** `frontend/`, `backend/`, `src-tauri/` flat at root.

**Q2 — Git initialization. ▲** Init locally on `main` **and** use the existing
remote. The repo already exists at `github.com/Niksa1101/OutreachOS.git`, so this
was settled: `git init` on `main`, `.gitignore` in the first commit, add `origin`,
push — with confirmation before the first push, since that is outward-facing.

**Q3 — Dev orchestration.** `pnpm dev` at root → `tauri dev` → Tauri spawns the
Python sidecar from the uv venv.

**Q4 — Python dependency layout.** Single `backend/pyproject.toml`, venv at
`backend/.venv`, uv-managed.

**Q5 — Version pinning files.** `.nvmrc` + `.python-version` +
`rust-toolchain.toml` + both lockfiles.

**Q6 — Conventional Commits enforcement.** Documented in the README, not enforced
by hooks. Solo project.

### B. Sidecar, transport, IPC

**Q7 — Sidecar in dev vs packaged.** Dev spawns
`backend/.venv/Scripts/python.exe -m outreachos_backend`; production spawns the
PyInstaller executable. Same spawn code, different resolved path.

**Q8 — Port allocation. ▲** Python binds and reports, not Rust.

> A's race is small but real on Windows, and you need a stdout channel anyway.
> Python creates the socket, binds to port 0, prints `PORT <n>` on stdout, then
> hands the socket to uvicorn via `Server.run(sockets=[sock])`. Rust parses the
> line. Zero race, ~10 extra lines. This composes with Q10-A rather than
> replacing it — Rust learns the port from stdout, frontend still gates rendering
> on `/health`.

See [ADR-0002](0002-port-allocation-in-python.md).

**Q9 — Token generation and delivery to the frontend.** Rust generates a 32-byte
random token; the frontend fetches it via `invoke("get_backend_info")`. (Delivery
*to Python* moved to stdin — see Q34.)

**Q10 — Readiness handshake.** The frontend polls `GET /api/v1/health` until 200
or timeout, then renders.

**Q11 — Sidecar death.** Detect exit → diagnostics screen with `Retry`. Manual
restart only; matches the PRD exit criteria literally.

**Q12 — SSE contract.** One endpoint `GET /api/v1/events`, named events, JSON
payload, heartbeat every 15s.

### C. Workspace & database

**Q13 — The ordering problem (backend needs a DB path; the path is the
workspace). ▲** Variant B′ — no restart, and the sidecar is not spawned until a
workspace exists.

> The ordering problem dissolves if the sidecar simply isn't spawned until a
> workspace exists:
>
> - Rust reads the pointer from app-data. Present → spawn sidecar with
>   `--workspace <path>`.
> - Absent → don't spawn. Frontend renders the picker; validation runs as a Rust
>   command (`validate_workspace`), no backend needed. On pick, Rust writes the
>   pointer, then spawns.
> - Changing workspace later (P5) = kill + respawn. Same code path.
>
> This gives you A's "no restart on first run" and D's single invariant: the
> backend never exists without a workspace. A's alternative — a backend with two
> lifecycle states and a `/workspace` mutation endpoint — buys nothing and
> permanently complicates every later phase's assumptions about what `/health`
> means.

**Q14 — Workspace validation rules. ▲** Must exist, be writable, and be either
empty or already contain `outreachos.db` — all blocking. Plus a soft warning:

> Hard-refusing OneDrive paths will misfire constantly: Windows 11 puts
> `Documents` under OneDrive by default. So: A's rules are blocking; a detected
> sync/network path is a dismissible warning with "choose anyway."

**Q15 — Workspace pointer storage. ▲** Pointer in a dedicated `workspace.json`;
window state delegated to `tauri-plugin-window-state`.

> Hand-rolled restore gets multi-monitor unplug and offscreen-position cases
> wrong, and the plugin is one line.

**Q16 — Alembic scope in P0.** One initial migration creating the full DB.md
schema. P1's CLI and P2 both need it, and "never wipe the DB" makes a real
baseline valuable.

**Q17 — Migration failure behavior.** Catch, log, keep the process alive serving
`/health` with `status: degraded`; the frontend shows diagnostics. PRD §6.8
explicitly says "rather than crashing the sidecar."

### D. Frontend shell

**Q18 — Router style.** Code-based route tree. File-based routing would fight the
requirement that modules register their own routes.

**Q19 — Module registry shape.** `ModuleDefinition { id, label, icon, navItems[],
routes[] }` in a static array — modules are imported there, one line each.

**Q20 — Cross-module import lint rule.** `eslint-plugin-boundaries` with element
types. Expresses the actual rule and gives good errors.

**Q21 — Path aliases and TS strictness.** `@/core/*`, `@/modules/*`; `strict` +
`noUncheckedIndexedAccess` + `exactOptionalPropertyTypes`.

> Flagged at the time: `exactOptionalPropertyTypes` will friction against
> `openapi-typescript` output in P2 (generated optional properties won't be
> `| undefined`-explicit). Worth keeping — far cheaper to adopt at line one than
> to retrofit — but expect a `satisfies`-shaped workaround or two at the API
> boundary. Not a reason to drop it.

**Q22 — Single-instance behavior.** Second launch focuses and restores the
existing window, then exits. Multi-workspace windows explicitly rejected.

**Q23 — Frontend error capture.** `window.onerror` + `unhandledrejection` + a
React error boundary → POST to the backend → the same rolling log. (Endpoint
renamed to `/api/v1/client-logs` in Q64.)

**Q24 — Log format and rotation.** Human-readable text lines, 10 MB × 5 files. A
user opens this file.

### E. Design system

**Q25 — shadcn preset resolution.** Try `--template next` first, observe what
breaks, fall back to a Vite-compatible init keeping the preset ID; record
ADR-0001 either way. The preset ID is opaque to both parties.

**Q26 — Token definition format.** CSS custom properties in
`core/tokens/tokens.css` as the single source, Tailwind v4 `@theme` mapping onto
them.

**Q27 — Visual identity.** Proposed and later approved (see Q123): zinc neutrals
in `oklch`, accent `oklch(0.58 0.15 255)`, Inter Variable + JetBrains Mono
self-hosted (OFL, subset to latin — no CDN, because a Google Fonts `<link>` would
fail silently in packaged builds), `0.5rem` base radius.

### F. API, CI, docs

**Q28 — API error envelope and type generation.** `{ error: { code, message,
details? } }` via a FastAPI exception handler; `openapi-typescript` wired in P0,
exercised from P2.

**Q29 — CI scope. ▲** Lint/typecheck/test on ubuntu, **plus `cargo fmt --check`
and `clippy` on windows-latest**.

> Rust is the most fragile code in P0 and the least covered by tests.
> `cargo fmt --check` + `cargo clippy` on `windows-latest` (no `tauri build`)
> keeps it from rotting silently. Still no release builds in CI, per the PRD.

**Q30 — P0 test and docs deliverables. ▲** Smoke tests both sides, plus
`docs/adr/0000-template.md` and `docs/decisions/p0-questionnaire.md` recording
the answers verbatim.

> Not 30 ADRs — that's ceremony. One decision log + real ADRs only for
> deviations.

---

## Round 2 — Backend architecture, lifecycle, transport, shell, hygiene (Q31–Q52)

### A. Backend architecture

**Q31 — Sync or async SQLAlchemy.** Fully sync + `def` endpoints (FastAPI
threadpools them); async only for SSE. SQLite is local and fast; `aiosqlite` adds
a driver layer for no gain.

**Q32 — SQLite connection strategy.** WAL + `busy_timeout=5000` +
`foreign_keys=ON` + `synchronous=NORMAL` on every connect, with
`check_same_thread=False`.

**Q33 — IDs and timestamps.** Python-side: UUIDv4 as `str`, ISO-8601 UTC written
by a SQLAlchemy default + `onupdate`. Keeps it testable and DB-agnostic.

> Note, not a deviation: `datetime.now(UTC).isoformat()` emits `+00:00`, not `Z`.
> Both sort correctly as strings, but pick one and route every timestamp through
> a single `utcnow_iso()` helper — mixed suffixes in one column is the kind of
> thing that surfaces two phases later as a comparison that silently fails.

**Q34 — Backend config delivery. ▲** The token goes over **stdin**, not argv or
env.

> Your Q34-A puts `--token` in argv, but Q9-A put it in env — they conflict, and
> argv is the worse of the two (any same-user process reads it from WMI /
> `Get-CimInstance Win32_Process` trivially). Since Q37-A already holds stdin open
> for the lifetime of the process, use it: Rust writes `<token>\n` as the first
> line, Python reads exactly one line at boot, then the same reader thread blocks
> on EOF for shutdown. The token never appears in argv, env, or any log.
> Remaining trio stays as CLI args (`--workspace`, `--log-level`, `--dev`),
> pydantic-settings for env overrides, args win.

**Q35 — Logging stack.** stdlib `logging` + `RotatingFileHandler`, `dictConfig`
at boot, uvicorn's loggers re-parented so access logs land in the same file.

**Q36 — `/health` payload. ▲** As specified, **plus `boot_id`**.

> Cheap, and it makes "did the sidecar silently restart?" answerable from one
> field instead of inferred from a 401. Skipping C: don't reserve a field you
> can't fill — adding one in P1 is non-breaking.

### B. Process lifecycle

**Q37 — Graceful shutdown on Windows.** Rust closes the sidecar's stdin; Python
watches for EOF on a reader thread and initiates uvicorn shutdown; hard-kill after
a 5s grace period. Works identically packaged and in dev.

**Q38 — Orphan prevention.** Windows **Job Object** with `KILL_ON_JOB_CLOSE` —
the OS guarantees it.

**Q39 — Sidecar stdout/stderr.** `@@OOS <json>` control lines parsed by Rust;
everything else forwarded verbatim into the rolling log. stderr always forwarded.

**Q40 — Stale workspace pointer. ▲** Diagnostics **plus a "Forget this workspace"
action**.

> A alone can produce a permanent boot loop into diagnostics with no exit that
> doesn't involve editing app-data by hand. "Forget this workspace" is a button
> and a store write.

**Q41 — Diagnostics taxonomy. ▲** Six codes **plus `unknown`**.

> Six codes is the right set — B's stubs are dead branches. But an unmapped
> failure must not render a blank screen, so add a fallback code carrying the raw
> error, which is also what C was really protecting against.

### C. Transport & auth

**Q42 — SSE authentication. ▲** Right approach, wrong package.

> `@microsoft/fetch-event-source` has been unmaintained since 2022 (v2.0.1) and
> has known reconnect bugs nobody is fixing. Use `eventsource` v3 (rexxars)
> instead — spec-compliant, maintained, and accepts a custom `fetch`, which is
> exactly the seam you need for the `Authorization` header. Falls back to C
> (hand-rolled, ~80 lines) if you'd rather own it; both beat inheriting an
> abandoned dep.

See [ADR-0005](0005-sse-client-library.md).

**Q43 — Token scheme and exemptions. ▲** `Authorization: Bearer`, constant-time
compare, **no exemptions** — plus dev-only token exposure.

> `/health` included — it leaks `workspace_path` (and therefore a username) so it
> shouldn't be open anyway. B's debugging need is real though: when `--dev` is
> passed, Python writes the token to `%TEMP%\outreachos-dev-token`. Curl-able in
> dev, absent in packaged builds, never in the rolling log.

**Q44 — OpenAPI docs surface.** `/docs` and `/openapi.json` enabled in dev,
disabled in packaged builds.

### D. Frontend shell

**Q45 — Tailwind version.** v4, CSS-first `@theme` + `oklch`.

**Q46 — Window chrome. ▲** Native decorations in P0, recorded as a **deferred
design task** rather than an open question, so P3 doesn't rediscover it.

> Window defaults confirmed — one caveat: clamp the 1440×900 initial size to the
> monitor work area. Tauri centers but does not clamp, so on a 1366×768 laptop
> you get a window taller than the screen with the titlebar offscreen. Mica
> skipped: it fights an opaque app background and would need real design intent
> behind it.

**Q47 — Sidebar shell.** shadcn `Sidebar` collapsible to an icon rail, sections
from the module registry, `Settings` pinned bottom, collapse state in
localStorage.

**Q48 — Workspace gate and diagnostics routing.** Root-level `beforeLoad` guard;
both are real routes outside the shell layout.

### E. Repo hygiene

**Q49 — Tauri plugins and capabilities. ▲** Drop the `shell` plugin; spawn with
`std::process::Command`.

> Q37-A (stdin held open), Q38-A (Job Object), and `CREATE_NO_WINDOW` all need
> control that `tauri-plugin-shell`'s sidecar API doesn't expose cleanly. Manual
> spawn gives you all three and removes a plugin. Final set: `dialog`, `store`,
> `window-state`, `single-instance`, `opener`. No `fs`, no `shell`, no `log`.
>
> `CREATE_NO_WINDOW` is not optional, incidentally — without it the packaged
> build flashes a console window on every launch.

See [ADR-0003](0003-tauri-plugin-set.md).

**Q50 — Lint/format toolchain.** Ruff (lint + format) + mypy strict for backend;
ESLint flat config + Prettier for frontend; `cargo fmt`/`clippy` for Rust.

**Q51 — Scaffolding depth. ▲** Full tree, with a refinement.

> Full tree per Tech.md, but on the frontend use a `README.md` per top-level
> directory rather than placeholder `index.ts` files. Empty `index.ts` stubs that
> export nothing trip `import/no-empty-named-blocks`-class lint rules and create
> importable-but-useless module paths. Backend gets the docstring treatment —
> `__init__.py` has to exist there anyway.

**Q52 — FFmpeg binaries. ▲** Gitignored + fetch script, with two pins.

> 1. Use an immutable release asset. `gyan.dev`'s "latest" URLs move; pin a BtbN
>    GitHub release by tag so the checksum stays valid.
> 2. Take the **LGPL** build, not the GPL one. BtbN ships both. Invoking FFmpeg
>    as a subprocess is defensible aggregation, but distributing a GPL binary
>    inside your installer carries a source-offer obligation that the LGPL shared
>    build simply doesn't. This is genuinely expensive to reverse — it's baked
>    into the pinned URL in the first commit — so decide it now, and vendor the
>    license texts alongside the binaries.

---

## Round 3 — Boot contract, migrations, observability, CI (Q53–Q72)

**Q53 — JS workspace shape.** pnpm workspace; root `package.json` (scripts only)
+ `pnpm-workspace.yaml`; `src-tauri/` at root with
`frontendDist: "../frontend/dist"`.

**Q54 — Boot state machine ownership. ▲** Rust owns it, **plus**:

> Window starts hidden. Set `visible: false` in `tauri.conf.json`; React calls
> `invoke("app_ready")` after the boot UI's first paint and Rust calls `show()`.
> Otherwise you get a white flash before the boot state renders. This is not D —
> the window appears at the boot UI, not at `ready`. Also make the event payload
> the full state snapshot rather than a delta, so `get_boot_state` and
> `boot://state` deserialize into the same type and React has one reducer, not two
> paths.

**Q55 — Dev-mode reload. ▲** Sidecar survives HMR; no uvicorn `--reload`; keep
`dev:backend` as a **standalone script only**.

> B's attach path means Rust grows an "external backend" branch with no stdin
> token handoff, no Job Object, and no port parse — a second lifecycle that is
> exercised only in dev and will therefore diverge from the one you ship.

**Q56 — Token lifetime on the frontend. ▲** A's lifecycle, D's encapsulation.

> Module-scoped `let` in `core/api`, not exported — the fetch wrapper and the SSE
> client both live in that module and close over it. Re-fetched on `boot_id`
> change. B is the one to avoid: putting it in a store makes it reachable from any
> component and therefore eventually logged by someone's debug `console.log`.

**Q57 — What `--dev` gates. ▲** With explicit precedence.

> `--dev` from `cfg!(debug_assertions)` gates the `%TEMP%` token file and `/docs`
> + `/openapi.json`, and sets the default log level to DEBUG. `--log-level`
> overrides that default in either direction. So A and D compose rather than
> conflict. C stays rejected — an advanced user debugging a packaged build should
> get a verbose log, not a live OpenAPI surface.

**Q58 — Alembic under PyInstaller. ▲** In-process, plus one trap:

> Alembic's stock `env.py` calls `fileConfig(config.config_file_name)`, which
> reconfigures the root logger and destroys the `dictConfig` handlers from Q35.
> Migrations run at boot, so this silently kills logging for the rest of the
> process. Delete that line from `env.py` in the first commit. `script_location`
> must also resolve absolute under `sys._MEIPASS`, and `versions/` needs to be in
> `datas` — a frozen build with zero migration files "succeeds" at `upgrade head`
> against an empty script directory, which is the worst possible failure mode.

**Q59 — Migration completeness. ▲** Full schema **with models and Pydantic
validation in both layers**, and one rule:

> Define each enum once as a `StrEnum`; the app imports it, Pydantic validates
> against it.
>
> The rule: migration files hardcode the literal values, they do not import the
> app enum. A migration is a frozen historical snapshot — if it imports a live
> enum, adding a value silently rewrites the meaning of a migration that already
> ran. Q61-D's drift test is what keeps the two honest.

**Q60 — `app_settings` singleton. ▲** Seeded in the migration **and** an
idempotent `INSERT OR IGNORE` at boot.

> A missing singleton is a crash on every settings read; self-healing costs three
> lines and removes an entire class of "how did this DB get into this state"
> support work.

**Q61 — Test database strategy. ▲** Real temp dir, file-backed SQLite, real
migrations — **plus the schema-comparison drift test**, which is what makes
Q59's two layers safe to have.

**Q62 — Pre-workspace logging.** A bootstrap log in OS app-data
(`%LOCALAPPDATA%\OutreachOS\logs\boot.log`), always written.

**Q63 — Rust-side logging. ▲** Same file and `[rust]` tag, but via `tracing` +
`tracing-appender` rather than a hand-rolled appender.

> Non-blocking writes and the ecosystem-standard macros. This doesn't reverse
> Q49: `tracing` is a crate, not a Tauri plugin. B stays rejected for the decisive
> reason that Rust most needs to log precisely when Python is dead or never
> started.

**Q64 — Frontend error ingestion. ▲** Batched endpoint **plus a pre-ready sink**.

> As written there's a hole: errors thrown during boot (the picker, the
> diagnostics screen) have no backend to POST to. Route those through
> `invoke("log_client_error")` into `boot.log`, mirroring the Q62 split. Two
> sinks, chosen by boot state. Also add a loop guard — a failure inside the error
> reporter must never re-enter the reporter, or one broken response turns into an
> unbounded request storm.
>
> Naming: Q23 said `/api/v1/logs`, this says `/api/v1/client-logs`. Take
> `client-logs`; it's clearer once there's a server log endpoint to confuse it
> with.

**Q65 — SSE envelope and replay. ▲** With ids scoped to boot.

> Make the event id `<boot_id>:<seq>`, not a bare counter. On reconnect, if the
> client's `Last-Event-ID` carries a different `boot_id`, emit `resync`
> immediately — replay across a restart is meaningless because the token rotated
> and the queue state was rebuilt anyway. Without this, a seq number from a
> previous boot lands inside the current ring buffer's range and replays
> confidently wrong events. Ring buffer at ~200 is right.

**Q66 — SSE connection ownership.** One `<EventStreamProvider>` inside the
ready-state shell; handlers dispatch into TanStack Query; a `boot_id` change
invalidates the entire cache.

**Q67 — API error taxonomy. ▲** Closed set **plus `unauthorized`** — it is
emitted in P0 from the token dependency, so it belongs from the start.

**Q68 — `cargo clippy` needs `frontendDist`.** The Rust job runs the real
frontend build first. Slower, but catches config drift too.

**Q69 — Which OS runs the Python tests. ▲** `windows-latest`, not ubuntu.

> This is the one I'd push back on hardest. Windows is the only target, and the
> P0 backend touches exactly the things that differ: workspace path handling,
> SQLite file locking, and `RotatingFileHandler` — which fails to rotate on
> Windows when another process holds the file open, and your diagnostics screen is
> designed to open that file. Ubuntu CI would report green on all of it.
>
> Q29-B already puts a `windows-latest` job in the workflow for clippy, so pytest
> rides along at near-zero marginal cost. Keep the frontend lint/typecheck/vitest
> job on ubuntu — that's genuinely platform-agnostic and fast. Test where you
> ship; use ubuntu only where the platform can't matter.

**Q70 — Build order. ▲** Six checkpoints, with a sequencing correction.

> Checkpoint 1's "CI green on an empty tree" can't include the Rust job, because
> Q68-A requires a frontend build and there's no `src-tauri` yet. So: checkpoint 1
> lands the frontend + Python CI jobs; the Rust job arrives with checkpoint 2.
> Note that at checkpoint 4 the sidecar receives `--workspace` and does nothing
> with it until 5. That's honest incrementalism, not an oversight.

**Q71 — Timestamp suffix. ▲** `Z` via a single helper **plus boundary
normalization**.

> If the columns are `Mapped[str]` (per DB.md's TEXT), the Pydantic serializer is
> a guard rather than a converter — the real enforcement is that nothing
> constructs a timestamp except the helper. Put it in a `TimestampMixin` so
> `created_at`/`updated_at` are inherited, never hand-written, and the grep for
> violations is trivial.

**Q72 — Palette/typography timing.** Carried open through rounds 3–5; resolved at
Q123.

---

## Round 4 — CORS/CSP, boot edges, workspace, durability, logs (Q73–Q92)

**Q73 — CORS. ▲** Explicit allowlist, **with both dev origins**.

> Allowlist `http://tauri.localhost` and `https://tauri.localhost`; under `--dev`
> add both `http://localhost:1420` and `http://127.0.0.1:1420` — those are
> distinct origins and Vite will hand you either depending on how the webview
> resolves `devUrl`. Getting one and not the other produces a preflight failure
> that looks like a CORS misconfiguration but is actually a hostname mismatch.
>
> One reconciliation: 1420 is correct — it's `create-tauri-app`'s default and it
> must match `build.devUrl`. `allow_credentials=False` is not just safe here, it's
> load-bearing: it's what keeps the allowlist honest if anyone later reaches
> for `*`.

**Q74 — CSP. ▲** Use `devCsp`; don't null the policy in dev.

> Tauri 2 solves this directly — `app.security.devCsp` is a separate policy
> applied only in dev builds. Strict CSP in production, plus a `devCsp` that adds
> `ws://localhost:1420` and the Vite origin. Dev/prod CSP divergence becomes
> explicit config rather than "it works in dev."
>
> Two additions to the production policy:
>
> - `img-src 'self' data: blob:` — nothing in P0 needs it, but the moment P2
>   renders a thumbnail you'll hit a silent CSP block. This is the one place I'd
>   break my own "don't reserve what you can't fill" rule, because a too-tight CSP
>   fails at runtime rather than at compile time.
> - `ipc.localhost` is genuinely required. Without it `invoke` fails on Windows and
>   the entire boot state machine is dead on arrival.

**Q75 — `boot_id` ownership.** Rust generates it per spawn and passes it on the
stdin line as JSON: `{"boot_id": "...", "token": "..."}` — one format, no
positional ambiguity, room to add a field without a parser change.

**Q76 — Handshake timing. ▲** 10s / 20s budgets, **and pick `onedir`**.

> This is the actual fix for the cold-start problem you're budgeting around.
> `onefile` extracts the entire bundle to `%TEMP%` on every launch — that's where
> the multi-second start comes from, and it's also the shape AV heuristics flag
> hardest. `onedir` starts in a fraction of the time and the 10s/20s budget
> becomes generous rather than tight.
>
> Surfacing it now because it changes Q79's release branch:
> `resource_dir()/backend/outreachos-backend.exe` alongside its `_internal/`
> directory, not a single file. Deciding it at P6 means rewriting the resolver and
> the bundler config.

See [ADR-0006](0006-pyinstaller-onedir.md).

**Q77 — `app_ready` never called. ▲** Watchdog **and** the error boundary calling
`app_ready` on its own mount, so a caught crash reveals the window immediately
rather than after 3s of apparent hang.

**Q78 — Sidecar dies mid-session.** Rust's exit event is authoritative; API
connection failures never navigate on their own.

> Retry semantics made explicit: Retry re-runs the full boot state machine — new
> spawn, new token, new `boot_id`. Which means on success the frontend must
> `queryClient.clear()` before returning to the remembered route. Returning to a
> stale cache from a dead process is a subtle enough bug to name now.

**Q79 — Dev sidecar path resolution.** `cfg!(debug_assertions)` branch; both
paths logged at boot.

**Q80 — `validate_workspace`.** Existence, write probe, SQLite header sniff,
typed result with warnings.

> Plus canonicalize the path before storing it. Resolve to absolute, strip
> trailing separators, normalize case-insensitively for comparison. Otherwise
> `C:\Work\ws` and `C:\Work\ws\` become two different pointers and the lock file
> in Q83 can't match them.

**Q81 — Sync/network path detection.** `GetDriveTypeW` for `DRIVE_REMOTE`, UNC
prefix, and a provider-name path scan.

> B is worse than you'd think for this case. `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`
> marks dehydrated files, not sync-root folders — a freshly created empty
> workspace folder inside OneDrive carries no such attribute, so B misses the
> common case entirely while adding Win32 surface. The name scan you're calling
> crude is actually the more reliable signal here.
>
> Optional accuracy upgrade: OneDrive records its sync roots at
> `HKCU\Software\Microsoft\OneDrive\Accounts\*\UserFolder`. Exact, cheap, catches
> renamed roots.

**Q82 — Workspace subdirectory creation.** Python, idempotently, every boot.

**Q83 — Workspace lock file.** `.oos-lock` with `{pid, hostname, boot_id,
started_at}`; stale or foreign-host lock offers "Take over".

> A dead PID's number gets recycled, so "PID is alive" must also mean "that
> process is ours" — compare the image name, or store the process start time.
> Note that Q38's Job Object kill path means there's no clean shutdown on a Tauri
> crash, so stale locks are the normal case, not the exception. That path will run
> often enough that it needs to be the well-tested one.

**Q84 — DB newer than the app.** A seventh code, `database_newer_than_app`,
detected before upgrading.

> It satisfies D automatically given one clarification: degraded must mean zero DB
> sessions handed out, not "the DB is available but flagged." If the dependency
> that yields a session raises in degraded mode, every DB-touching route returns
> 503 and there is no path by which the app writes against a schema it doesn't
> understand. Worth stating in the code as a comment, because "degraded" is
> otherwise ambiguous enough that someone adds a read-only exception later.

**Q85 — Backup before migration. ▲** `VACUUM INTO`, not a file copy.

> This one would have cost you real data. The DB is in WAL mode, so recent
> committed transactions live in `outreachos.db-wal`, not the main file. A plain
> `shutil.copy` produces a backup silently missing the most recent work — the
> exact failure the backup exists to prevent, discovered only when someone
> restores it.
>
> `VACUUM INTO 'outreachos.db.bak-<rev>'` is atomic, consistent, single-file, and
> needs no WAL handling. Same retention (keep 3), same trigger.
>
> Add a failure policy: backup fails → do not migrate → diagnostics. Fold it into
> `migration_failed` with detail naming the backup failure, plus an explicit
> "Proceed without backup" action. Skipping a Restore action in P0 — the backup is
> one click away in Explorer, and a casually-clicked restore button is a data-loss
> vector dressed as a feature.

**Q86 — `RotatingFileHandler` on Windows.** Bounded tail reads that close
immediately, `delay=True`, and rotation wrapped so a `PermissionError` logs and
continues instead of killing the handler.

**Q87 — Diagnostics log surface. ▲** The tail must be read **Rust-side**.

> Diagnostics is displayed precisely when the backend is dead, so an API-based log
> read fails exactly when it's needed. Both files go through
> `invoke("read_log_tail", { which: "boot" | "backend" })`.

**Q88 — P0 endpoint surface.** Four: `/health`, `/events`, `/client-logs`,
`/settings`.

**Q89 — Generated API client in P0. ▲** Used and staleness-checked, **with the
spec dumped offline**.

> Don't boot the sidecar in CI to get the spec.
> `python -c "import json; from outreachos_backend.main import app;
> print(json.dumps(app.openapi()))"` produces it without a server, in-process, in
> ~1s. Then regenerate and `git diff --exit-code`. That also fixes A's wording —
> "against the live spec" implies a running backend, which makes the local dev
> script slower and the CI job fragile for no benefit.

**Q90 — P0 Settings page.** Read-only diagnostics: workspace path, versions,
`boot_id`, migration head, log path. No `Change workspace` — that's P5.

**Q91 — Token naming and preview surface. ▲** Semantic names **plus a shadcn
alias layer**.

> shadcn's components hardcode its variable names: `--background`, `--foreground`,
> `--card`, `--primary`, `--muted`, `--border`, `--ring`. If your tokens don't
> feed those, every `shadcn add` needs hand-editing forever.
>
> The composition: your semantic tier is the source of truth, and shadcn's names
> are a thin alias layer over it. Both vocabularies exist, one set of values.
> `/dev/tokens` renders both tiers so a mismatch is visible rather than inferred.
> Route registration guarded by `import.meta.env.DEV` so it tree-shakes out.

**Q92 — Git workflow.** Branch per checkpoint, PR into `main`, squash-merge.

> Scopes are good. Adding `deps` (dependency bumps, lockfile-only changes) and
> `build` (PyInstaller, bundler config) — both will otherwise get miscategorized
> into `ci` or `core`.

---

## Round 5 — API conventions, build, boot UX, quality (Q93–Q112)

**Q93 — API casing.** `snake_case` end to end. Zero mapping layer; DB, API, and
generated types all agree.

**Q94 — Types at the boundary.** `datetime` with a `Z`-emitting serializer;
`StrEnum` → OpenAPI enum → TS union; error envelope declared in `responses`.

> Override the 422. FastAPI declares its own `HTTPValidationError` automatically.
> If you install a `RequestValidationError` handler emitting your envelope without
> also overriding the declared 422 model, the generated TS types describe
> FastAPI's shape while the server sends yours — a typed client that is
> confidently wrong about the most common error.
>
> D rejected for a reason worth stating: `openapi-typescript` emits `string` for
> `format: date-time`, so parsing to `Date` in the wrapper puts runtime values out
> of agreement with the generated types. Keep them strings; parse at display.

**Q95 — Trailing slashes.** `redirect_slashes = False`, hard no-trailing-slash
convention. The CORS spec forbids following redirects during preflight.

> Set it on the router. `app.router.redirect_slashes = False` is the form
> guaranteed to work across FastAPI versions; the constructor kwarg isn't reliably
> exposed. Set it on each `APIRouter` too, since routers carry their own flag.
> Pleasant side effect: a mistyped path returns a clean 404 instead of a redirect
> the preflight silently refuses to follow.

**Q96 — Fetch wrapper policy. ▲** With an explicit per-call timeout override.

> A already says "default," so the override is implied; making it explicit in the
> signature costs one optional field and avoids a wrapper rewrite. One note on how
> it should be used: P1 renders should be job-submission plus SSE progress, not a
> long-held HTTP request. If the timeout override starts appearing on render
> calls, that's a signal the async job path was skipped, not that 15s was too
> short.

**Q97 — Version source of truth. ▲** `package.json`, not `tauri.conf.json`.

> Both need a sync script, so pick the source with the better ergonomics:
>
> - `pnpm version minor` bumps and git-tags in one standard command. There's no
>   equivalent for `tauri.conf.json`.
> - Tauri 2 reads `"version": "../package.json"` natively, so that file needs no
>   syncing at all.
> - The script then propagates to `Cargo.toml` and `pyproject.toml` only — two
>   targets instead of three.

**Q98 — FFmpeg location. ▲** Tauri resource, **and it moves the vendor path**.

> FFmpeg is no longer a Python package asset, so `backend/app/vendor/ffmpeg/` is
> the wrong home. Move it to a top-level `vendor/ffmpeg/` and update Q52's
> `.gitignore` entry and the fetch script target accordingly. Dev resolves
> `<repo>/vendor/ffmpeg/`, release resolves `resource_dir()/ffmpeg/`, same `cfg!`
> branch as Q79.
>
> And pass the directory, not the executable — P1 needs `ffprobe.exe` too, and one
> arg beats two that can disagree.

See [ADR-0004](0004-backend-package-layout.md).

**Q99 — Vite build target. ▲** `esnext`, but skip the browserslist entry.

> Vite doesn't read browserslist for `build.target` without an extra plugin, so a
> browserslist file would be inert documentation that looks load-bearing — worse
> than a comment.

**Q100 — Production sourcemaps. ▲** `hidden`, but don't commit the maps.

> They change on every build and are a few MB each; committing them bloats history
> permanently for a file whose only consumer is a one-off symbolication. Archive
> them alongside the installer. D rejected — runtime symbolication requires the
> maps to be reachable from the client, which is exactly what `hidden` prevents.

**Q101 — Window-state restore.** Plugin restores, Rust clamps, then `show()`.

> Clamp size, not just position. A window restored at 2560×1400 onto a 1920×1080
> panel is positioned fine and still unusable. Note also that Q38's Job Object
> kill means geometry won't always be saved on a crash — stale-but-valid geometry
> is acceptable.

**Q102 — Boot UI.** Wordmark + status line, no spinner before 400ms, no
artificial minimum.

**Q103 — Clipboard. ▲** Add `tauri-plugin-clipboard-manager` now.

> `navigator.clipboard.writeText` almost certainly works — `*.localhost` is
> potentially-trustworthy per spec, Chromium implements it, and a button click
> supplies the transient activation. But the cost asymmetry decides it: the plugin
> is one line, while the failure mode is a dead button on the one screen that only
> renders when the user is already stuck, discovered by a user rather than by you.
>
> Not a reversal of Q49 — that decision was "minimum viable set," and a
> break-glass surface makes clipboard viable-set.

**Q104 — Degraded-mode UI. ▲** Route to diagnostics; the shell never mounts.

> C is broken on inspection: Settings reads `/api/v1/settings`, which is a DB
> route, which 503s in degraded. It cannot be the screen that names the problem.
>
> So A, with the requirement stated explicitly: the diagnostics screen must be
> DB-free. Everything it shows comes from `/health` and Rust invokes. Nothing on
> that screen may touch a DB route, or the screen fails exactly when it's needed.

**Q105 — Production log levels.** `INFO` default; lifecycle only; request logging
in middleware at DEBUG.

> Confirming it already covers the concern: 4xx/5xx responses log at
> WARNING/ERROR from the middleware regardless of the configured level. That's
> "errors," not request logging.

**Q106 — Heartbeats vs the ring buffer. ▲** Named `heartbeat` with the `id:`
field **omitted**, not a comment frame.

> Your analysis of the buffer problem is exactly right, and the fix is right —
> heartbeats must not consume sequence ids. But comment frames break Q42:
> `eventsource` v3 does not surface `:` comments to consumers, so the 45s watchdog
> would have nothing to observe and would fire during a perfectly healthy idle
> connection, tearing down and reconnecting every 45 seconds forever.
>
> `id:` is optional in SSE. An event sent without an `id:` field does not update
> the client's `Last-Event-ID`. So a named `heartbeat` event with no id gives you
> everything you wanted while remaining a real event the client can attach a
> watchdog reset to.

**Q107 — Rust tests.** `cargo test` on the pure-logic pieces: validation rules,
path canonicalization, monitor clamping, control-line parser. No Tauri runtime
needed.

**Q108 — Vitest scope. ▲** Boot reducer + fetch wrapper **plus the token-alias
test**.

> The token-alias test is the automated guard for Q91's mapping layer, which is
> otherwise verified only by looking at `/dev/tokens` and remembering to. One
> constraint: make it a static parse (postcss), not a jsdom `getComputedStyle`
> check. jsdom's `var()` chain resolution is unreliable and you'd be debugging the
> test rather than the tokens.

**Q109 — Verification checklist. ▲** A living document, extended by every later
phase.

> The checklist is the regression suite for everything automation structurally
> can't reach, and every later phase adds failure modes to it (P4's queue, P6's
> packaging). Freezing it at P0 wastes the artifact.

**Q110 — Lint parity.** Ruff line length 100 to match Prettier; `E, F, I, UP, B,
SIM, RUF`; `ANN` off; mypy strict with SQLAlchemy's native typing.

> Plus per-file mypy ignores for `alembic/versions/*`. Generated migration files
> are unannotated `op.` calls that produce dozens of strict-mode errors carrying no
> signal. Ruff still formats and lints them.

**Q111 — Decision record format. ▲** MADR-lite **with cross-links**.

> The cross-links are the difference between an ADR that states a decision and one
> that lets you reconstruct why the alternatives lost. Cheap at write time,
> expensive to reconstruct later.

**Q112 — Questionnaire vs the specs. ▲** Specs unmodified, **plus a contradiction
rule**.

> Some of what we've settled contradicts rather than elaborates — Q42 drops
> `EventSource`, Q49 drops the `shell` plugin, Q98 moves FFmpeg out of the Tech.md
> tree. If those live only in the questionnaire, the specs quietly become wrong.
>
> So: elaborations go in the questionnaire; contradictions get their own ADR with
> explicit "Supersedes Tech.md §X" in the Status field. The spec stays
> byte-identical and locked, and anyone reading §3.4 can find what overrode it via
> the ADR index.

---

## Round 6 — Final seams (Q113–Q126)

**Q113 — `/health` and `migration_head`.** Captured once at boot into a
process-level `BootReport`; `/health` serializes that struct and never opens a
session.

> Make `BootReport` carry everything the diagnostics screen needs, not just
> migration state: head, current revision, status, backup path, error detail,
> workspace path, app and backend version, `boot_id`, and both log paths. Q104
> requires that screen to be DB-free, and this struct is the only thing standing
> between it and a session. `?refresh=1` rejected because it would have to re-run
> migrations to mean anything, which puts DB access back into `/health` and
> duplicates Retry.

**Q114 — `/events` in the OpenAPI schema.** `include_in_schema=False`; hand-written
TS event types with a cross-language parity test.

> Scope the test deliberately: assert parity on the set of event names and the
> envelope's required top-level keys. That's the cheap, robust check. Full
> payload-shape parity across two languages is where this gets fragile and starts
> wanting a generator.

**Q115 — Python layout.** `src` layout, `backend/src/outreachos_backend/`,
hatchling, installed editable by `uv sync`.

**Q116 — Windows path length. ▲** Pick-time validation, plus two P1 handoffs.

> Reject over ~150 chars, warn over ~120; declare `longPathAware` as
> belt-and-braces. Two additions:
>
> - Pass FFmpeg args as a list, never a shell string. Python's `subprocess` uses
>   `CreateProcessW`, so wide characters survive intact — but only if you're not
>   round-tripping through a shell.
> - Put a non-ASCII workspace path on the manual checklist. Something like
>   `C:\Users\...\Тест Проект\` — the bundled FFmpeg's handling of non-ASCII argv
>   on Windows is the piece that isn't guaranteed by anything in your control.
>
> `longPathAware` depends on the machine-wide `LongPathsEnabled` policy the app
> can't set without admin, and the static FFmpeg builds aren't manifested for it
> regardless. Pick-time validation is the actual defense.

**Q117 — Refused workspace locations.** Drive root, the app's install directory,
and `%LOCALAPPDATA%\OutreachOS`.

> It composes with a rule you already have. Q14 requires the folder to be empty or
> already contain `outreachos.db`. That alone rejects Desktop root,
> `%USERPROFILE%`, and Documents — they're never empty. And `Program Files`
> additionally fails the write probe for a non-admin user. Three hard refusals
> plus the emptiness rule is a complete set without the paternalism.

**Q118 — Shutdown sequence.** Stop accepting → close SSE → uvicorn shutdown →
remove `.oos-lock` → flush handlers → exit 0. Lock removal late, deliberately.

**Q119 — `boot.log` growth.** 2 MB × 3, appended across runs with a
`=== boot <boot_id> <ts> ===` separator per launch.

**Q120 — DB session pattern. ▲** The dependency **never commits**.

> This is the pattern P1–P5 inherits, so it's worth the paragraph.
>
> Commit-on-success in the dependency's teardown runs after the route returns and
> the response model is serialized. A commit that fails there — constraint
> violation, disk full, lock timeout — happens when the response is already
> composed, so you can't map it to the error envelope cleanly and the client can
> receive a 200 for a transaction that rolled back. It also makes every read path
> a latent writer: any route that accidentally dirties the session issues a write
> on the way out.
>
> So: the dependency yields a session, rolls back on exception, closes always, and
> never commits. Services commit explicitly, inside the code that knows what the
> transaction meant and can handle its failure. A `UnitOfWork` wrapper is
> abstraction this app doesn't have the complexity to earn.

**Q121 — Repo settings and first push.** Private; inspect remote, initial commit,
**ask before pushing**, branch protection after the first CI run.

> Ordering: enable branch protection after the first CI run completes. Required
> status checks can only be selected from checks GitHub has actually observed, so
> doing it before checkpoint 1's run means the requirement silently isn't
> attached.
>
> Fallback: branch protection on private repos has historically been plan-gated on
> GitHub Free. If it isn't available, fall back to no protection, say so, and note
> it here rather than working around it.

**Q122 — CI topology.** Ubuntu frontend job producing a `dist/` artifact; Windows
job consuming it.

> The Windows job needs no Node at all. Add `Swatinem/rust-cache` — on Windows the
> cargo target directory is large enough that an uncached job dominates run time.
> D rejected: with every checkpoint going through a PR, restricting Windows to PRs
> and `main` means the branch never gets Rust or Python signal until the PR opens,
> which is the wrong moment to find out.

**Q123 — Palette and typography. ▲** Approved as proposed, **written now** rather
than deferred to checkpoint 6.

> I'm reversing my own D-sequenced recommendation because my framing of it
> undercut it: I argued the preset informs structure, not identity, and Q91's alias
> layer means the structure is the same regardless. If that's true — and I think it
> is — then the identity decision was never actually waiting on the preset.
> Deferring bought nothing except an open item carried into implementation, and the
> downside is one rewrite of roughly forty lines of CSS in the one file
> specifically designed to isolate those values.
>
> If the preset ships a well-designed palette that's better than this, ADR-0001
> records the override and we take it. That's a normal outcome, not a failure of
> the decision.

**Q124 — Diagnostics code enumeration.** Nine: `workspace_missing`,
`workspace_unwritable`, `workspace_locked`, `sidecar_spawn_failed`,
`sidecar_exited`, `handshake_timeout`, `migration_failed`,
`database_newer_than_app`, `unknown`.

> Rejecting a merge of `workspace_locked` into `workspace_unwritable`: they have
> different causes and, more importantly, different action sets — takeover versus
> pick-somewhere-else. Merging means the picker either offers "Take over" on a
> permissions failure or hides it on a lock, and both are wrong.
>
> Rejecting a split of `sidecar_exited` into at-boot vs mid-session: same
> condition, different surrounding state. Q78 already tracks whether there's a
> route to return to, so the screen can select its title from that boolean.
> Different copy, same code — splitting the enum to carry a fact the state already
> holds is how enums start drifting.
>
> Two separate namespaces from the API error codes, no shared values. Diagnostics
> codes describe why the app can't run; API error codes describe why a request
> failed. Nothing is ever both. Worth a comment on each enum saying so, because the
> temptation to reach across will arrive around P4.
>
> `handshake_timeout` covers both misses — the `PORT` line and the health poll —
> with the detail field distinguishing them.

**Q125 — Checkpoint 6 ordering.** `shadcn init` first, capture its output, then
replace values — with the explicit escape hatch if the preset's palette is better.

> One mechanical addition that makes ADR-0001 much better: commit the raw
> `shadcn init` output as its own commit before touching it. Then "what the preset
> actually contributed" is a diff in git history rather than a prose reconstruction
> in an ADR, and the ADR can just cite the SHA. Prose descriptions of generated CSS
> go stale immediately; the commit doesn't.
>
> And keep the files separated so future `shadcn add` commands can't reach the
> palette: point `components.json`'s `css` at the file holding the alias layer,
> keep `tokens.css` as a separate import owning the values.

**Q126 — Backend version in a frozen build.** `_version.py` written by the sync
script, committed, covered by the divergence check.

> Rejecting the stdin-delivery option for a concrete reason: `pnpm dev:backend`
> runs the sidecar standalone with no Rust in the picture, so a version that
> arrives over stdin makes `/health` report nothing in exactly the mode you'd use
> to debug `/health`. And an `importlib.metadata` fallback puts the literal string
> `unknown` in the field you'd ask a user to read back to you.

---

## Corrections applied late

Three items were revised after their round closed. Recorded here because the
final state is what binds.

**`.oos-lock` is not swept at next boot.** The dev token file is; the lock is not.

> Sweeping `.oos-lock` on next boot destroys Q83 entirely. If the sweep runs
> before lock acquisition, it deletes a lock that may belong to a live instance on
> another machine — the network-share case the lock exists for — and silently
> bypasses the foreign-host warning. If it runs after, it can only ever delete our
> own lock, which makes it a no-op. The lock's staleness check *is* its cleanup
> path.

**`resync` carries the current head id.** It is not buffered, but it is not
id-less.

> Omitting `id:` produces a subtler failure. `eventsource` v3 manages
> `Last-Event-ID` internally from `id:` fields, so a client that receives an
> id-less resync keeps its old stale id. Next reconnect: same uncoverable id,
> another resync, another full refetch. Forever. The ring buffer is permanently
> defeated for that client, and a flapping connection becomes a refetch storm.
>
> `resync` carries the head id at time of send and is not written into the ring
> buffer. `Last-Event-ID` advances to head, so the next reconnect resumes cleanly
> with nothing to replay, and the resync event itself can never be replayed
> because it was never buffered.

**The threat-model sentence must name the dev token file.**

> In `--dev` builds the token also exists at `%TEMP%\outreachos-dev-token`.
> Dev-only, deliberately, and gated on `cfg!(debug_assertions)` — but a
> threat-model sentence that says "only" should say it, or someone reading it in
> six months concludes the temp file is a bug and removes it.

---

## Assumptions locked without a numbered question

- `.gitattributes` with `* text=auto eol=lf`, `*.ps1 eol=crlf`, and binary entries
  for `woff2`/`exe`/`png` — without it, Prettier and `cargo fmt` fight
  `core.autocrlf` on Windows forever.
- `uvicorn.Server(config)` with `log_config=None` **and `access_log=False`** —
  the boot health poll at 250ms would otherwise write ~80 lines into a log a user
  is expected to read.
- Alembic URL passed via `config.attributes["connection"]`, never
  `set_main_option` — ConfigParser does `%`-interpolation, so a workspace path
  containing `%` would raise on a string the user chose. `alembic.ini` stays
  URL-free.
- `env.py` keeps only the online path; offline mode is deleted along with the
  `fileConfig` line.
- `secrets.compare_digest` for token comparison; a failed compare logs the source
  path but never the presented value.
- SSE client watchdog: no heartbeat for 45s → close and reconnect with
  `Last-Event-ID`.
- `--motion-*` tokens zero out under `prefers-reduced-motion`. Tokens are the only
  motion values, so nothing can bypass it.
- Motion in P0 is CSS transitions only. `motion` is not installed until something
  needs animating — an unused dependency is a lockfile entry, an audit surface,
  and a version that will be stale by the time P3 uses it.
- `eslint-config-prettier` switches off conflicting rules; Prettier runs as a
  separate command, never as an ESLint rule — that would make every format diff a
  lint error and slow the lint pass.
- `.env` precedence is explicit: CLI args > process env > `.env` file.
- `read_log_tail` takes a `"boot" | "backend"` discriminant, never a path.
  Traversal is impossible by construction rather than prevented by validation.
- lucide-react for icons. React Compiler off in P0 — stable, but it adds a Babel
  step and obscures Vite errors; revisit in P3 when the overlay editor gets
  re-render-heavy.
- TanStack Query defaults: `staleTime: Infinity`, `retry: false`, no
  window-focus refetch. This is a local backend; invalidation is event-driven,
  never time-driven.
- `vite.config.ts` sets `server.host: '127.0.0.1'` — Vite's default binds broadly
  enough to expose the dev server on the LAN, contradicting the loopback-only
  threat model everything else is built around.
- Naming: Rust crate `outreachos`, window label `main`, Python distribution
  `outreachos-backend` with import package `outreachos_backend`, sidecar
  `outreachos-backend.exe` (**no target-triple suffix** — a side effect of the
  manual-spawn decision), npm packages `@outreachos/frontend` and root
  `outreachos`.
- P0 pages are honest empty states. No fake data, no placeholder charts.
- No i18n. Hardcoded English, no `t()` wrapper.
- A11y baseline: visible focus rings as a token, correct landmark elements,
  keyboard-reachable nav. No screen-reader audit in V1.
- `THIRD-PARTY-LICENSES.md` is required regardless of the omitted repo LICENSE.
  Inter and JetBrains Mono are OFL, which requires the license accompany the font
  files, and FFmpeg's LGPL texts ship alongside. This is a distribution
  obligation, not repo hygiene — a private repo does not exempt it.
