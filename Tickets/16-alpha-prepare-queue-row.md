# 16 — Alpha-prepare as its own pinned queue row

**What to build:** Building a campaign's alpha clip is a visible queue row of its own, pinned directly above that campaign's video jobs, and it only appears when the cache is cold. On a warm cache the batch goes straight to encoding and the user sees why it was fast.

Video jobs depend on their campaign's alpha job. If alpha preparation fails, every dependent job fails immediately with the same root cause rather than each one rediscovering it.

**Blocked by:** 15 — Worker pool, job enqueue, and the first render from the UI.

**Status:** ready-for-agent

- [ ] A cold cache produces an alpha-prepare row pinned above its campaign's video jobs
- [ ] A warm cache produces no alpha row and the batch starts encoding directly
- [ ] Video jobs record their dependency on the campaign's alpha job
- [ ] Alpha failure fails all dependents immediately, each carrying the same root cause
- [ ] The campaign's cache key is computed and persisted on the campaign, so later tickets can compare against it
- [ ] Changing the overlay config, trim, or focal point invalidates the cache so the next batch rebuilds the alpha clip
- [ ] The alpha cache measurably reduces total time for a multi-video batch compared with a cold run
