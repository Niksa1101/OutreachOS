# 24 — Company rename renames the output on disk

**What to build:** Renaming a company after its video has rendered renames the staged output file on disk. No re-render happens — the company name is never burned into the video, only into the filename.

The renamed file still obeys duplicate resolution, so a rename into a collision produces a suffixed name rather than an overwrite.

**Blocked by:** 23 — Outputs staging view and Export All; 05 — Recordings table with inline editing.

**Status:** ready-for-agent

- [ ] Renaming a company with a staged un-exported output renames that file on disk
- [ ] No re-render is triggered and the recording's rendered state stays valid
- [ ] A rename that would collide with another staged output resolves to a suffixed filename, never an overwrite
- [ ] Renaming a company with no staged output simply updates the resolved filename for future renders
- [ ] A failed rename on disk is reported and leaves the database and filesystem consistent with each other
