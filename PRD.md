# OutreachOS — Product Requirements & Implementation Plan

> **Status:** Specification locked. **P0 complete** (2026-08-04). **P1 complete** (2026-08-05).
> **Version:** 1.0 (Video Composer)
> **Target platform:** Windows 11 (code written cross-platform-clean)

**Companion documents**
- [`Tech.md`](Tech.md) — complete technology stack, versions, and rationale
- [`DB.md`](DB.md) — database schema, JSON config contracts, and state enums

---

## 1. Product Definition

OutreachOS is a modular desktop workspace for outbound sales. It is **not** a video merger — it is a platform whose first module happens to solve video generation.

**Version 1 ships exactly one module: Video Composer.**

Its single responsibility: *generate personalized outreach videos in batches by overlaying one reusable talking-head video onto many website screen recordings.*

Generated videos are exported to a folder and uploaded to Loom manually. The application makes **zero network calls of any kind**.

### 1.1 In scope

Campaign management · talking-head upload and trimming · batch screen-recording import · overlay customization with live preview · batch rendering · global render queue · export.

### 1.2 Explicitly out of scope

Email sending · CRM · lead management · Loom integration · any third-party API · analytics · AI features · uploads of any kind.

### 1.3 Deferred, but architecturally accommodated

Text overlays on video · per-video overlay overrides · parallel rendering (worker pool exists, pinned to 1) · light theme (tokens are light-ready) · macOS/Linux builds · auto-update · command palette · the Dashboard, Lead Finder, CRM, Outreach, Analytics, and AI Assistant modules.

---

## 2. Non-Negotiable Principles

1. **Build for Version 10.** Every structural decision assumes six more modules arrive later.
2. **Modules are isolated.** Cross-module imports are lint-forbidden. Shared behavior lives in `core/`.
3. **The frontend never executes FFmpeg.** Python owns all rendering.
4. **Rendering never starts automatically.** The user presses *Generate Videos*.
5. **The app is a production tool, not storage.** Outputs are staged, exported, and gone.
6. **Determinism.** Identical inputs must always produce identical outputs.
7. **No network.** Not for telemetry, not for updates, not for anything.

---

## 3. MANDATORY: UI Component Workflow

> **Every agent or developer creating any UI component must use the project's shadcn/ui preset. This is not optional.**

Initialize the component system with:

```bash
npx shadcn@latest init --preset b51GFh7y6 --template next --pointer
```

Add components with:

```bash
npx shadcn@latest add button dialog table
```

### Rules

1. **Never hand-write a component that shadcn provides.** Buttons, dialogs, dropdowns, tables, tabs, sliders, tooltips, toasts, sheets, sidebars, forms, popovers, selects, switches, and progress bars all come from shadcn.
2. **Always run `npx shadcn@latest add <component>`** before building anything custom. Check the registry first.
3. shadcn supplies **primitives only.** The visual identity is ours — see §4.
4. Custom components belong in `frontend/src/core/ui/` and must be **composed from** shadcn primitives, never replace them.
5. Component styling uses **design tokens** (§4), never hardcoded colors or spacing values.

### P0 resolution (2026-08-04)

The command specifies `--template next`, but this project is **Vite + Tauri, not Next.js**. Resolved in P0: **`--template next` dropped**, preset ID kept, palette overridden per Q123. See [`docs/decisions/0001-shadcn-preset-vite.md`](docs/decisions/0001-shadcn-preset-vite.md).

---

## 4. Design Direction

**Reference quality bar:** Linear, Raycast, Notion, Arc Browser, Vercel Dashboard.
**Explicit anti-goal:** a stock shadcn app.

- **Dark-first**, dark-only in V1. Tokens are structured so light mode is an addition, not a refactor.
- **Neutral palette** with a single restrained accent color.
- **Custom scales** for spacing, typography, and border radius — defined as tokens before any component is built.
- **Subtle shadows.** Depth through elevation, not decoration.
- **Restrained motion.** Micro-interactions only: modal transitions, queue row enter/exit, status changes. No page transitions, no staggered lists, no animated counters.
- **Zero clutter.** Everything obvious without documentation.

Tokens are defined once in P0 and are the only source of visual values.

---

## 5. Core Workflow

```
Create Campaign
  ↓
Add Talking Head  →  trim in/out  →  set focal point
  ↓
Add Screen Recordings (batch drop; company names derived from filenames)
  ↓
Configure Overlay (live preview, direct manipulation, presets)
  ↓
Generate Videos
  ↓
Global Render Queue  (alpha prepare → per-video encode)
  ↓
Export All  →  files move out  →  queue clears
```

---

## 6. Locked Behavioral Specification

### 6.1 Render contract

| Property | Value |
|---|---|
| Output duration | Talking head duration (`D`), after trim |
| Screen recording segment | First `D` seconds, via input-side `-ss`/`-t` seek |
| Recording shorter than `D` | Freeze last frame (`tpad`) to fill |
| Canvas | 1920×1080 @ 30fps, fixed |
| Aspect mismatch | Scale to fit, centered, black bars, **warning shown** |
| Audio | Talking head only; AAC 192kbps stereo 48kHz |
| Container | MP4, H.264, `+faststart` |
| Filename | `{Company}.mp4`, duplicates suffixed `(2)` at **add time** |

### 6.2 Overlay

- **Geometry:** corner anchor (TL/TR/BL/BR) + pixel width/height + x/y offsets against the fixed canvas. Clamped so the overlay can never leave the frame or invert.
- **Anchoring:** always canvas-relative, never content-relative. Non-16:9 sources produce a warning.
- **Shape:** circle · rounded rectangle · rectangle.
- **Properties:** size, scale, x/y offset, opacity, border radius, border, shadow, background, padding.
  - *Padding* = inset between the video and the border.
  - *Background* = the fill visible in that inset.
- **Animation:** fade in / fade out only. One duration value applied to both ends. Default 500ms.
- **Talking head fit:** center-crop to fill the box (never distort), with a draggable focal point.
- **Presets:** named snapshots of the full overlay config. Applying **copies** values. Editing a preset never mutates campaigns that used it.

### 6.3 Rendering pipeline

**Alpha preparation** — once per campaign, cached:

```
FFprobe talking head
  → Pillow renders mask PNG + border/shadow PNG at overlay bounding-box size
  → FFmpeg: scale/crop to focal point → alphamerge → composite frame
             → alpha fade in/out → ProRes 4444 .mov (carries talking-head audio)
  → cached under sha256(source path+mtime+size, overlay config, trim, focal point)
```

Encoding at **bounding-box size, not full canvas**, keeps ProRes practical. Audio living in the cached clip means each job maps `1:a` with no second decode of the source.

**Per-video render** — one FFmpeg process, one pass:

```
trim (input seek) → scale/pad to 1920×1080 → fps=30 → tpad (freeze)
  → overlay(x, y) → h264 encode + aac → -progress pipe:1
```

The filtergraph is assembled by an **ordered list of composite step objects** (§7, P1), each contributing nodes to a single graph. Text layers slot in later without restructuring.

### 6.4 Queue

Global across campaigns. Reorderable. Worker pool with concurrency **pinned to 1**.

| State | Meaning |
|---|---|
| `Waiting` | Queued, not started |
| `Preparing` | Validation, FFprobe, cache check |
| `Rendering` | Building/updating the campaign alpha clip |
| `Encoding` | The per-video FFmpeg pass |
| `Completed` | Output written to workspace |
| `Failed` | Error captured, batch continues |

- The **alpha-prepare job is its own queue row**, pinned above its campaign's video jobs, and only runs when the cache is cold.
- If alpha preparation fails, **all dependent jobs fail immediately** with the same root cause.
- A job failure never stops the batch. Summary at the end: *"28 completed, 2 failed"* with `Retry failed`.
- Controls: pause · resume · cancel · reorder · retry. The actively-encoding job cannot be reordered.
- Progress: per-job percentage parsed from FFmpeg `-progress`, plus batch progress and ETA, streamed over SSE.
- **Crash/close recovery:** in-flight job resets to `Waiting`, partial output is deleted, queue resumes paused with a Resume prompt.
- Closing the app during an active render prompts for confirmation.

### 6.5 Editor locking

While a campaign has **queued or active** jobs:

- Overlay settings, talking-head trim, and focal point become **read-only**
- Presets cannot be applied
- A banner explains: *"Editing is locked while this campaign has queued or active render jobs."*
- `Cancel Queue` unlocks editing

This is the mechanism that guarantees a batch is visually consistent and deterministic.

### 6.6 Validation service

A central service returns typed issues with severity:

| Issue | Severity |
|---|---|
| No talking head | Blocking |
| No screen recordings | Blocking |
| Source file missing | Blocking (for that row) |
| Unreadable / not a video | Blocking (rejected at add) |
| Recording shorter than `D` | Warning |
| Recording is not 16:9 | Warning |
| Duplicate company name | Warning (auto-suffixed) |

Blocking issues disable *Generate Videos* with a stated reason. Warnings render as inline amber row indicators plus a campaign-level summary.

### 6.7 Files, workspace, export

- **Source media is referenced by path, never copied.** Missing files show *"File missing"* with a **Relocate** button.
- **Workspace** is user-chosen on first run. It holds the SQLite database, mask/alpha caches, rendered outputs, and logs.
- The **workspace pointer** lives in OS app-data (Tauri store) — it cannot live inside the workspace it points to.
- Changing the workspace offers **Move existing** or **Start fresh**, then restarts the backend. Blocked while any queue activity exists.
- **Outputs** are a staging area inside the workspace. The campaign Outputs section shows only un-exported renders.
- **Export All** opens a folder picker (seeded from the default export folder), **moves** files out, never overwrites, reports conflicts. Only completed jobs export; it works mid-batch.
- After successful export, completed jobs clear from the queue. Failed jobs persist until dismissed.
- *"Already rendered"* is tracked as `last_rendered_at` **on the recording row**, not the job — so pressing Generate after an export skips completed work.
- Renaming a company after render **renames the file on disk**; no re-render (the name is not burned into the video).
- Deleting a campaign shows a confirmation naming exactly what is removed: campaign data, cached alpha clip, un-exported outputs. **Source recordings are never touched.**

### 6.8 Failure surfaces

- Full FFmpeg stderr is stored on every failed job. UI shows a plain-language summary with expandable technical detail. Everything also goes to a rolling log file in the workspace.
- Startup failures (sidecar won't launch, port bind fails, bundled FFmpeg missing, workspace folder gone) show a **dedicated diagnostics screen** naming the specific failure, with `Retry` and `Choose Workspace` where applicable.

---

## 7. Implementation Phases

> Phases are sequential. **P1 must be provably correct before any UI depends on it** — the render engine is the only part of this system that can be fundamentally wrong.

---

### P0 — Project Skeleton

**Status:** ✅ **Complete** — merged to `main`, 2026-08-04.

**Goal:** A running shell that proves every layer can talk to every other layer. No features.

**Deliverables** *(all landed)*
- Git repository initialized on `main`, Conventional Commits with module scopes (`feat(video-composer):`, `feat(core):`), full `.gitignore`
- Tauri 2 application shell, single-instance enforced
- React 19 + TypeScript + Vite frontend
- shadcn initialized per §3, **design tokens defined first** (color, spacing, typography, radius, shadow, motion)
- FastAPI backend running as a Tauri-spawned sidecar
- Loopback binding, random free port, shared-secret token passed from Tauri to frontend
- SSE stream established, proven with a heartbeat event
- SQLite + SQLAlchemy + Alembic wired; migrations auto-run at startup
- First-run workspace picker; workspace pointer persisted in OS app-data
- Startup diagnostics screen
- Rolling log file infrastructure (backend + frontend error capture)
- Module registry + shadcn Sidebar shell: `Video Composer → Campaigns, Render Queue`, `Settings` pinned bottom
- ESLint rule forbidding cross-module imports
- GitHub Actions: lint, typecheck, test

**Exit criteria** *(verified)*
- App launches, picks a workspace, creates the database, and displays a heartbeat received over SSE from the sidecar
- Killing the sidecar surfaces the diagnostics screen
- CI green

**Verification record**
- **Automated:** 190 tests green locally (64 `cargo`, 100 `pytest`, 26 `vitest`); GitHub Actions CI on push
- **Manual (2026-08-04):** workspace picker · SSE **Connected** · kill sidecar → `sidecar_exited` + Retry · kill Tauri → no orphan Python · second launch focuses first instance
- **Checklist:** [`docs/p0-verification.md`](docs/p0-verification.md) — high-value items done; remaining items (monitor unplug, 10‑min idle, non-ASCII path, packaged build) deferred to ongoing regression or P6
- **Implementation:** six checkpoint branches (`p0/01-tooling` … `p0/06-ui`), squash-merged to `main`
- **Decisions:** [`docs/decisions/`](docs/decisions/) — ADRs 0001–0006; full P0 interview in `p0-questionnaire.md`

---

### P1 — Headless Render Engine

**Status:** ✅ **Complete** (2026-08-05) — verification record in
[`docs/p1-verification.md`](docs/p1-verification.md).

**Goal:** Correct video output, driven entirely from a CLI. **Zero UI.**

**Deliverables**
- FFmpeg/FFprobe wrapper with bundled-binary path resolution (never PATH)
- Probe service returning duration, dimensions, fps, codec, audio presence
- Encoder capability detection: NVENC / QSV / AMF → libx264 fallback
- Pillow overlay asset builder: mask PNG + border/shadow/background/padding frame PNG
- **Composite step objects** assembling one filtergraph
- Alpha clip builder with content-hash cache and invalidation
- Per-video render pipeline: trim → scale/pad → fps → tpad → overlay → encode
- `-progress` parser emitting structured progress events
- CLI entry point: render a campaign from a JSON config file
- **Golden-frame test suite** — synthetic FFmpeg fixtures (`testsrc`, `sine`) plus one committed real sample; deterministic libx264 settings; lossless PNG frame comparison with tolerance
- Filtergraph builder unit tests (assert the graph, don't render)

**Exit criteria**
- CLI renders a batch of fixtures to spec-correct MP4s
- Golden frames pass
- All four edge cases verified: recording shorter than `D`, non-16:9 source, cache hit, cache invalidation
- Alpha cache measurably reduces batch time

**Risks resolved here:** ProRes 4444 viability · CSS↔Pillow parity baseline · whether NVENC actually wins · `tpad`/`overlay`/fade interaction. See §9.

---

### P2 — Campaign & Asset Management

**Goal:** Data in, validated, visible. Still no overlay editing, still no rendering from the UI.

**Deliverables**
- Campaign CRUD; Campaigns table (name, recording count, last rendered, status)
- Delete confirmation naming exactly what is removed
- **Duplicate Campaign** — copies talking head, trim, focal point, overlay config, settings; recordings intentionally empty
- Talking-head assignment (single per campaign)
- Batch drag-and-drop of screen recordings; parallel FFprobe on import
- Filename → company name cleanup: strip extension, separators, timestamps, and common noise (`screen recording`, `final`, `v2`); title-case
- Inline-editable recordings table with duration, resolution, and resolved output filename
- Duplicate name resolution at add time; duplicate source path rejected
- **Central validation service** with typed blocking/warning issues
- File-missing detection with Relocate
- Generated typed API client (`openapi-typescript` + thin fetch wrapper), regenerated manually via script

**Exit criteria**
- Drop 30 files, get 30 correctly-named rows with metadata in under a few seconds
- Every §6.6 validation case renders correctly in the UI
- *Generate Videos* correctly disabled with a stated reason when requirements are unmet

---

### P3 — Overlay Editor

**Goal:** The core creative surface.

**Deliverables**
- Split-view campaign layout: config left, live preview pinned right
- Preview background: frame extracted from the first recording at 00:02 (clamped to midpoint if shorter)
- Live CSS overlay preview, 1:1 calibrated against Pillow output
- Direct manipulation: drag to position, handle to resize, magnetic snap to corners and safe margin
- Synced numeric fields for every property; clamping enforced
- **Talking Head Editor**: player, trim timeline with in/out handles, draggable focal point inside a live shape preview
- Full overlay property set (§6.2)
- Preset library inline in the Overlay section: Apply Preset, Save as Preset, Manage dialog
- Editor locking (§6.5) — implemented here, exercised in P4

**Exit criteria**
- Preview and rendered output agree within golden-frame tolerance for all three shapes
- Overlay cannot be placed off-frame or inverted by any input path

---

### P4 — Render Queue

**Goal:** Batch execution the user can trust and walk away from.

**Deliverables**
- Worker pool abstraction, concurrency pinned to 1
- Job enqueue from *Generate Videos*; skip-completed via `last_rendered_at`, plus `Re-render All`
- Alpha-prepare job as its own pinned queue row
- Six-state model with per-job percentage, batch progress, and ETA over SSE
- Global queue view with live active-job badge in the sidebar
- Pause · resume · cancel · retry · reorder (`dnd-kit`), with active job pinned
- Failure handling: continue batch, capture full stderr, friendly summary + expandable detail, `Retry failed`
- Alpha-failure cascade to dependents
- Crash/close recovery with Resume prompt and partial-output cleanup
- Close-during-render confirmation
- Editor locking enforced end to end

**Exit criteria**
- 30-video batch completes unattended
- Injected mid-batch failure: batch continues, error is legible, retry works
- Kill the app mid-batch: relaunch recovers correctly with no orphaned partials

---

### P5 — Export

**Goal:** Get files out and reclaim the disk.

**Deliverables**
- Campaign Outputs staging view (un-exported renders only)
- `Export All`: folder picker seeded from the default export folder, move-not-copy, confirmation stating the file count and destination
- Overwrite refusal with conflict reporting
- Completed jobs clear from the queue after successful export; failed jobs persist until dismissed
- Company rename → output file rename on disk
- Settings: workspace location (Move / Start fresh + backend restart), global quality presets (Draft / Standard / High), per-campaign tri-state override, encoder override, cache size display + Clear Cache, FFmpeg version info, default export folder

**Exit criteria**
- Export moves files, reclaims space, and leaves the queue clean
- Workspace relocation correctly blocked during queue activity

---

### P6 — Packaging

**Goal:** An installable application, validated on a machine that has never seen this project.

**Deliverables**
- PyInstaller build of the FastAPI backend as a single sidecar executable
- Static FFmpeg/FFprobe binaries bundled with correct licensing attribution
- Tauri Windows installer; identity `OutreachOS` / `com.outreachos.app`; placeholder icon
- Sidecar lifecycle hardening: startup, health check, graceful shutdown, orphan cleanup
- Workspace initialization on a clean machine
- Full diagnostics coverage for packaged-only failure modes

**Exit criteria — this is the V1 definition of done**
- ✅ Windows installer builds successfully
- ✅ Installs and runs on a clean Windows machine with no Python, no FFmpeg, no dev tooling
- ✅ Full workflow validated with a **real production batch of ~30 prospect videos**
- ✅ Generated videos match expected visual output
- ✅ Queue, export, cache, recovery, and validation all verified in the packaged build

**Developer-mode success does not count as done.**

---

## 8. Testing Strategy

| Layer | Tool | Scope |
|---|---|---|
| Render correctness | pytest + golden frames | Synthetic fixtures + one real sample; deterministic libx264; lossless PNG comparison |
| Filtergraph | pytest | Assert graph structure without rendering |
| Backend services | pytest | Validation, cache keys, filename cleanup, queue state machine |
| Frontend logic | Vitest | Overlay geometry math, filename cleanup parity, clamping |
| CI | GitHub Actions | Lint, typecheck, test on push. Release builds manual. |

No component tests, no E2E in V1 — tests go where bugs are invisible, not everywhere.

---

## 9. Known Risks

These are **implementation risks with named fallbacks**, not open decisions. All resolve by measurement in P1 or P6.

| # | Risk | Resolves in | Fallback |
|---|---|---|---|
| 1 | ProRes 4444 alpha clip size / decode speed | P1 | QTRLE or VP9-alpha, drop-in |
| 2 | CSS `box-shadow` ≠ Pillow Gaussian blur | P1 → P3 | Calibration pass; golden frames prevent drift |
| 3 | NVENC may not beat CPU for 25s clips | P1 | Auto-detect stays; benchmark decides the default |
| 4 | `tpad` + `overlay` + fade ordering in one graph | P1 | Reorder graph nodes; worst case, pad before overlay |
| 5 | PyInstaller freezing FastAPI/uvicorn/SQLAlchemy on Windows | P6 | Hidden-imports tuning; embedded runtime as fallback |
| 6 | shadcn preset targets `next`, project is Vite | ~~P0~~ ✅ | Resolved — ADR-0001: preset kept, `--template next` dropped, palette overridden |

---

## 10. Decision Record

Decisions resolved before each phase: **Q1–Q126 before P0**, **Q127–Q201 before P1** — full records in [`docs/decisions/`](docs/decisions/). Each phase must record any deviation as an ADR with its rationale.

**A decision is not changed by writing different code. It is changed by writing a new ADR.**
