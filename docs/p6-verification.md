# P6 verification record — production batch acceptance

Exit criteria for the packaged build (PRD §7 P6, ticket 30). **Developer-mode
success does not count.** This is the V1 definition of done.

Run against the **NSIS installer** produced by `pnpm build:installer`, on a
machine that has completed ticket 29 (clean-machine validation). Record the
date and outcome for every item; a skipped item is a result too.

---

## How to read this

Each item names what to do, what should happen, and — where it is not obvious —
**why it is on the list**. Items marked **(automated)** can be checked with the
helper scripts in `scripts/`. Visual checks and crash-recovery steps are manual
by design — they exercise subsystems together in ways unit tests cannot.

---

## Prerequisites

Before the acceptance run:

- [ ] Ticket 29 clean-machine validation is complete — see findings recorded
      there (or in this document's record table if run on the same machine).
- [ ] Installer built from a clean tree: `pnpm build:installer`
- [ ] Installer path recorded below.
- [ ] A **real media kit** prepared (not synthetic lavfi fixtures):
  - One talking-head recording (webcam or phone footage, with audio)
  - ~30 screen recordings of prospect websites (real Loom-style captures)
  - Files live on a local disk path; source media is referenced by path, never
    copied into the workspace.

| Field            | Value |
| ---------------- | ----- |
| Installer path   |       |
| Build date       |       |
| FFmpeg (bundled) |       |
| Media kit folder |       |
| Export folder    |       |
| Workspace folder |       |

---

## Preflight (automated)

These run on the build machine before the manual acceptance session. They do not
substitute for the full batch run but catch packaging regressions early.

| Check                                         | Command / script                          | Status |
| --------------------------------------------- | ----------------------------------------- | ------ |
| Installer builds                              | `pnpm build:installer`                    | pass — 2026-08-07 |
| Frozen sidecar boots, migrates, serves health | `pytest tests/test_frozen_sidecar.py -q`  | pass — 2/2 |
| Frozen render CLI end-to-end                  | (included in above)                       | pass |
| Bundled FFmpeg resolved, not PATH             | Settings → FFmpeg version in packaged app | pending — manual in installed app |
| Batch output probe script                     | `scripts/verify-batch-output.ps1`         | pass — 3/3 fixture MP4s |

---

## 1. Campaign setup (~30 real recordings)

Create a campaign in the **installed application**, not `pnpm dev`.

1. Pick a fresh workspace folder (or use one created during ticket 29).
2. Create a campaign with a descriptive name (e.g. `P6 acceptance batch`).
3. Assign the real talking-head video. Trim in/out to the segment you intend to
   reuse across the batch; set a focal point off-centre so crop correctness is
   visible.
4. Batch-drop the ~30 screen recordings. Confirm company names are derived from
   filenames and any duplicate-name warnings appear as amber indicators.
5. Configure overlay: corner anchor, shape, opacity, fade, border/shadow. Confirm
   the live CSS preview matches your intent (spot-check one frame against a
   finished output in §3).
6. Confirm validation: *Generate Videos* is enabled; any warnings (short
   recording, non-16:9) show inline and in the campaign summary.

- [ ] ~30 real prospect recordings imported with correct metadata
- [ ] Talking head trimmed and focal point set on real footage
- [ ] Overlay configured; preview looks correct on real background frame
- [ ] Validation warnings (if any) render correctly; no blocking issues

> Real footage catches probe edge cases, VFR sources, and colour-space surprises
> that lavfi fixtures never produce. This is why P1 golden tests defer the full
> batch to P6.

---

## 2. Unattended batch render

1. Start **network monitoring** before pressing *Generate Videos*:

   ```powershell
   .\scripts\verify-no-network.ps1 -LogFile .\p6-network-log.txt
   ```

   Leave it running in a separate terminal for the entire session (render +
   export + relaunch after crash test).

2. Press *Generate Videos*. Confirm the editor locks (overlay, trim, focal
   point, presets read-only; banner visible).
3. Open the global Render Queue. Confirm:
   - Alpha-prepare appears as its own row, pinned above the campaign's video jobs
   - Per-job states progress: Waiting → Preparing → Rendering/Encoding → Completed
   - Batch progress and ETA update over SSE
   - Sidebar shows the active-job badge
4. **Walk away** until the batch finishes. Do not pause, reorder, or interact.

- [ ] Batch completes unattended (~30 completed, 0 unexpected failures)
- [ ] Alpha-prepare row ran once (cache cold), then video jobs proceeded
- [ ] Editor remained locked for the campaign until export cleared completed jobs
- [ ] Batch summary matches expected count

> P4 automated tests prove the state machine; this proves the packaged sidecar,
> bundled FFmpeg, and UI over a real batch duration without dev tooling.

---

## 3. Visual output on real footage

Spot-check at least **three** outputs (first, middle, last) in a video player:

- [ ] Canvas is 1920×1080; talking-head overlay sits at the configured corner
      with correct shape, opacity, and fade
- [ ] Screen recording segment matches talking-head duration (trim length)
- [ ] Audio is talking-head only (no screen-recording audio bleed)
- [ ] Short recordings (if any) freeze the last frame rather than ending early
- [ ] Non-16:9 sources (if any) show letterboxing; overlay position is
      canvas-relative, not content-relative

Then run the automated contract check on the **staged outputs** (before export):

```powershell
.\scripts\verify-batch-output.ps1 `
  -InputDir "<workspace>\outputs\<campaign_id>" `
  -ExpectedDurationSec <talking_head_trim_seconds> `
  -ReportFile .\p6-output-report.json
```

- [ ] Automated probe reports all files pass (1920×1080, 30fps, H.264, AAC)

> Golden frames lock render math; this locks perception on real website captures
> and real webcam lighting.

---

## 4. Alpha cache reuse

With the same campaign (do not change talking head, trim, overlay, or focal
point):

1. Export all outputs (§6) to clear completed jobs from the queue.
2. Press *Generate Videos* again (or *Re-render All* if skip-completed skips them).
3. Watch the queue: alpha-prepare should **not** rebuild — the cached clip is warm.

- [ ] Second run skips alpha rebuild (alpha-prepare row completes instantly or
      video jobs start without a cold alpha build)
- [ ] Backend log shows cache hit, not a full alpha encode

Optional timing evidence: compare `Preparing`/`Rendering` duration on the
alpha-prepare row between first and second run in `outreachos.log`.

---

## 5. Queue behaviour and failure surfacing

If the batch completed with zero failures, inject a controlled failure:

1. Temporarily rename or move **one** source recording while a fresh batch is
   queued (or use a known-bad file in a one-recording test campaign).
2. Confirm the batch **continues** — other jobs complete; the bad row shows
   `Failed` with a plain-language summary and expandable FFmpeg detail.
3. Press *Retry failed* and confirm the retried job succeeds after restoring the
   file.

- [ ] One failed job does not stop the batch
- [ ] Failure detail is legible; full stderr is stored
- [ ] Retry failed recovers the job

> Skip this subsection only if a natural failure occurred during §2 and was
> already verified.

---

## 6. Export — move out, reclaim disk, clean queue

1. Note staged output size in the campaign Outputs section (file count + bytes).
2. Press *Export All*. Pick a destination folder (not inside the workspace).
3. Confirm the dialog states the file count and destination; confirm the move.
4. After export:
   - Files exist at the destination with `{Company}.mp4` names
   - Staged outputs folder is empty (or shows zero exportable)
   - Completed jobs cleared from the queue; failed jobs (if any) remain until
     dismissed
   - Workspace disk usage dropped by roughly the staged size

Run the automated contract check on the **exported** folder:

```powershell
.\scripts\verify-batch-output.ps1 `
  -InputDir "<export_folder>" `
  -ExpectedDurationSec <talking_head_trim_seconds>
```

- [ ] Export moved all completed files; none left in staging
- [ ] Queue is clean of completed jobs
- [ ] Disk reclaimed (staged size → ~0)
- [ ] Automated probe passes on exported files

---

## 7. Crash recovery (mid-batch kill)

Use a **second campaign** with at least 5 recordings (can reuse media files) so
you do not repeat the full 30-video wait:

1. Start *Generate Videos* and wait until at least one video job is actively
   encoding.
2. Force-quit `outreachos.exe` from Task Manager (simulate crash).
3. Relaunch the installed app. Confirm:
   - Resume prompt appears; queue is paused
   - In-flight job reset to `Waiting`; no orphaned partial MP4 in outputs
4. Resume and let the batch finish.

- [ ] Crash recovery prompt on relaunch
- [ ] Partial output cleaned; queue resumes correctly
- [ ] Remaining jobs complete after Resume

> Defers P4's pytest crash tests to the packaged process tree (Tauri + frozen
> sidecar + bundled FFmpeg).

---

## 8. Zero network calls

After stopping the network monitor from §2:

```powershell
# Review the log — must be empty of violations
Get-Content .\p6-network-log.txt
```

The monitor allows **loopback only** (`127.0.0.1`, `::1`). Any other remote
address is a failure.

Additionally, on Windows 11, optional corroboration:

- Resource Monitor → Network tab → filter `outreachos.exe` and
  `outreachos-backend.exe` during §2 — no entries outside loopback.

- [ ] Network monitor reported zero violations for the full session
- [ ] No telemetry, update, or CDN requests observed

> PRD §2 principle 7. Loopback SSE/API traffic between Tauri and the sidecar is
> expected and allowed.

---

## 9. Close-during-render guard

With a batch actively encoding:

- [ ] Closing the window prompts for confirmation
- [ ] Cancel keeps the app open; confirm closes cleanly with no orphan
      `outreachos-backend.exe`

---

## Record

| Date | Installer | Videos | Completed | Failed | Network violations | Visual spot-check | Notes |
| ---- | --------- | ------ | --------- | ------ | ------------------ | ----------------- | ----- |
|      |           |        |           |        |                    |                   |       |

---

## Helper scripts

| Script | Purpose |
| ------ | ------- |
| `scripts/verify-no-network.ps1` | Poll TCP connections for OutreachOS processes; flag non-loopback |
| `scripts/verify-batch-output.ps1` | FFprobe each MP4 against the §6.1 render contract |
| `scripts/build-installer.ps1` | Full NSIS installer build (sidecar + FFmpeg + Tauri) |
