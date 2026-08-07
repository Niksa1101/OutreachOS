# 03 — Talking-head assignment with probe on add

**What to build:** A user can assign a single talking-head video to a campaign by picking a file. The file is probed on add, and its duration, dimensions, fps, codec, and audio presence are stored and displayed. Assigning a second talking head replaces the first rather than adding one.

Source media is referenced by absolute path and never copied into the workspace.

Files that cannot be read, or that are not video, are rejected at add time with a plain-language reason — they never become a row in a broken state.

**Blocked by:** 01 — Campaign CRUD end-to-end.

**Status:** done

- [ ] Picking a talking head stores an absolute path reference; no file is copied
- [ ] The existing probe service from the render engine is reused, not reimplemented
- [ ] Duration, resolution, fps, codec, and audio presence are persisted and shown in the UI
- [ ] Probe failure and non-video files are rejected at add time with a readable reason, leaving the campaign unchanged
- [ ] A campaign can hold at most one talking head; assigning another replaces it and the database constraint is what guarantees this
- [ ] A talking head with no audio track is accepted but recorded as such
