# ADR-0014: Outputs staging layout — `outputs/<campaign_id>/<basename>.mp4`

**Status:** Accepted

---

## Context

Ticket 15 requires the outputs staging directory layout to be *defined and
documented*, with stored paths workspace-relative. Tickets 23 (export) and 24
(rename) both say they need this *settled, not inferred* — until now the shape
existed only as `workspace.outputs / campaign.id` at the two call sites that
write renders.

## Decision

Rendered videos land at:

```
<workspace>/outputs/<campaign_id>/<output_basename>.mp4
```

- **Per-campaign namespace.** Each campaign owns a subdirectory under
  `outputs/`. Ticket 24's rename and ticket 23's export operate inside one
  campaign's staging tree without colliding with another campaign's identical
  company names.
- **Workspace-relative `output_path`.** `render_jobs.output_path` stores the
  path relative to the workspace root (POSIX separators), e.g.
  `outputs/<campaign_id>/Acme.mp4`. Absolute paths are resolved at use time via
  `workspace.root / job.output_path`.
- **`.part.mp4` sibling during encode.** While FFmpeg runs, the file is written
  to `outputs/<campaign_id>/<output_basename>.mp4.<pid>-<nonce>.part.mp4` and
  atomically renamed to the final name on success (`rendering.render.render_one`).
  Cancel / crash recovery deletes these partials only — never a pre-existing
  final at the target basename inferred from `output_filename` alone.

## Consequences

- Export (ticket 23) and rename (ticket 24) can assume this layout without
  reverse-engineering call sites.
- Skip-completed (ticket 17) remains correct across cancel/retry: a prior good
  MP4 is not deleted when a waiting/failed job is cleared.
