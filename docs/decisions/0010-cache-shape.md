# ADR-0010: Cache key shape and asset layers

**Status:** Accepted — **supersedes DB.md §1 and §5**

---

## Context

DB.md §1 shows two asset files per cache key (`_mask.png`, `_frame.png`). DB.md §5
defines a single alpha cache key over talking-head identity + overlay config.

Rendering requires **three** compositing layers: a backdrop (shadow + background)
behind the video, a mask, and a frame (border) in front. A shadow must render
*behind* the talking-head video; a border must render *in front*. Two PNGs
cannot express that ordering without an extra decode pass or incorrect z-order.

Format-version bumps (code changes to asset generation or alpha encoding) must
invalidate cache entries without mutating user config.

## Decision

**Three asset layers:** `backdrop`, `mask`, `frame` — each a straight-alpha RGBA
PNG at bleed-box dimensions.

**Two keys:**

- `assets_key` — hash of overlay config + bleed geometry + `ASSETS_FORMAT_VERSION`.
- `alpha_key` — hash of talking-head identity (path, mtime, size), trim, focal
  point, `assets_key`, and `ALPHA_FORMAT_VERSION`. Nested: alpha depends on assets.

Paths under `<workspace>/cache/`:

```
assets/<assets_key>/backdrop.png
assets/<assets_key>/mask.png
assets/<assets_key>/frame.png
alpha/<alpha_key>.mov
alpha/<alpha_key>.manifest.json   # owner_ref + owner_kind for P5 orphan sweep
```

`ASSETS_FORMAT_VERSION` and `ALPHA_FORMAT_VERSION` are integer constants in code;
bumping either invalidates the corresponding cache tier without a schema migration.

## Alternatives considered

- **Two PNGs; composite shadow in FFmpeg.** Rejected: duplicates Pillow logic and
  breaks CSS↔Pillow parity testing.
- **Single combined PNG.** Rejected: cannot split static backdrop/frame from the
  dynamic mask+video alphamerge step cleanly.

## Consequences

- DB.md §1 `masks/` layout is superseded by `assets/<key>/`; P2 migration adds
  nothing — workspace cache is filesystem-only until first render.
- Campaign `alpha_cache_key` stores `alpha_key`; asset drift is detectable via
  nested `assets_key`.
- Cache write: temp file then `os.replace`; miss if file missing or FFprobe fails.

## References

p1-questionnaire Q146–Q155. DB.md §1, §5. PRD §6.3. Tech.md §5.3.
