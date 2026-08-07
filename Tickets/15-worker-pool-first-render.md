# 15 — Worker pool, job enqueue, and the first render from the UI

**What to build:** The user presses _Generate Videos_ and gets finished MP4s in the workspace, watching progress as it happens.

Pressing Generate enqueues one job per eligible recording. A worker pool — concurrency pinned to 1, but a real pool abstraction so parallelism is later a configuration change — picks jobs off the queue and drives the existing render engine in-process. Jobs advance through the six states, and per-job percentage parsed from FFmpeg's progress output streams to the UI over the existing SSE transport. A global queue view, shared across campaigns, shows the rows moving.

Rendering never starts automatically. Nothing here runs without the user pressing the button.

**Two things this ticket must pin down**, because everything after it inherits them:

- **The outputs staging layout.** Where a rendered file lands inside the workspace, how it is namespaced per campaign, and how the stored relative path maps to it. Ticket 23 moves these files and ticket 24 renames them; both need this settled, not inferred.
- **The quality preset used before Settings exists.** Ticket 25 introduces the global preset and per-campaign override. Until then this ticket renders at a fixed default, chosen explicitly and recorded, so the later Settings work is wiring a value through rather than changing behaviour.

**Blocked by:** 07 — Central validation service; 12 — Full overlay property set.

**Status:** done

- [ ] _Generate Videos_ enqueues one job per eligible recording and returns immediately
- [ ] A worker pool abstraction with concurrency pinned to 1 pulls and executes jobs; the concurrency value is configuration, not a hardcoded assumption in the loop
- [ ] The render engine is invoked in-process, reusing the P1 pipeline rather than shelling out to its CLI; if the pipeline is not yet cleanly callable as a service, extracting it is part of this ticket
- [ ] Jobs move through the six states and the transitions are covered by state-machine tests
- [ ] Per-job progress percentage streams over the existing event stream and the queue view updates live
- [ ] The global Render Queue screen shows jobs from every campaign in queue order
- [ ] The outputs staging directory layout is defined and documented, and stored output paths are workspace-relative
- [ ] The pre-Settings default quality preset is explicit in code, not an accident of a default argument
- [ ] A single recording renders end to end to a spec-correct MP4 in the workspace outputs area
- [ ] Nothing renders without an explicit user action
