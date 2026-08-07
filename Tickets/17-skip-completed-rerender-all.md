# 17 — Skip-completed and Re-render All

**What to build:** Pressing _Generate Videos_ a second time only renders what has not already been rendered. "Already rendered" is tracked on the recording, not on the job — so it survives an export that cleared the queue.

A `Re-render All` action overrides this and re-renders the whole campaign. If the overlay config has drifted since a recording was last rendered, that recording is not treated as complete — which is why this depends on the cache key being computed and persisted.

The UI states what will happen before it happens: how many will render and how many will be skipped.

**Blocked by:** 16 — Alpha-prepare as its own pinned queue row.

**Status:** done

- [x] A successful render stamps the recording's last-rendered state, including the cache key it was rendered under
- [x] Pressing Generate again enqueues only recordings that are not already current
- [x] Skip-completed still works after an export has removed the completed jobs from the queue
- [x] A recording rendered under a since-changed overlay config, trim, or focal point is treated as stale and re-rendered
- [x] `Re-render All` re-enqueues everything regardless of state
- [x] Before enqueueing, the UI states how many will render and how many will be skipped
- [x] A campaign where everything is current reports that clearly instead of enqueueing an empty batch
