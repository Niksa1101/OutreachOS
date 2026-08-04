# `core/layout/`

The application shell: boot UI, diagnostics screen, sidebar frame, and the
ready-state layout that modules render into.

`AppRoot.tsx` is the composition root rendered by `src/main.tsx`. It grows a boot
gate in checkpoint 4 and the sidebar shell in checkpoint 6.

The diagnostics screen has one hard constraint: it is **DB-free by
construction**. Everything it displays comes from `/health`'s `BootReport` or a
Rust `invoke`. It renders precisely when the backend is broken, so anything it
touches must survive a dead database and a dead sidecar.
