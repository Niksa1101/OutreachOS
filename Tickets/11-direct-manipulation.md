# 11 — Direct manipulation: drag, resize, snap

**What to build:** The user positions the overlay by dragging it in the preview and resizes it with a handle. Dragging near a canvas corner or the safe margin snaps magnetically. Numeric fields for every geometry property sit beside the preview and stay synced in both directions — dragging updates the numbers, typing a number moves the overlay.

Clamping is enforced on every input path equally: drag, resize, snap, and typed value. There is no sequence of interactions that places the overlay off-frame or inverts its dimensions.

**Blocked by:** 10 — Calibrated CSS overlay preview.

**Status:** ready-for-agent

- [ ] Dragging the overlay repositions it and persists the result
- [ ] A resize handle changes width and height, respecting minimum size
- [ ] Magnetic snap engages near the four corners and the safe margin, and can be overridden by continuing to drag
- [ ] Numeric fields for anchor, width, height, and x/y offsets stay synced with direct manipulation in both directions
- [ ] No input path — drag, resize, snap, typed value, or pasted value — can place the overlay off-frame or invert it, covered by tests
- [ ] Out-of-range typed values clamp visibly rather than being silently discarded
