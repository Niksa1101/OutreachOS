# 29 — Clean-machine validation

**What to build:** The installer is validated on a Windows machine that has never seen this project — no Python, no FFmpeg, no development tooling. It installs, launches, walks the user through picking a workspace, creates the database, and reaches a working Campaigns screen.

Diagnostics coverage is completed for the failure modes that only exist in a packaged build: sidecar fails to launch, port bind fails, bundled FFmpeg missing or unrunnable, workspace folder gone or unwritable. Each names the specific failure and offers `Retry` and `Choose Workspace` where those actually help.

**Blocked by:** 28 — Windows installer and sidecar lifecycle hardening; 26 — Workspace relocation.

**Status:** ready-for-agent

- [ ] Installs and launches on a clean Windows machine with no Python, no FFmpeg, and no dev tooling
- [ ] First run initialises a workspace from scratch and reaches a usable Campaigns screen
- [ ] Sidecar launch failure, port bind failure, missing or unrunnable FFmpeg, and a missing or unwritable workspace each show a diagnostics screen naming that specific failure
- [ ] `Retry` and `Choose Workspace` appear where they can actually resolve the failure, and are absent where they cannot
- [ ] Logs are written to the workspace on a clean machine and contain enough to diagnose a failed start
- [ ] Findings from the clean-machine run are recorded, and anything that had to change is captured
