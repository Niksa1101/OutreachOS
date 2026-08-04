# `video-composer/hooks/`

Module-specific React hooks — overlay geometry math, drag/resize interaction,
trim timeline behaviour.

Pure logic here is what Vitest covers (PRD §8: tests go where bugs are
invisible). Overlay geometry and clamping are the first real targets, in P3.
