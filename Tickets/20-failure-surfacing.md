# 20 — Failure surfacing and Retry failed

**What to build:** A job failing never stops the batch. The remaining jobs keep going, and at the end the user gets a summary — _"28 completed, 2 failed"_ — with a `Retry failed` action that re-enqueues only the failures.

Each failed job shows a plain-language summary of what went wrong, with the full FFmpeg stderr and the exact command available behind an expandable detail view so it can be pasted into a terminal unchanged. Everything also goes to the rolling log file in the workspace.

**Blocked by:** 16 — Alpha-prepare as its own pinned queue row.

**Status:** ready-for-agent

- [ ] A mid-batch failure is captured and the batch continues to completion
- [ ] Full stderr and the exact command are stored on the failed job, respecting the configured detail size cap
- [ ] The queue row shows a plain-language summary; technical detail is one expansion away, not the default
- [ ] Failures are written to the workspace rolling log
- [ ] A batch ends with a completed/failed summary
- [ ] `Retry failed` re-enqueues only the failed jobs and they can succeed on retry
- [ ] An injected mid-batch failure is verified end to end: batch continues, error is legible, retry works
