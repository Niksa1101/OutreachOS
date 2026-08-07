# 25 — Settings: quality, encoder, cache, export folder

**What to build:** A working Settings screen. The user sets a global quality preset (Draft / Standard / High) that every campaign inherits, and any campaign can override it with a tri-state control — inherit, or an explicit preset.

Also here: an encoder override on top of the automatic hardware detection, the current cache size with a Clear Cache action, the bundled FFmpeg version information, and the default export folder that seeds the export picker.

**Blocked by:** 15 — Worker pool, job enqueue, and the first render from the UI.

**Status:** complete

- [x] A global quality preset persists and is what campaigns inherit by default
- [x] The per-campaign override is genuinely tri-state: inherit, or an explicit preset, distinguishable in the UI and in storage
- [x] The selected preset visibly changes the encoding settings actually used for a render
- [x] Encoder override sits on top of automatic detection, with the detected default shown
- [x] Cache size is displayed accurately and Clear Cache frees it, after which the next batch rebuilds the alpha clip
- [x] Bundled FFmpeg version information is shown, read from the bundled binary rather than from PATH
- [x] The default export folder persists and seeds the export picker
