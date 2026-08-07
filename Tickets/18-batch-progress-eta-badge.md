# 18 — Batch progress, ETA, and sidebar active-job badge

**What to build:** The user can tell how far along the whole batch is without doing arithmetic, and can tell from any screen that a render is running.

Alongside per-job percentage, the queue shows batch-level progress and an estimated time remaining derived from observed throughput. The sidebar carries a live badge showing the active job count so the queue is legible from the Campaigns screen or Settings.

**Blocked by:** 15 — Worker pool, job enqueue, and the first render from the UI.

**Status:** done

- [x] Batch progress reflects completed, active, and remaining jobs across the whole queue
- [x] An ETA is shown and derived from measured throughput, not from a fixed per-job guess
- [x] The ETA degrades gracefully early in a batch when there is not yet enough data, rather than showing a wild number
- [x] The sidebar badge shows active queue state live and disappears when the queue is idle
- [x] Progress and badge updates arrive over the existing event stream with no polling
