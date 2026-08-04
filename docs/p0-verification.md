# P0 manual verification

Q109: **a living document.** Every later phase adds the failure modes its own
work introduces — P4's queue, P6's packaging — rather than freezing this list at
P0. The checklist is the regression suite for everything automation structurally
cannot reach: process kills, unplugged monitors, folders renamed underneath a
running app.

Run it against a **debug build** (`pnpm dev`) unless an item says otherwise.
Record the date and the outcome; a skipped item is a result too.

---

## How to read this

Each item names what to do, what should happen, and — where it is not obvious —
**why it is on the list**. An item without a reason is an item nobody knows
whether to delete.

---

## Process lifecycle

### 1. Kill the sidecar from Task Manager

Kill `python.exe` (dev) or `outreachos-backend.exe` (packaged) while the app is
on the home screen.

- [ ] The diagnostics screen appears within one budget window (~5s).
- [ ] The code is `sidecar_exited`.
- [ ] `Retry` recovers, and the app returns to the route it was on — not to
      home.

> Q78 makes Rust's child-exit event authoritative. If the app instead sits
> there with a dead SSE stream, the frontend is navigating on fetch failures,
> which is exactly what that decision forbids.

### 2. Kill Tauri from Task Manager

Kill `outreachos.exe` while the backend is running.

- [ ] No orphaned `python.exe` remains (check Task Manager, sorted by name).

> Q38's Job Object with `KILL_ON_JOB_CLOSE`. There is no shutdown path to run
> when the parent is killed outright, so the OS is the only thing that can make
> this guarantee. An orphan here means the job assignment silently failed.

### 3. Close the window normally

- [ ] `.oos-lock` is gone from the workspace.
- [ ] The backend log's last line is a clean shutdown, not a truncation.

> Q118's ordering. The lock is removed after the server stops and before the
> handlers flush.

---

## Workspace

### 4. Rename the workspace folder between runs

Close the app, rename the folder, start it again.

- [ ] Diagnostics shows `workspace_missing`.
- [ ] `Forget this workspace` returns to the picker.
- [ ] Picking the renamed folder works, and its data is intact.

> Q40. Without "Forget", this is a permanent boot loop whose only exit is
> editing app-data by hand.

### 5. Point at a OneDrive path

- [ ] A warning appears naming the provider.
- [ ] It is dismissible — "Use this folder anyway" proceeds.

> Q14. Hard-refusing would misfire constantly: Windows 11 puts `Documents`
> under OneDrive by default.

### 6. Point at `C:\`

- [ ] Refused, with a stated reason rather than a generic error.

### 7. Point at a folder containing unrelated files

- [ ] Refused as not empty, and the message explains what is wanted.

> Q117 leans on this rather than a blocklist — it is what rejects Desktop,
> `%USERPROFILE%` and Documents without naming any of them.

### 8. Corrupt the database header

With the app closed, open `outreachos.db` in a hex editor and change the first
16 bytes. Start the app and re-pick the folder.

- [ ] Rejected at **pick time**, before anything opens it.

> Better here than as a confusing failure three seconds later inside Alembic.

### 9. Non-ASCII workspace path

Use something like `C:\Users\<you>\Тест Проект\`.

- [ ] The picker accepts it and shows it correctly.
- [ ] The database is created and `/settings` shows the path unmangled.
- [ ] The backend log is written inside it and is readable.

> **The most important item on this list.** Q116: the bundled FFmpeg's handling
> of non-ASCII argv on Windows is the one piece not guaranteed by anything in
> our control, and P1 puts these paths on an FFmpeg command line. Finding a
> problem now is cheap; finding it in P1 is not.

### 10. Two instances against one workspace

Start the app, then start it again from a second copy of the executable (or on
a second machine, if the workspace is on a share).

- [ ] The second launch focuses the first window and exits (single instance).
- [ ] On a share: the second machine reports `workspace_locked` and offers
      `Take over`.

> Q22 and Q83. Two processes against one SQLite file is a corruption path.

---

## Database

### 11. First launch creates the database

- [ ] `outreachos.db` exists in the workspace and is at the migration head.
- [ ] `cache/`, `outputs/` and `logs/` exist.
- [ ] `/settings` shows the revision.

### 12. A database from the future

Close the app. Run
`sqlite3 outreachos.db "UPDATE alembic_version SET version_num='9999'"`.

- [ ] Diagnostics shows `database_newer_than_app`.
- [ ] **No Retry button** — retrying does the same thing and fails the same
      way; offering it would suggest the problem might resolve itself.
- [ ] The database is unchanged afterwards.

> Q84: detected _before_ upgrading, because a database written by a newer
> version is not "behind", it is unreadable.

### 13. A backup exists after a revision change

Once a second migration exists (P1 or later), run it against a populated
workspace.

- [ ] `outreachos.db.bak-<rev>` appears.
- [ ] Opening it shows the rows committed immediately before the upgrade.
- [ ] At most three backups are kept.

> Q85: this is the one that would have cost real data. In WAL mode a
> `shutil.copy` produces a backup silently missing the most recent work.

---

## Logs

### 14. Delete the workspace log while running

- [ ] The next write recreates it.
- [ ] Rotation still works afterwards.

### 15. Open the log in an editor and trigger a rotation

Hold `outreachos.log` open in an editor while the backend writes enough to roll
it.

- [ ] The process keeps logging.
- [ ] A deferral note appears rather than silence.

> Q86: `RotatingFileHandler` cannot rename a file another process holds open,
> and the diagnostics screen is _designed_ to read this file. Stock behaviour
> leaves the handler with a closed stream and every subsequent line vanishes.

### 16. Diagnostics actions

On any diagnostics screen:

- [ ] `Copy to clipboard` puts the code, `boot_id`, workspace, detail and log
      tail on the clipboard.
- [ ] `Open logs folder` opens Explorer at the right directory.

> Q103: this is the one button that only ever renders when the user is already
> stuck, so a dead one would be found by a user rather than by us.

---

## Window

### 17. Unplug a second monitor between runs

Move the window to a secondary display, close the app, unplug the display,
start again.

- [ ] The window is visible, on the remaining display, at a usable size.

> Q101: clamp **size** as well as position. A window restored at 2560×1400 onto
> a 1920×1080 panel is positioned perfectly and still unusable.

### 18. A laptop-sized display

On a 1366×768 display (or with the resolution set to it):

- [ ] The window fits, and the titlebar is on screen.

> Q46: Tauri centers but does not clamp.

---

## Transport

### 19. Idle for ten minutes

Leave the app on the home screen for ten minutes.

- [ ] The heartbeat timestamp keeps advancing, roughly every 15s.
- [ ] No reconnect storm in the backend log.
- [ ] Real events are not evicted from the ring buffer.

> Q106: heartbeats carry no `id:` precisely so they cannot consume sequence
> numbers. A ring buffer full of keepalives after ten idle minutes means that
> regressed.

### 20. Suspend and resume

Sleep the machine with the app open, then wake it.

- [ ] The stream reconnects within ~45s.
- [ ] The app does not navigate to diagnostics.

> The watchdog exists for exactly this: a half-open TCP connection produces no
> error, it just goes quiet. And Q78 forbids a fetch failure from navigating.

---

## Record

| Date | Build | Items run | Failures |
| ---- | ----- | --------- | -------- |
|      |       |           |          |
