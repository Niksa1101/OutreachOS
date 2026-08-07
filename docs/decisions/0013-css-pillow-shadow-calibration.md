# ADR-0013: CSS `box-shadow` blur maps 1:1 to Pillow Gaussian blur, no divergence factor

**Status:** Accepted

---

## Context

PRD Known Risk #2 flags that CSS `box-shadow` and Pillow's Gaussian blur are
different algorithms and asks for a calibration pass in P1, resolving through
P3, with golden frames as the drift guard. `OverlayPreview.tsx` (P1 direct-
manipulation editor) renders the shadow as a CSS preview; `overlay_assets.py`
(P1 render engine, ticket 12) renders the same shadow with Pillow's
`ImageFilter.GaussianBlur`. If the two didn't agree on what `shadow.blur`
means, the editor preview would visibly lie about the rendered output.

ADR-0008 already derived CSS `box-shadow`'s blur-to-sigma relationship
(`σ = blur / 2`) to compute the shadow's bleed allowance. `overlay_assets.py`
uses that same relationship directly:

```python
sigma = max(0.5, overlay.shadow.blur / 2.0)
shadow = shadow.filter(ImageFilter.GaussianBlur(radius=sigma * _SUPERSAMPLE))
```

(`overlay_assets.py:143-144`, supersample factor applied uniformly and
downsampled afterward — see the module's supersampling pass — so it doesn't
change the effective sigma in output pixels.)

`OverlayPreview.tsx` passes `overlay.shadow.blur` straight through as the CSS
`box-shadow` blur radius (`px(overlay.shadow.blur)`), with no scaling factor
applied.

## Decision

No divergence factor. `shadow.blur` is defined once, in canvas pixels, and
both renderers interpret it as a CSS-standard blur radius:

- **CSS preview:** `blur` passed directly as the `box-shadow` blur-radius argument.
- **Pillow render:** `blur` converted to Gaussian sigma via `σ = blur / 2`,
  which is the sigma CSS box-shadow implementations use for the same blur-radius
  input (per ADR-0008's derivation).

If a future browser or Pillow version changes either's blur-to-sigma constant,
this ADR is what should change, not a silently-added fudge factor in one
renderer only.

**Opacity** (added when this second CSS/Pillow semantic surfaced during P3
review): `overlay.opacity` fades only the talking-head video layer in both
renderers, not the border, background, or shadow. `overlay_assets.py`
already applied `opacity` solely to the mask layer's alpha
(`_draw_shape_mask`); `OverlayPreview.tsx` originally applied CSS `opacity`
to the whole positioned box, fading the border and shadow along with the
video — a mismatch fixed by moving the CSS `opacity` to the inner video
layer only, matching the render.

## Alternatives considered

- **Empirical divergence factor** (e.g. scale Pillow's sigma by some measured
  ratio to visually match a screenshot of the CSS preview). Rejected: no
  measured mismatch justified one, and an empirical constant with no formula
  behind it rots silently as either renderer's blur implementation changes.
- **Skip the preview shadow entirely, render server-side for accuracy.**
  Rejected: defeats the point of a direct-manipulation editor (PRD §6);
  the whole editor is built on the premise that a CSS preview approximates the
  render closely enough to drag/resize/tune against without a server round trip.

## Consequences

- The shadow-golden-frame coverage added in ticket 12
  (`test_render_golden.py::test_overlay_shape_and_padding_golden_frame`,
  `shape_rounded_rect`/`shape_rect`/`shape_circle_padded` cases, tolerance
  `max_delta=2, max_mae=0.5`) is the drift guard PRD Known Risk #2 asks for —
  it pins the Pillow-rendered output byte-for-byte (within tolerance) and
  fails on any future Pillow render change, whether or not that change
  actually diverges from the CSS mapping. It is not a comparison against the
  CSS preview; nothing automated checks the two renderers against each other.
- No runtime code needs to change to close out Known Risk #2; this ADR is the
  record that the P1→P3 calibration concluded "no offset needed."
- If a real visual mismatch is found later (e.g. during P6 manual QA), the fix
  belongs in this ADR's Decision section — replacing `σ = blur / 2` with
  whatever formula actually matches — not a one-off constant in
  `overlay_assets.py` or `OverlayPreview.tsx` alone.

## References

PRD §9 Known Risk #2. ADR-0008 (blur-to-sigma derivation).
`overlay_assets.py:143-144`. `OverlayPreview.tsx` shadow `boxShadow` style.
Tickets/12-overlay-property-set.md.
