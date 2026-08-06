# 05 — Recordings table with inline editing

**What to build:** The campaign screen shows its screen recordings as a table: company name, duration, resolution, and the resolved output filename. The company name is editable inline, and editing it updates the resolved output filename immediately — still honouring duplicate suffixing against the rest of the campaign.

Rows can be removed. Removing a row deletes only the reference, never the source file.

**Blocked by:** 04 — Batch screen-recording drop with parallel probe.

**Status:** ready-for-agent

- [ ] The table shows company name, duration, resolution, and resolved output filename per row
- [ ] Company name edits inline, saves, and updates the output filename live
- [ ] Renaming into a collision with another row in the same campaign resolves to a suffixed name rather than producing two identical filenames
- [ ] An empty or whitespace-only company name is rejected with a stated reason
- [ ] Removing a recording removes only the reference; the source file is untouched
- [ ] Built from shadcn table primitives and design tokens
