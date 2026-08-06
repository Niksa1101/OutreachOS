# 07 — Central validation service

**What to build:** One service decides whether a campaign can be rendered, returning typed issues each carrying a severity. The UI renders those issues rather than deriving its own opinions anywhere.

Blocking: no talking head, no screen recordings, a missing source file (blocking for that row only), and anything unreadable or not a video. Warning: a recording shorter than the talking-head duration, a recording that is not 16:9, and a duplicate company name that was auto-suffixed.

Blocking issues disable _Generate Videos_ and the UI states the specific reason. Warnings appear as inline amber indicators on the affected rows plus a campaign-level summary — they never block.

**Blocked by:** 06 — File-missing detection and Relocate.

**Status:** done

- [x] Validation is a single backend service returning typed issues with severity; no validation logic is duplicated in the frontend
- [x] Every case in the specification's validation table produces the correct issue and severity, covered by tests
- [x] The missing-source blocking issue reads the persisted link-health state rather than re-implementing detection
- [x] _Generate Videos_ is disabled when any blocking issue exists, and the UI names the specific reason rather than saying "not ready"
- [x] Warnings render as inline amber row indicators plus a campaign-level summary and never block rendering
- [x] A row-level blocking issue blocks only that row's participation, and the campaign-level state reflects that accurately
- [x] Validation results refresh when assets are added, edited, or removed
- [x] The campaign status shown on the Campaigns table is derived from this service
