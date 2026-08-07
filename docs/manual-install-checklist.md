# Manual install validation — final P6 sign-off

Short checklist for the one thing automated verification cannot do: install from
the NSIS `.exe` the way a real user would, on a machine with **no Python, no
FFmpeg on PATH, and no dev tooling**, and confirm the app starts and renders.

Everything else in P6 packaging (sidecar build, resource layout, shutdown path,
export guard, test suites) is already verified. This is the gold-standard pass.

**Installer:** `src-tauri/target/release/bundle/nsis/OutreachOS_0.1.0_x64-setup.exe` (~111 MB)  
**Install location:** `%LOCALAPPDATA%\OutreachOS` (Tauri NSIS `currentUser` mode — *not*
`%LOCALAPPDATA%\Programs\OutreachOS`)

Steps 0–3, 5 and the layout checks were run on the dev machine 2026-08-07 and are
recorded below; they still want a repeat on a genuinely clean box. Step 4 (real
render) and step 6 (uninstall) are untouched.

---

## 0. Prepare the machine

A Windows 11 VM snapshot is ideal — you can roll back and re-run.

- [ ] No Python on PATH — `python --version` fails
- [ ] No FFmpeg on PATH — `ffmpeg -version` fails
- [ ] Copy the installer over; note its SHA-256 if you want a record

```bash
powershell -c "Get-FileHash .\OutreachOS_0.1.0_x64-setup.exe -Algorithm SHA256"
```

---

## 1. Install

- [x] Silent `/S` install returns exit 0 and populates the install directory
      *(the earlier "silent install doesn't work" reading was a wrong path — the
      files were always there, just under `%LOCALAPPDATA%\OutreachOS`)*
- [ ] Double-click the setup `.exe` and complete the wizard (do this at least
      once — the GUI path is what a user actually runs)
- [ ] SmartScreen warning is expected (unsigned build) — note whether it appears
- [ ] Install completes without an elevation prompt (`installMode: currentUser`)

Then confirm the layout that the packaging fix was about:

```bash
powershell -c "Get-ChildItem $env:LOCALAPPDATA\OutreachOS -Recurse -Depth 1 | Select-Object FullName"
```

- [x] `outreachos.exe` at the install root
- [x] `backend\outreachos-backend.exe` and `backend\outreachos-render.exe`
- [x] `backend\_internal\` present (PyInstaller runtime)
- [x] `ffmpeg\ffmpeg.exe` and `ffmpeg\ffprobe.exe`
- [x] `THIRD-PARTY-LICENSES.md` at the root

> If `backend\` or `ffmpeg\` are missing or nested one level deeper, that is the
> original blocker regressing — stop and report the actual tree.

> **Note:** the install directory and the app-data directory are the same folder,
> so `logs\boot.log` sits inside the installed tree. Harmless today, but it means
> uninstall touches log data — see the findings table.

---

## 2. First launch

- [x] App launches; boot log records `dev=false` and the installed sidecar path
- [ ] Workspace picker appears on a profile with no stored workspace
      *(not exercised here — the dev profile already had one)*
- [ ] Pick a fresh folder, e.g. `C:\Users\<you>\Documents\OutreachOS`
- [x] Workspace initialises — `database is at head (0003)`, no migration error
- [x] Sidecar handshake completes; API accepting requests
- [ ] Reaches the Campaigns screen (visual confirmation)

If it fails, grab both logs before retrying:

```bash
powershell -c "Get-Content $env:LOCALAPPDATA\OutreachOS\logs\boot.log -Tail 60"
```

```bash
powershell -c "Get-Content \"$env:USERPROFILE\Documents\OutreachOS\logs\outreachos.log\" -Tail 60"
```

---

## 3. Bundled FFmpeg is the one being used

The whole point of shipping FFmpeg — on this machine there is no PATH fallback
to mask a broken bundle.

- [x] Boot log resolves `ffmpeg directory: ...\OutreachOS\ffmpeg` (install dir, not PATH)
- [x] Cached probe reports `n7.1.5-12-g1fdbca85aa-20260803`, matching `ffmpeg\VERSION.txt`
- [x] Encoder detection ran against the bundled binary (`h264_nvenc`, `libx264`
      available; `h264_qsv` / `h264_amf` correctly rejected on this hardware)
- [ ] Settings screen shows the same version; health is `ok`, not `degraded`

---

## 4. One real render

Doesn't need the full 30-video batch — that's ticket 30. Prove the packaged
process tree can encode at all.

- [ ] Create a campaign, assign a talking head, add 2–3 screen recordings
- [ ] Configure the overlay; preview renders
- [ ] *Generate Videos* — alpha-prepare runs, then video jobs complete
- [ ] Output MP4 plays: 1920×1080, overlay in the right corner, talking-head audio only
- [ ] *Export All* moves files out; staging empties; queue clears

---

## 5. Shutdown leaves nothing behind

The shutdown-split fix — verify it in the installed build, not just dev.

- [x] Close the app with the queue idle — window closes, sidecar gets
      `stdin closed; shutting down`, exits with status 0
- [x] No `outreachos-backend.exe` or `ffmpeg.exe` left running:

```bash
powershell -c "Get-Process outreachos,outreachos-backend,ffmpeg -ErrorAction SilentlyContinue | Select-Object Name,Id"
```

- [x] Force-killing `outreachos.exe` also reaps the sidecar (no orphan)
- [ ] Close **during** an active render → confirmation prompt appears
- [ ] Cancel keeps the app open; Confirm exits with no orphan process

> This step caught the ACL blocker below. Re-run it against any build where
> `capabilities/main.json` changed.

---

## 6. Uninstall

- [ ] Uninstall from Settings → Apps
- [ ] Install directory is removed
- [ ] Workspace folder and its outputs are **left intact** (user data survives)

---

## Result

| Field | Value |
| --- | --- |
| Date | 2026-08-07 |
| Machine | Dev machine, installed build (**not** a clean box — repeat required) |
| Installer SHA-256 (pre-fix build) | `76CC9661…5BC81A87` |
| Install layout correct | Pass — `backend\`, `ffmpeg\`, licenses at install root |
| First launch → sidecar ready | Pass — migrations at head, handshake on 127.0.0.1:49658 |
| Bundled FFmpeg resolved | Pass — install-dir FFmpeg, version matches `VERSION.txt` |
| Render + export | **Not run** — needs GUI interaction |
| Window close | Fail on first build → fixed → pass on rebuild (finding 1) |
| No orphan processes | Pass — clean sidecar exit, status 0 |
| Uninstall clean | **Not run** |

### Findings

| # | Finding | Resolution |
| --- | --- | --- |
| 1 | Packaged app **could not be closed**. `onCloseRequested` makes Tauri's JS API call `window.destroy()`, which `core:default` does not permit: `Command plugin:window\|destroy not allowed by ACL`. The X button was inert; only Task Manager ended it. `dialog:allow-ask` was missing too, so the close-during-render prompt would have failed the same way. | Added `core:window:allow-destroy` and `dialog:allow-ask` to `src-tauri/capabilities/main.json`; pinned by `close_guard_permissions_are_granted` in `src-tauri/src/window.rs`. Rebuilt, reinstalled, verified closing works and the sidecar exits cleanly. |
| 2 | Earlier "silent install doesn't populate the install dir" was a wrong-path reading — NSIS `currentUser` installs to `%LOCALAPPDATA%\OutreachOS`, not `%LOCALAPPDATA%\Programs\OutreachOS`. | No code change; path corrected in this document. |
| 3 | Install directory and app-data directory are the same folder, so `logs\boot.log` lives inside the installed tree and uninstall will remove it. | Open — decide whether boot logs should move to a sibling app-data folder. |

Remaining before P6 sign-off: run this list on a genuinely clean machine
(no Python, no FFmpeg), covering the workspace picker, one real render + export,
close-during-render, and uninstall. Then ticket 30 (production batch acceptance,
~30 real recordings) is the last P6 item.
