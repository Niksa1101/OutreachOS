# ADR-0008: Alpha clip encoded at bleed box, not bounding box

**Status:** Accepted — **supersedes PRD §6.3**

---

## Context

PRD §6.3 states the alpha clip is encoded at **overlay bounding-box size, not
full canvas**. That sizing assumes the shadow fits inside the box. It does not:
CSS `box-shadow` extends past the overlay by construction, and clipping the
shadow at the box edge is visible in the corner-anchor default (`bottom_right` at
48/48 px).

## Decision

Encode the alpha clip at the **bleed box** — the bounding box expanded per side
by:

```
bleed = ceil(1.5 × blur) + |offset|
```

asymmetric per side (shadow offset applies independently on x and y). Derived from
CSS `box-shadow`'s σ = blur/2 and a Gaussian's 3σ extent. Bleed is **zero** when
shadow is disabled.

Overlay coordinates in the per-video pipeline use the bleed-box origin so negative
x/y are permitted — clamping overlay coordinates to ≥ 0 would silently reintroduce
the clipping this ADR exists to prevent.

## Alternatives considered

- **Keep bounding box; shrink shadow to fit.** Rejected: changes the visual spec
  and diverges from CSS preview in P3.
- **Full-canvas alpha clip.** Rejected: ProRes 4444 at 1920×1080 for 25 s is
  impractical; the bleed box is the minimum expansion that preserves the shadow.

## Consequences

- `geometry.py` computes bleed alongside anchor placement; Vitest in P3 ports the
  same pure math.
- Cache keys and asset PNG dimensions use bleed-box size, not overlay size.
- Filtergraph overlay step must allow negative x/y.

## References

p1-questionnaire Q133–Q140. PRD §6.2, §6.3. Tech.md §5.3.
