# 13 — Talking Head Editor

**What to build:** A dedicated editor for the talking head: a video player, a trim timeline with draggable in and out handles, and a draggable focal point shown inside a live preview of the current overlay shape — so the user sees exactly what the centre-crop will keep.

The trim determines the output duration for the whole campaign, so the resolved duration is displayed prominently. Trim and focal point persist and feed the render engine.

**Blocked by:** 09 — Split-view campaign layout with live preview background; 03 — Talking-head assignment with probe on add.

**Status:** done

- [ ] A player scrubs the talking head using the local-media transport established in ticket 09, with in/out handles on a trim timeline
- [ ] The resolved output duration after trim is displayed and updates live
- [ ] Trim cannot invert, cannot exceed source bounds, and cannot resolve to a zero-length clip
- [ ] The focal point is draggable inside a live preview of the current overlay shape, and the crop it implies is what the render produces
- [ ] Trim and focal point persist and are picked up by the render engine
- [ ] Changing trim or focal point invalidates the campaign's alpha cache key
