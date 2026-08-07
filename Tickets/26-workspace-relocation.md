# 26 — Workspace relocation

**What to build:** The user can change where the workspace lives. Choosing a new location offers **Move existing** — bring the database, caches, and staged outputs along — or **Start fresh**, then restarts the backend against the new location.

Relocation is blocked outright while any queue activity exists, with a stated reason. The workspace pointer stays in OS app-data, since it cannot live inside the workspace it points to.

**Blocked by:** 25 — Settings: quality, encoder, cache, export folder.

**Status:** complete

- [x] Changing the workspace offers Move existing and Start fresh as an explicit choice
- [x] Move existing brings the database, caches, and staged outputs to the new location intact
- [x] Start fresh leaves the old workspace untouched on disk and initialises a new one
- [x] The backend restarts cleanly against the new location and the app reconnects without a manual relaunch
- [x] Relocation is refused while any queue activity exists, with a stated reason
- [x] The workspace pointer in OS app-data is updated only after the move succeeds, so a failed move cannot leave the app pointing at nothing
- [x] A failed or interrupted move surfaces on the diagnostics screen with a route back to a working workspace
