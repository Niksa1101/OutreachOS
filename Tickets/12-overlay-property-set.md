# 12 — Full overlay property set

**What to build:** Every overlay property from the specification is editable and visible in the preview, and produces matching rendered output: the three shapes (circle, rounded rectangle, rectangle), size, scale, x/y offset, opacity, border radius, border, shadow, background, and padding — where padding is the inset between the video and the border, and background is the fill visible in that inset.

Animation is fade in / fade out only, one duration applied to both ends, defaulting to 500ms.

This is where the CSS-versus-Pillow calibration gets settled for real: box-shadow and Gaussian blur are not the same thing, and the golden frames are what keep the two from drifting apart afterwards.

**Blocked by:** 10 — Calibrated CSS overlay preview.

**Status:** done

- [ ] All three shapes are selectable and render correctly in both preview and output
- [ ] Opacity, border radius, border, shadow, background, and padding are all editable and all visible in the preview
- [ ] Padding reads as an inset between video and border, with the background filling that inset — in preview and in output
- [ ] Fade in/out uses a single duration for both ends, defaults to 500ms, and appears in the rendered result
- [ ] The talking head is centre-cropped to fill its box and is never distorted at any aspect
- [ ] Preview and rendered output agree within golden-frame tolerance for all three shapes, and the calibration approach is recorded as an ADR if it required a deliberate offset

**Note:** the spec text above lists "scale" among the required properties, but `OverlayConfig` has no separate scale field — `size` (width/height) already covers it, and a distinct scale multiplier would be redundant on top of it. Recording this here so it doesn't read as unimplemented.
