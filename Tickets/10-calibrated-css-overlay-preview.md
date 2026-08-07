# 10 — Calibrated CSS overlay preview

**What to build:** The overlay itself renders in CSS on top of the preview frame, positioned and sized from the campaign's overlay config, and it agrees with what the render engine actually produces.

Geometry is corner-anchor plus pixel width/height plus x/y offsets against the fixed 1920×1080 canvas — always canvas-relative, never content-relative. The same clamping the backend enforces is enforced here, so the overlay can never be described off-frame or inverted.

This is the calibration baseline the rest of the overlay editor is built on: preview and render must agree before any direct-manipulation or styling work lands on top.

**Blocked by:** 09 — Split-view campaign layout with live preview background.

**Status:** done

- [ ] The overlay renders over the preview frame from the persisted overlay config, at the correct anchor, size, and offset
- [ ] Changing the config updates the preview immediately
- [ ] Frontend clamping matches the backend geometry rules, covered by a parity test asserting identical results for the same inputs
- [ ] Anchoring is canvas-relative and unaffected by the source recording's aspect ratio
- [ ] A non-16:9 source produces the aspect warning without shifting the overlay's position
- [ ] Preview position and size agree with rendered output within golden-frame tolerance for the default config
