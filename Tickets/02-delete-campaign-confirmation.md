# 02 — Delete campaign with itemised confirmation

**What to build:** Deleting a campaign asks for confirmation first, and the confirmation names exactly what is about to be removed: the campaign's data, its cached alpha clip, and any un-exported outputs — with counts and sizes where they are known. It states explicitly that the user's source recordings are not touched.

Confirming removes the campaign row (cascading to its assets), deletes the cached alpha clip and un-exported output files from the workspace, and leaves every source file on disk exactly where it was.

**Blocked by:** 01 — Campaign CRUD end-to-end.

**Status:** done

- [ ] The confirmation dialog names campaign data, cached alpha clip, and un-exported outputs as separate line items, not as generic prose
- [ ] The dialog states that source recordings are never touched
- [ ] Cancelling changes nothing
- [ ] Confirming removes the campaign, its assets, its cached alpha clip, and its un-exported outputs from the workspace
- [ ] No file outside the workspace is ever deleted — covered by a test that asserts source paths survive
- [ ] Deleting a campaign that has no cache and no outputs still works and says so accurately
