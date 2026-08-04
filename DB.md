# OutreachOS — Data Model

> Companion to [`PRD.md`](PRD.md) (scope, phases, behavior) and [`Tech.md`](Tech.md) (stack).

**Engine:** SQLite · **ORM:** SQLAlchemy 2.x · **Migrations:** Alembic, auto-applied at backend startup.

---

## 1. Storage Topology

Two storage locations, and the split is deliberate:

| Location | Contents |
|---|---|
| **OS app-data** (Tauri store) | The **workspace pointer only** — a path string, plus last-used window state |
| **Workspace** (user-chosen) | `outreachos.db`, cache, outputs, logs |

The workspace pointer cannot live inside the workspace it points to. Everything else lives in the workspace so it moves as one unit.

```
<workspace>/
  outreachos.db
  cache/
    alpha/      <cache_key>.mov          # cached alpha clips
    masks/      <cache_key>_mask.png     # Pillow-generated overlay assets
                <cache_key>_frame.png
    previews/   <asset_id>.jpg           # extracted preview frames
  outputs/
    <campaign_id>/  Acme Corp.mp4        # staging only — export moves these out
  logs/
    outreachos.log  (rolling)
```

---

## 2. Conventions

- Primary keys: `TEXT` UUIDv4
- Timestamps: `TEXT` ISO-8601 UTC (`created_at`, `updated_at` on every table)
- Durations and offsets: **integer milliseconds** — never floats, never seconds
- Booleans: `INTEGER` 0/1
- Enums: `TEXT` with a `CHECK` constraint
- Structured config: `TEXT` containing JSON, always carrying `schema_version`
- Foreign keys: `ON DELETE CASCADE` unless stated; `PRAGMA foreign_keys = ON` at connection

---

## 3. Tables

### 3.1 `campaigns`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `name` | TEXT NOT NULL | |
| `overlay_config` | TEXT NOT NULL | JSON, §4.1 |
| `overlay_schema_version` | INTEGER NOT NULL | Mirrors the JSON field for queryability |
| `quality_override` | TEXT NULL | `draft` \| `standard` \| `high`; NULL = use global |
| `alpha_cache_key` | TEXT NULL | Current content hash, §5 |
| `alpha_cache_path` | TEXT NULL | Relative to workspace |
| `default_export_path` | TEXT NULL | Last destination used, seeds the picker |
| `created_at` / `updated_at` | TEXT | |

Overlay config is a JSON column rather than a table: it is strictly 1:1 with a campaign, it is never queried by field, and it must absorb new properties without a migration.

**Duplicate Campaign** copies `overlay_config`, `quality_override`, the talking-head asset row (with its trim and focal point), and settings. Screen recordings are intentionally not copied.

---

### 3.2 `media_assets`

One row per file referenced by a campaign. **Source files are never copied or modified.**

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `campaign_id` | TEXT FK → `campaigns.id` | CASCADE |
| `role` | TEXT | `talking_head` \| `screen_recording` |
| `source_path` | TEXT NOT NULL | Absolute path on disk |
| `source_filename` | TEXT NOT NULL | For display and relocation matching |
| `company_name` | TEXT NULL | `screen_recording` only |
| `output_basename` | TEXT NULL | Resolved **at add time**, incl. `(2)` suffix |
| `sort_order` | INTEGER NOT NULL | |
| **Probe results** | | |
| `probe_status` | TEXT | `pending` \| `ok` \| `failed` |
| `probe_error` | TEXT NULL | |
| `duration_ms` | INTEGER NULL | |
| `width` / `height` | INTEGER NULL | |
| `fps` | REAL NULL | |
| `video_codec` | TEXT NULL | |
| `has_audio` | INTEGER NULL | |
| **Link health** | | |
| `file_missing` | INTEGER NOT NULL DEFAULT 0 | |
| `last_verified_at` | TEXT NULL | |
| **Talking head only** | | |
| `trim_start_ms` | INTEGER NULL | |
| `trim_end_ms` | INTEGER NULL | |
| `focal_x` / `focal_y` | REAL NULL | 0.0–1.0, normalized crop center; default 0.5 |
| **Render tracking** | | |
| `last_rendered_at` | TEXT NULL | Drives skip-completed, §6 |
| `last_rendered_cache_key` | TEXT NULL | Detects config drift since last render |
| `created_at` / `updated_at` | TEXT | |

**Constraints**
- `UNIQUE (campaign_id, source_path)` — the same file cannot be added twice
- At most one `talking_head` per campaign (enforced by a partial unique index)

**Indexes:** `(campaign_id, role, sort_order)`

**Effective duration** for a talking head is `trim_end_ms - trim_start_ms`. This value is `D` — it defines the length of every output in the campaign.

---

### 3.3 `render_jobs`

The global queue. One table serves both job types so the queue is genuinely unified.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `campaign_id` | TEXT FK → `campaigns.id` | CASCADE |
| `asset_id` | TEXT FK → `media_assets.id` NULL | NULL for `alpha_prepare` |
| `job_type` | TEXT | `alpha_prepare` \| `video_render` |
| `status` | TEXT | §4.2 |
| `queue_position` | INTEGER NOT NULL | Global ordering |
| `progress_pct` | REAL NOT NULL DEFAULT 0 | 0–100 |
| `attempts` | INTEGER NOT NULL DEFAULT 0 | |
| `depends_on_job_id` | TEXT NULL | Video jobs point at their `alpha_prepare` |
| `output_path` | TEXT NULL | Relative to workspace |
| `output_filename` | TEXT NULL | Snapshot of `output_basename` at enqueue |
| `error_message` | TEXT NULL | Plain-language summary |
| `error_details` | TEXT NULL | **Full FFmpeg stderr** |
| `ffmpeg_command` | TEXT NULL | Exact command, for diagnostics |
| `started_at` / `finished_at` | TEXT NULL | |
| `created_at` / `updated_at` | TEXT | |

**Indexes:** `(status, queue_position)` · `(campaign_id)` · `(depends_on_job_id)`

**Rules**
- `alpha_prepare` rows are pinned above their campaign's `video_render` rows and cannot be dragged below them
- The actively-encoding job cannot be reordered
- If an `alpha_prepare` job fails, every dependent job is failed immediately with the same root cause
- On startup, any job left `preparing` / `rendering` / `encoding` resets to `waiting` and its partial output is deleted
- Completed jobs are deleted after successful export; failed jobs persist until dismissed

---

### 3.4 `overlay_presets`

Global across campaigns.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `name` | TEXT NOT NULL UNIQUE | |
| `overlay_config` | TEXT NOT NULL | JSON snapshot, §4.1 |
| `overlay_schema_version` | INTEGER NOT NULL | |
| `created_at` / `updated_at` | TEXT | |

Presets are **snapshots applied by copy**. There is intentionally no foreign key from a campaign back to a preset — editing a preset must never mutate a campaign that already used it.

---

### 3.5 `app_settings`

Single row, `id = 1`.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK CHECK (id = 1) | |
| `quality_preset` | TEXT NOT NULL DEFAULT `'standard'` | Global default |
| `encoder_override` | TEXT NULL | NULL = auto-detect |
| `default_export_path` | TEXT NULL | |
| `ffmpeg_version` | TEXT NULL | Cached probe result, shown in Settings |
| `detected_encoders` | TEXT NULL | JSON array from capability probe |
| `created_at` / `updated_at` | TEXT | |

The **workspace path is not stored here** — it lives in OS app-data.

---

## 4. Contracts

### 4.1 Overlay config JSON — `schema_version: 1`

```json
{
  "schema_version": 1,
  "anchor": "bottom_right",
  "size":   { "width": 480, "height": 480 },
  "offset": { "x": 48, "y": 48 },
  "shape": "circle",
  "border_radius": 24,
  "opacity": 1.0,
  "padding": 0,
  "border":     { "enabled": true,  "width": 4,  "color": "#FFFFFF" },
  "shadow":     { "enabled": true,  "blur": 32, "offset_x": 0, "offset_y": 8,
                  "opacity": 0.45, "color": "#000000" },
  "background": { "enabled": false, "color": "#0A0A0A" },
  "animation":  { "type": "fade", "duration_ms": 500 }
}
```

| Field | Values |
|---|---|
| `anchor` | `top_left` · `top_right` · `bottom_left` · `bottom_right` |
| `shape` | `circle` · `rounded_rect` · `rect` |
| `animation.type` | `fade` (only value in V1) |

- All pixel values are against the **fixed 1920×1080 canvas**
- `padding` is the inset between the video and the border; `background.color` fills that inset
- `border_radius` applies only when `shape` is `rounded_rect`
- Size and offsets are **clamped** so the overlay can never leave the frame or invert

**Evolution rules**
- Additive changes bump `schema_version` and are handled by an in-code upgrader, not a migration
- Text layers (deferred) will arrive as a new top-level key, not a restructure — the render pipeline is an ordered list of composite steps precisely so this is additive

### 4.2 Job status enum

| Value | Meaning |
|---|---|
| `waiting` | Queued, not started |
| `preparing` | Validation, FFprobe, cache check |
| `rendering` | Building the campaign alpha clip (`alpha_prepare` only) |
| `encoding` | The per-video FFmpeg pass |
| `completed` | Output written to workspace staging |
| `failed` | Error captured; batch continues |

### 4.3 Validation issues (not persisted)

Computed on demand by the validation service, never stored.

| Code | Severity |
|---|---|
| `no_talking_head` | blocking |
| `no_recordings` | blocking |
| `source_file_missing` | blocking |
| `probe_failed` | blocking |
| `recording_shorter_than_talking_head` | warning |
| `aspect_ratio_not_16_9` | warning |
| `duplicate_company_name` | warning |

---

## 5. Alpha Cache Key

```
sha256(
  talking_head.source_path + mtime + size_bytes +
  trim_start_ms + trim_end_ms +
  focal_x + focal_y +
  canonical_json(overlay_config)
)
```

Stored on `campaigns.alpha_cache_key`. Any change to the talking head, its trim, its focal point, or the overlay configuration invalidates the cache and forces a rebuild on the next Generate.

`media_assets.last_rendered_cache_key` records the key used for a recording's last successful render, so config drift since that render is detectable.

**Retention:** a campaign's alpha clip lives as long as the campaign. Settings displays total cache size and offers Clear Cache. Deleting a campaign deletes its cached clip and generated overlay assets.

---

## 6. Notable Query Paths

**Skip-completed on re-Generate** — `last_rendered_at` lives on `media_assets`, not `render_jobs`, because completed jobs are deleted after export. Without this, pressing Generate after an export would re-render the entire campaign.

```sql
SELECT * FROM media_assets
WHERE campaign_id = ? AND role = 'screen_recording'
  AND file_missing = 0 AND probe_status = 'ok'
  AND last_rendered_at IS NULL;
```

`Re-render All` ignores the final predicate.

**Next job for the worker** — dependency-aware, so a video job never starts before its alpha clip exists.

```sql
SELECT * FROM render_jobs
WHERE status = 'waiting'
  AND (depends_on_job_id IS NULL
       OR depends_on_job_id IN (SELECT id FROM render_jobs WHERE status = 'completed'))
ORDER BY queue_position
LIMIT 1;
```

**Editor lock check** — the overlay and talking-head editors are read-only when this returns any row.

```sql
SELECT 1 FROM render_jobs
WHERE campaign_id = ?
  AND status IN ('waiting','preparing','rendering','encoding')
LIMIT 1;
```

---

## 7. Migration Policy

- Alembic runs automatically at backend startup, before the API accepts requests
- Every schema change ships as a migration — **never** an ad-hoc `ALTER`
- Migrations must be additive and backward-tolerant; a failed migration surfaces on the startup diagnostics screen rather than crashing the sidecar
- The database is a user document. It is never wiped to resolve a schema problem.

**Forward-compatibility note:** future modules (Lead Finder, CRM, Outreach, Analytics) add their own tables namespaced by module prefix. No V1 table is designed to be reshaped to accommodate them — Video Composer's schema is intentionally self-contained.
