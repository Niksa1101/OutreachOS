# 21 — Editor locking

**What to build:** While a campaign has queued or active render jobs, its creative settings become read-only. Overlay settings, talking-head trim, and the focal point cannot be changed, and presets cannot be applied. A banner explains: _"Editing is locked while this campaign has queued or active render jobs."_

`Cancel Queue` unlocks editing.

This is the mechanism that guarantees a batch is visually consistent and deterministic, so the lock is enforced on the backend as well — a request that would mutate a locked campaign is rejected, not merely hidden in the UI.

The specification places this in the overlay-editor phase, but it cannot be built or verified without a real queue to lock against and a real cancel to unlock with, so it is sequenced after those exist.

**Blocked by:** 12 — Full overlay property set; 13 — Talking Head Editor; 19 — Queue controls: pause, resume, cancel, retry, reorder.

**Status:** ready-for-agent

- [ ] A campaign with any job in a queued or active state reports itself as locked
- [ ] Overlay settings, trim, and focal point render read-only, and preset application is disabled
- [ ] The banner explains the reason in the specified wording
- [ ] The backend rejects mutations to a locked campaign's overlay config, trim, and focal point — the lock is not UI-only
- [ ] `Cancel Queue` clears the jobs and unlocks editing
- [ ] A campaign is unaffected by another campaign's jobs — the lock is per-campaign, not global
- [ ] The lock state updates live over the existing event stream rather than needing a refresh
