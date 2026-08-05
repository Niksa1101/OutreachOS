# P1 Specification Interview — Q127–Q201 (75 items)

The complete record of the questions resolved before P1 code was written, across
five rounds. Each entry gives the question, the decision, and — where the answer
deviated from the recommendation — the reasoning verbatim. **The rationales are
the point of this document.**

Items that *elaborate* the locked specs live here. Items that *contradict* one
also carry an ADR that names the superseded section. See [`README.md`](README.md).

Notation: `▲` marks a deviation from the recommended option. `′` marks a variant
of an option rather than a clean choice.

---

## Definition of done (Step 0 documentation commit)

Before any P1 branch lands:

- [x] [ADR-0007](0007-ffmpeg-gpl-build.md) — GPL static BtbN build; supersedes Q52
- [x] [ADR-0008](0008-alpha-clip-bleed-box.md) — bleed box; supersedes PRD §6.3
- [x] [ADR-0009](0009-determinism-definition.md) — determinism scope; supersedes PRD §2
- [x] [ADR-0010](0010-cache-shape.md) — three asset layers + nested keys; supersedes DB.md §1, §5
- [x] [ADR-0011](0011-error-details-cap.md) — 64 KiB cap; supersedes DB.md §3.3
- [x] This file — Q127–Q201
- [x] `docs/decisions/README.md` index rows
- [x] `PRD.md` status only
- [x] `vendor/README.md` — GPL, static, source archival

`Tech.md` and `DB.md` remain byte-identical.

---

## Round 1 — Licensing, binaries, process wrapper (Q127–Q140)

### A. FFmpeg licensing and fetch

**Q127 — LGPL vs GPL build. ▲** GPL static `win64-gpl`, not LGPL.

> Q52 chose LGPL to avoid a source-offer obligation, but libx264 is GPL-only and
> is the named CPU fallback in Tech.md §5.1/§5.2/§7. An LGPL build cannot
> contain it. libopenh264 has no CRF and worse screen-recording quality. Take the
> compliance cost now; retrofitting at P6 is worse.

See [ADR-0007](0007-ffmpeg-gpl-build.md).

**Q128 — Shared vs static.** Static executables only.

> The LGPL shared build's DLL resolution hazard disappears with two self-contained
> `.exe` files. PyInstaller in P6 bundles a directory anyway.

**Q129 — Fetch script language.** PowerShell (`scripts/fetch-ffmpeg.ps1`).

> Bootstrap must not require Python. Pin immutable BtbN release **tag**, never
> `latest`. `Get-FileHash` against pinned SHA256. `Expand-Archive` into
> `vendor/ffmpeg/`.

**Q130 — Source archival.** Matching FFmpeg source tarball archived beside binaries.

> GPL compliance artifact built in P1, not retrofitted. Stored under
> `vendor/ffmpeg/source/` (gitignored).

**Q131 — Version pin enforcement.** Full first line of `ffmpeg -version` stored;
mismatch warns at runtime, **hard-fails under `-m render`**.

**Q132 — Binary resolution.** Explicit `--ffmpeg-dir` only; reuse
`core/config.py` precedence (CLI > env > `.env`, `OOS_` prefix). Never PATH.

### B. Process wrapper

**Q133 — Module location.** `rendering/process.py`, not `core/`.

> `core/errors.py` imports FastAPI/Starlette at module scope; the render engine
> must stay importable from CLI without dragging the web stack.

**Q134 — Argument passing.** Args as a **list**, never a shell string.

> p0-Q116: `CreateProcessW` preserves wide chars only if nothing round-trips
> through a shell.

**Q135 — Window creation.** `CREATE_NO_WINDOW` on Windows; `stdin=DEVNULL` plus
FFmpeg `-nostdin`.

**Q136 — Pipe draining.** One reader thread per pipe; both drained to EOF before
`wait()`. Stall timeout resets on any progress line.

**Q137 — Live process registry.** Module-level registry of handles; killed in the
shutdown hook alongside p0-Q118's sequence.

**Q138 — Render errors.** `rendering/errors.py` hierarchy separate from
`core/errors.py`. Warning-code constants for non-fatal issues.

**Q139 — Probe fps field.** `avg_frame_rate` for stored fps; `r_frame_rate` is
routinely `1000/1` on VFR screen recordings.

**Q140 — Rotation metadata.** `side_data_list` first; `tags.rotate` fallback only.
Display dimensions derived from rotation.

---

## Round 2 — Geometry, assets, bleed box (Q141–Q155)

**Q141 — Determinism scope. ▲** Byte-identical on one machine; within-tolerance
across machines. Not `-threads 1` in production.

> PRD Principle 6 literally requires cross-machine byte identity with libx264's
> default threading — unachievable at acceptable cost. Golden tests pin settings;
> production does not.

See [ADR-0009](0009-determinism-definition.md).

**Q142 — Alpha clip dimensions. ▲** Bleed box, not bounding box.

> Shadow extends past the overlay; clipping at the box edge is visible at default
> `bottom_right` placement. Bleed = `ceil(1.5 × blur) + |offset|` per side.

See [ADR-0008](0008-alpha-clip-bleed-box.md).

**Q143 — Audio in alpha clip.** 48 kHz stereo `pcm_s16le`; 15 ms de-click at
ends; `anullsrc` when source has no audio. Resample when probe `sample_rate` /
`channels` differ.

**Q144 — Geometry module purity.** `rendering/geometry.py` — pure math, no FFmpeg
or Pillow. Vitest port in P3 must be mechanical.

**Q145 — Even rounding.** Applied at all three stages: box dims → anchor math →
clamp. Rounding only after anchor math drifts right/bottom by one pixel.

**Q146 — Asset layers. ▲** Three layers: backdrop (shadow + background), mask,
frame (border).

> Shadow behind video, border in front — two PNGs cannot express z-order.

See [ADR-0010](0010-cache-shape.md).

**Q147 — Pillow compositing.** 4× supersample + LANCZOS downscale. Straight alpha
via `Image.alpha_composite`; never `paste` with mask. σ = blur/2 for shadow.

**Q148 — Pillow pin.** Exact version in `pyproject.toml`; Tech.md §9
re-verification rule in comment.

> **Forward flag:** `RING_CAPACITY = 200` in `core/events.py:57` will be undersized
> once P4 publishes ~3000 progress events per batch. Not P1 scope; recorded here.

**Q149 — Reference PNGs.** Committed fixtures for 2–3 representative overlay configs;
blur regression fails with legible mask diff, not 40 frame deltas.

**Q150 — Cache path normalization.** `os.path.normcase` for keys — not
`casefold` (leaves `/` and `\` hashing differently on Windows).

**Q151 — Cache write atomicity.** Write to `.tmp`, then `os.replace`.

**Q152 — Cache hit validation.** Clip must exist **and** FFprobe successfully or
it is a miss.

**Q153 — Manifest sidecar.** `owner_ref` + `owner_kind` on alpha entries for P5
orphan sweep.

**Q154 — Format version constants.** `ASSETS_FORMAT_VERSION`, `ALPHA_FORMAT_VERSION`
— code-only bumps, not schema migrations.

**Q155 — Canonical JSON for hashing.** `json.dumps(sort_keys=True, separators=(",", ":"))`.

---

## Round 3 — Filtergraph, alpha encode, cache CLI (Q156–Q170)

**Q156 — Error details cap. ▲** 64 KiB head+tail in stored details; full stderr to
rolling log.

See [ADR-0011](0011-error-details-cap.md).

**Q157 — Graph context owns inputs.** `GraphContext` registers `-i` entries, not
just labels — alpha clip and future text layers need new inputs.

**Q158 — Step objects carry ids.** Tests assert step contributions, not
string-matched filtergraph output.

**Q159 — Graph tests only on `p1/03`.** No rendering until graph structure is locked.

**Q160 — Alpha codec.** ProRes 4444 `yuva444p10le` via `prores_ks`; QTRLE fallback
if probe fails in P1 measurement.

**Q161 — Alpha fps.** `fps=30` filter plus `-fps_mode cfr`.

**Q162 — Post-build frame assert.** FFprobe alpha clip; assert exactly `N` frames
after every build. Converts timing bugs into immediate localized failures.

**Q163 — Alpha filter order.** scale/crop focal → alphamerge (video + mask) →
composite (backdrop + frame static PNGs) → alpha fade → encode.

**Q164 — Quality tiers.** CRF/preset per tier in `presets.py`; bt709 color tagging.

**Q165 — x264 keyframe cadence. ▲** `-g 60 -keyint_min 60` with `-sc_threshold 0`
rejected as redundant when `-g` equals `-keyint_min`.

**Q166 — NVENC rate control.** `-rc vbr -b:v 0` alongside `-cq`.

**Q167 — Encoder trial dimensions.** Trial-encode **1920×1080** per candidate;
QSV and AMF initialize at 64×64 but fail at real dimensions.

**Q168 — Capability cache.** Lazy probe; cached in `app_settings.detected_encoders`
keyed on FFmpeg version string (P4 wires persistence; P1 CLI caches in-memory).

**Q169 — `--cache-dir` default.** `.outreachos-cache/` beside `--out`.

**Q170 — `build-alpha` subcommand.** Standalone alpha rebuild for cache testing.

---

## Round 4 — Per-video pipeline, progress, render CLI (Q171–Q188)

**Q171 — Trim seek.** Input-side `-ss`/`-t` with explicit `-accurate_seek`.

**Q172 — Scale/pad skip.** Skip entirely when source is exactly 1920×1080 (dominant
class).

**Q173 — tpad margin.** ~2 frames of margin beyond `D`.

**Q174 — Overlay coordinates.** Negative x/y **permitted** — default placement puts
bleed box off-canvas; clamping to ≥ 0 reintroduces shadow clipping.

**Q175 — Output atomicity.** Write to `.part`, then `os.replace`.

**Q176 — Frame count assert.** `nb_frames` from container header — not
`-count_frames` (decodes entire file).

**Q177 — Duration encode.** `-frames:v N` and `-t D_exact` together.

**Q178 — Progress parser.** `-progress pipe:1`; prefer `out_time_us`, `out_time`
fallback; monotonic percent.

**Q179 — Progress callback injection.** Engine never imports `core/events.py`; P4
injects SSE publisher.

**Q180 — Alpha failure cascade.** Flat per-job status in P1 CLI; six-state enum
stays with queue in P4.

**Q181 — Render exit codes.** `0` success · `1` some jobs failed · `2` usage.

**Q182 — `--dry-run`.** Print exact commands; create no directories.

**Q183 — Batch JSON contract.** Standalone CLI reads JSON; no HTTP, no DB from
`rendering/`.

**Q184 — Import boundary.** Ruff `flake8-tidy-imports` banned-api: `rendering.*`
must not import `modules.*` or `core.db`.

**Q185 — Lint marker.** `render` pytest marker registered in `pyproject.toml`.

**Q186 — Non-16:9 warning.** Emit `aspect_ratio_not_16_9` warning code; centered
letterbox with black bars.

**Q187 — Short recording.** tpad freeze; last frame is frozen content, not black.

**Q188 — Rotated phone video.** Honor rotation side-data; render upright (silent-wrong
if ignored, not crash).

---

## Round 5 — Golden suite, bench, CI, verification (Q189–Q201)

**Q189 — Gray-ramp fixture.** `geq` frame `i` → flat gray patch at `(i mod 32) × 8`
luma in subsampled `yuv420p`; FFV1 `gray` in MKV. Reads average 32×32 region for
frame-accurate trim assertion.

**Q190 — Real samples.** Two committed samples (talking head, VFR screen recording);
self-recorded; no LFS; ~8–15 MB total.

**Q191 — Golden case matrix.** Nine cases: 1080p baseline, 4:3, 21:9, short-recording
tpad, VFR, real end-to-end, three shapes, no-audio, rotate side-data.

**Q192 — Comparison thresholds.** Max channel delta ≤ 2 **and** MAE ≤ 0.5; looser ≤ 6
on mid-fade sample. Decode: `-pix_fmt rgb24 -sws_flags full_chroma_int+accurate_rnd`.

**Q193 — Overlay centroid diagnostic.** Alongside whole-frame comparison.

**Q194 — Golden encoder.** Force `libx264` with fixed settings in golden tests only.

**Q195 — `--update-golden`.** Gated on clean working tree (`git status --porcelain`).

**Q196 — `bench` subcommand.** Cold vs warm cache; `--markdown` appends to
`docs/p1-verification.md`; reduced ~8-video set with set size in row.

**Q197 — CI FFmpeg cache.** `scripts/fetch-ffmpeg.ps1` in Windows job; `actions/cache`
keyed on pinned version tag.

**Q198 — Checkpoint branches.** Six branches `p1/01`…`p1/06`, squash-merged like P0.
Graph assertions (`03`) before rendering (`04`).

**Q199 — `docs/p1-verification.md`.** Exit-criteria checklist plus Risk #1/#3 tables.

**Q200 — Manual verification gate.** ~10-video real batch; confirm overlay placement,
shadow not clipped, no audio click, rotated phone upright — once before declaring P1 done.

**Q201 — PRD §10 path fix. ▲** Per-phase question ranges in status line; path
`docs/decisions/` not `docs/adr/`. Count never edited again.

---

## Cross-reference: code decisions recorded here (not document edits)

| Item | Decision | Where |
|------|----------|-------|
| Q165 | `-g 60 -keyint_min 60`, reject `-sc_threshold 0` | `rendering/presets.py` |
| Q148 | Pillow exact pin | `backend/pyproject.toml` |
| Q148 forward | `RING_CAPACITY = 200` undersized at P4 | `core/events.py:57` |
| Q184 | Import ban | `pyproject.toml` `[tool.ruff.lint.flake8-tidy-imports]` |
