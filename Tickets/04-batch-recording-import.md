# 04 — Batch screen-recording drop with parallel probe

**What to build:** A user drags thirty screen recordings onto a campaign at once and gets thirty rows back within a few seconds, each with a company name derived from its filename and full probe metadata.

Company names come from cleaning the filename: strip the extension, normalise separators, strip timestamps and common noise words (`screen recording`, `final`, `v2`, and similar), then title-case the remainder. Two files that clean to the same company name are resolved **at add time** — the second gets a `(2)` suffix — so names are stable and distinct from the moment they exist.

The same source path cannot be added to a campaign twice; the attempt is rejected, not silently deduplicated into a confusing state.

Probing runs in parallel across the dropped batch. Individual files that fail to probe are reported per-file; they do not abort the import of the rest.

**Blocked by:** 03 — Talking-head assignment with probe on add.

**Status:** ready-for-agent

- [ ] Dropping 30 files yields 30 correctly named rows with metadata in a few seconds, with probing genuinely parallel
- [ ] Filename cleanup handles extensions, separators, timestamps, and common noise words, and title-cases the result
- [ ] Duplicate company names are suffixed `(2)`, `(3)` at add time and persisted that way
- [ ] Adding a source path already present in the campaign is rejected with a clear message
- [ ] A single unreadable file in a batch is reported without blocking the other files
- [ ] Filename-cleanup rules are covered by backend tests, and the frontend has a parity test if it does any of the same work
