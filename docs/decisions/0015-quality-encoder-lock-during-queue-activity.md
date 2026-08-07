# ADR-0015: Lock quality, encoder, and cache during queue activity

**Status:** Accepted

---

## Context

PRD §6.5 lists overlay, trim, and focal point as read-only while a campaign has
queued or active render jobs. Ticket 21 implements that per-campaign editor lock.
Tickets 23–25 add export, rename, and global Settings (quality preset, encoder
override, Clear Cache).

Quality and encoder are not per-campaign constants for a batch: `_quality_for`
and `_encoder_for` read the database when each job starts. Changing the global
preset or encoder mid-batch, or clearing the workspace cache while FFmpeg holds
an alpha clip, breaks **Principle 6 (Determinism)** — the back half of a batch
can encode at different settings than the front.

Clear Cache deletes cached alpha clips that a running `alpha_prepare` or
dependent `video_render` may still have open.

## Decision

Extend the existing lock machinery rather than inventing a second one:

- **Per-campaign:** `update_campaign_quality` calls `_require_unlocked`, the
  same 409 `CONFLICT` path as overlay and trim (ticket 21).
- **Global:** `queue_has_activity` scans `render_jobs` for
  `JobStatus.active()` (waiting, preparing, rendering, encoding). While true:
  - `update_app_settings` rejects changes to `quality_preset` and
    `encoder_override` with 409.
  - `clear_workspace_cache` rejects with 409.
  - `default_export_path` stays editable — it cannot affect a running render.
- **API:** `SettingsResponse.queue_busy` exposes the flag so the UI can disable
  controls and show why.
- **Relocation (ticket 26):** Rust probes `GET /api/v1/render-queue` before
  stopping the sidecar; non-zero `batch.active_job_count` refuses relocation.

## Consequences

- A batch started under Draft / auto-detect finishes under the same effective
  settings unless the user cancels the queue first.
- Settings and campaign quality controls mirror the editor lock banner pattern.
- Spec change from §6.5's read-only list is recorded here per PRD §10 — the
  decision is not changed by writing different code.
