# 23 — Outputs staging view and Export All

**What to build:** Finished videos leave the app. The campaign's Outputs section lists only un-exported renders. `Export All` opens a folder picker seeded from the default export folder, confirms the file count and destination, then **moves** the files out — reclaiming the disk rather than duplicating it.

Export never overwrites. Conflicting filenames at the destination are refused and reported by name, and the rest of the batch still exports.

Export works mid-batch: only completed jobs are eligible. After a successful export, completed jobs clear from the queue. Failed jobs persist until dismissed.

**Blocked by:** 15 — Worker pool, job enqueue, and the first render from the UI.

**Status:** complete

- [x] The Outputs section shows only renders that have not been exported
- [x] `Export All` picks a destination seeded from the default export folder and confirms file count and destination before acting
- [x] Files are moved, not copied, and the workspace staging area shrinks accordingly
- [x] An existing file at the destination is never overwritten; conflicts are reported by name and the remaining files still export
- [x] Exporting mid-batch exports only completed jobs and does not disturb running ones
- [x] Completed jobs clear from the queue after a successful export; failed jobs remain until dismissed
- [x] A partially failed export leaves the app in a consistent state — moved files are gone from staging, unmoved ones are not
