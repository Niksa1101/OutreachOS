# 28 — Windows installer and sidecar lifecycle hardening

**What to build:** A Windows installer that produces a real installed application, identified as `OutreachOS` / `com.outreachos.app` with the placeholder icon.

In the packaged build the sidecar lifecycle has to be correct, not merely usually correct: it starts reliably, passes a health check before the UI trusts it, shuts down gracefully when the app closes, and leaves no orphaned process behind under any exit path — including a force-quit of the main window.

**Blocked by:** 27 — PyInstaller sidecar and bundled FFmpeg.

**Status:** complete

- [x] The Windows installer builds and produces an installed, launchable application
- [x] Application identity and icon are correct in the installer, the executable, and the taskbar
- [x] The packaged app starts its sidecar and waits on a health check before presenting the UI
- [x] Closing the app shuts the sidecar down gracefully
- [x] Force-quitting the main window leaves no orphaned backend process
- [x] Single-instance enforcement still works in the packaged build — a second launch focuses the first
- [x] Uninstalling removes the application without touching the user's workspace
