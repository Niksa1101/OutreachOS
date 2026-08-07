# 19 — Queue controls: pause, resume, cancel, retry, reorder

**What to build:** The queue is something the user can steer. They can pause the whole queue, resume it, cancel individual jobs or the whole queue, retry a single job, and drag rows into a different order.

Pausing lets the in-flight job finish and stops the next one starting. Cancelling a running job terminates its process and cleans up its partial output. The actively-encoding job cannot be reordered and is pinned in place; everything below it moves freely.

`Cancel Queue` at campaign scope is what later releases the editor lock, so it needs to genuinely clear that campaign's queued and active jobs, not merely hide them.

**Blocked by:** 15 — Worker pool, job enqueue, and the first render from the UI.

**Status:** done

- [x] Pause stops the next job from starting; the in-flight job finishes rather than being killed
- [x] Resume continues from where the queue stopped
- [x] Cancelling a running job terminates the render process and deletes its partial output
- [x] `Cancel Queue` clears a campaign's waiting and active jobs and leaves no job in a state that would still read as busy
- [x] Retry re-runs a single job and resets its state cleanly
- [x] Rows reorder by drag; the actively-encoding job is pinned and cannot be moved or displaced
- [x] Reordering persists and the worker respects the new order
