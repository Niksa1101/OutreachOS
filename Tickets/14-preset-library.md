# 14 — Preset library

**What to build:** Inline in the Overlay section: Apply Preset, Save as Preset, and a Manage dialog for renaming and deleting presets. Presets are named snapshots of the full overlay config, global across campaigns.

Applying a preset **copies** its values into the campaign. Editing or deleting a preset afterwards never mutates a campaign that used it — there is no live link between the two.

**Blocked by:** 12 — Full overlay property set.

**Status:** done

- [ ] Save as Preset captures the complete current overlay config under a user-supplied name
- [ ] Apply Preset copies values into the campaign and the preview updates immediately
- [ ] Editing a preset does not change any campaign that previously applied it — covered by a test
- [ ] Deleting a preset does not change any campaign that previously applied it
- [ ] Preset names are unique, and a collision is reported rather than silently overwriting
- [ ] Presets carry the overlay schema version so an older preset can be upgraded on apply rather than corrupting a campaign
