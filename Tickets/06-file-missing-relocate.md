# 06 — File-missing detection and Relocate

**What to build:** When a source file has moved or been deleted, the campaign shows that row as "File missing" with a **Relocate** button. Relocating opens a file picker, re-points the reference at the new path, re-probes it, and clears the missing state.

Detection runs when a campaign is opened and refreshes the row's link-health state, so the user finds out before pressing Generate rather than during a batch. This link-health state is what the validation service later reads to raise its row-level blocking issue, so it lands first.

**Blocked by:** 05 — Recordings table with inline editing.

**Status:** ready-for-agent

- [ ] Opening a campaign detects missing sources and marks exactly those rows
- [ ] A missing row shows "File missing" and a Relocate action
- [ ] Relocating re-points the path, re-probes, refreshes the metadata, and clears the missing flag
- [ ] Relocating to a file that is unreadable or not a video is rejected and the row stays missing
- [ ] Relocating to a path already used by another row in the campaign is rejected
- [ ] A missing talking head and a missing recording both surface correctly
- [ ] Link-health state is persisted and queryable, not merely computed for display
