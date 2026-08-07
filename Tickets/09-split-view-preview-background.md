# 09 — Split-view campaign layout with live preview background

**What to build:** The campaign screen becomes the creative surface: configuration on the left, a live preview pinned on the right that stays visible while scrolling the config.

The preview's background is a real frame from the campaign's first screen recording, extracted at 00:02 — clamped to the recording's midpoint when it is shorter than that. The frame is extracted once and cached in the workspace, and re-extracted when the first recording changes.

A campaign with no recordings shows a neutral placeholder canvas at the correct aspect, not a broken image.

**This is the first time the app has to show the user's own media inside the webview**, and nothing in the project does that yet. Getting a workspace-cached image — and later, in ticket 13, a playable source video that the webview can seek — from disk into the frontend needs a deliberate transport decision: the Tauri asset protocol with an appropriately scoped capability, or an authenticated backend endpoint serving range requests. Pick one, apply it to both cases, and record it as an ADR. Ticket 13 is blocked on this being right, so it does not get to rediscover the problem.

**Blocked by:** 05 — Recordings table with inline editing.

**Status:** done

- [ ] Config-left / preview-right split, with the preview pinned as the config column scrolls
- [ ] The preview background is a frame from the first recording at 00:02, clamped to the midpoint for short recordings
- [ ] The extracted frame is cached in the workspace and reused, and invalidated when the first recording changes
- [ ] The preview canvas is the fixed 1920×1080 output frame, scaled to fit its container, so preview coordinates map to output coordinates
- [ ] With no recordings, a neutral placeholder canvas renders at the correct aspect
- [ ] Frame extraction failure degrades to the placeholder with a readable message rather than breaking the screen
- [ ] The chosen local-media transport is implemented, scoped no wider than the workspace and the campaign's referenced sources, and recorded as an ADR
- [ ] The transport is proven to also serve a seekable source video, so ticket 13's player is unblocked
