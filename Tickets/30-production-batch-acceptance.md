# 30 — Production batch acceptance — V1 done

**What to build:** The real thing, in the packaged build: a genuine batch of roughly 30 prospect videos, from creating the campaign through to exported files ready to upload.

This is the V1 definition of done. Developer-mode success does not count. Every subsystem is exercised together, on real footage, on an installed application.

**Blocked by:** 29 — Clean-machine validation.

**Status:** ready-for-agent — verification procedure in [`docs/p6-verification.md`](../docs/p6-verification.md); helper scripts in `scripts/verify-no-network.ps1` and `scripts/verify-batch-output.ps1`. Preflight packaging checks pass; full acceptance run requires real media kit on installed build.

- [ ] A campaign of ~30 real prospect recordings is created, configured, and rendered in the packaged build
- [ ] The generated videos match expected visual output on real footage, not just on synthetic fixtures
- [ ] The batch completes unattended
- [ ] Queue behaviour, export, alpha cache reuse, crash recovery, and validation are each verified in the packaged build
- [ ] Export moves the files out, reclaims the disk, and leaves the queue clean
- [ ] The application makes zero network calls throughout — verified, not assumed
- [ ] The run is recorded as a verification document alongside the existing phase verification records
