# P1 verification record

Exit criteria for the headless render engine (PRD §7 P1).

Recorded on 2026-08-05 against `vendor/ffmpeg` build
`n7.1.5-12-g1fdbca85aa-20260803`, Windows 11, libx264.

## Automated checklist

| Criterion | Command | Status |
|---|---|---|
| CLI renders batch to spec-correct MP4s | `outreachos-render render --config tests/fixtures/render/batch.json --out ./out` | pass — 8/8 outputs, correct frame count and duration |
| Golden frames pass | `pytest -m render` | pass — 9 cases × 2 frames, max delta ≤ 2 |
| Recording shorter than D | golden case `short_recording` | pass — warns `recording_shorter_than_talking_head`, freezes last frame via `tpad=stop_mode=clone` |
| Non-16:9 source | golden cases `aspect_4_3`, `aspect_21_9` | pass |
| Cache hit | `build-alpha` twice, second is no-op | pass — `test_cache_hit_requires_probe_ok`, and the bench's warm pass rebuilds nothing |
| Cache invalidation | mutate overlay → new key | pass — `test_assets_key_changes_when_overlay_changes`, `test_alpha_key_nested_under_assets_key` |
| Alpha cache batch speedup | `outreachos-render bench --markdown docs/p1-verification.md` | pass — see the bench table below |
| Frame-accurate trim | gray-ramp fixture | pass — `test_frame_accurate_trim_lands_on_the_expected_ramp_frame` |

Two additional guards were added while building the suite, both for defects the
checklist above did not cover:

- `test_overlay_lands_at_the_configured_offset` — the overlay's visible edge sits
  48px from the canvas edge and does not move when the shadow blur changes
  (ADR-0008). The original code anchored the bleed box, so blur 24 → 64 walked the
  overlay from 84px to 92px.
- The alpha clip is byte-identical across rebuilds of the same cache key. See
  ADR-0009: this needs `-filter_threads 1 -filter_complex_threads 1` in addition
  to `-threads 1`, because `overlay`'s framesync is nondeterministic across filter
  threads.

## Risk #1 — ProRes 4444 alpha clip size / decode speed

A 2.5s, 576×584 alpha clip at ProRes 4444 / `yuva444p10le` is **9.2 MB** — roughly
3× a finished 1080p output (2.8–3.1 MB). It is built once per batch and cached, so
the cost is paid once and amortises across the batch; the warm bench pass below
shows the decode is not the bottleneck. Acceptable at P1 sizes. Worth revisiting if
the overlay box or talking-head duration grows substantially, since the clip scales
with both.

## Risk #3 — NVENC vs CPU for short clips

Hardware encoders were probed and rejected on this machine: `h264_qsv` and
`h264_amf` both failed a trial encode at 1920×1080, so the bench below is CPU
libx264. The capability probe degrades to libx264 without failing the batch, which
is the behaviour this risk called for.

### Bench results (cold vs warm)

| Videos | Cold | Warm | FFmpeg |
|---|---|---|---|
| 8 videos | 12.16s | 8.76s | n7.1.5-12-g1fdbca85aa-20260803 |

Cold builds the alpha clip from scratch; warm reuses the cache entry. The 3.4s
difference is the alpha build, and it is constant per batch rather than per video —
the saving grows with batch size.
