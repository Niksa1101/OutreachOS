# 08 — Duplicate Campaign

**What to build:** From the Campaigns table, a user can duplicate a campaign. The copy carries over the talking head reference, its trim, its focal point, the overlay config, and campaign settings. Its recordings list is intentionally empty — the point of duplicating is to reuse a look for a new batch.

The copy gets its own name (the original's, disambiguated) and does **not** inherit the original's alpha cache pointer, render history, or jobs.

**Blocked by:** 05 — Recordings table with inline editing.

**Status:** ready-for-agent

- [ ] Duplicating copies talking head reference, trim, focal point, overlay config, overlay schema version, and campaign settings
- [ ] The duplicate has no screen recordings
- [ ] The duplicate has no alpha cache pointer, no render history, and no jobs
- [ ] The duplicate's name is disambiguated from the original
- [ ] Editing the duplicate never affects the original, and vice versa — covered by a test
- [ ] Duplicating a campaign with no talking head works and produces an empty-but-valid campaign
