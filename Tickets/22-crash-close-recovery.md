# 22 — Crash and close recovery

**What to build:** Killing the application mid-batch loses nothing but the job that was running. On relaunch, any job that was in flight resets to waiting, its truncated partial output is deleted, and the queue comes back **paused** with a prompt to resume.

Closing the window while a render is active asks for confirmation first.

**Blocked by:** 19 — Queue controls: pause, resume, cancel, retry, reorder.

**Status:** done

- [x] On startup, jobs left in an interrupted state reset to waiting
- [x] Partial output files from interrupted jobs are deleted, leaving no orphaned fragments in the workspace
- [x] The queue resumes in a paused state with a Resume prompt rather than silently restarting work
- [x] Closing during an active render prompts for confirmation and cancels the close if declined
- [x] Killing the app mid-batch and relaunching is verified end to end, with no orphaned partials and no double-rendered outputs
- [x] Completed jobs from before the crash are untouched
