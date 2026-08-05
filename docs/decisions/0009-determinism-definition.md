# ADR-0009: Determinism definition

**Status:** Accepted — **supersedes PRD §2 (Principle 6)**

---

## Context

PRD Principle 6 states: *Identical inputs must always produce identical outputs.*
Taken literally with libx264, that requires `-threads 1` in production — libx264's
default thread count derives from core count, so byte-identical output across
machines is unachievable otherwise, at a 3–4× cost nobody would observe the
benefit of.

Golden-frame tests already force fixed libx264 settings on one machine; the
principle was written before the thread-count implication was examined.

## Decision

**Determinism means:**

1. **Byte-identical output on one machine** with pinned FFmpeg, pinned encoder
   settings, and golden tests forcing `libx264`.
2. **Within-tolerance visually identical across machines** for production encodes
   (hardware encoders, threaded libx264) — measured by the golden-frame MAE/delta
   thresholds, not bytewise comparison.

Production libx264 may use default threading. Hardware encoders (NVENC/QSV/AMF)
are explicitly non-deterministic and never used in the golden suite.

## Alternatives considered

- **`-threads 1` everywhere.** Rejected: 3–4× encode cost for a guarantee no user
  can observe outside the test suite.
- **Drop Principle 6.** Rejected: batch visual consistency still requires same
  inputs → same pixels within tolerance; only the cross-machine byte identity
  claim is relaxed.

## Consequences

- Golden tests pin encoder, pix_fmt, swscale flags, and `-threads 1`; production
  does not.
- **Pinning the encoder is not sufficient on its own.** FFmpeg threads the filter
  graph independently of the encoder, and `overlay`'s framesync pairs its two
  inputs nondeterministically across filter threads — roughly half the frames of a
  75-frame alpha clip differed run to run with `-threads 1` already set.
  Reproducibility additionally requires `-filter_threads 1 -filter_complex_threads 1`.
- The alpha clip carries these flags **unconditionally**, not only under the
  deterministic test path. It is a content-addressed cache entry, so the same key
  yielding different bytes is a correctness bug independent of testing; it is small
  and built once per batch, so the cost is not measurable. The per-video render
  pins threads only under `deterministic=True` and keeps filter threading in
  production.
- PRD §2 Principle 6 stands as intent; this ADR records the measurable definition.
- Benchmark rows in `docs/p1-verification.md` record encoder and machine context.

## References

p1-questionnaire Q141–Q145. PRD §2, §9 Risk #3. Tech.md §5.2, §7.
