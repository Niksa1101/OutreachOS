# ADR-0012: Local media transport — Tauri asset protocol

**Status:** Accepted

---

## Context

Ticket 09 is the first place the app shows the user's own media inside the
webview: the split-view campaign screen's preview background, a JPEG frame
extracted from the campaign's first screen recording. Ticket 13 needs the same
thing for a full video a moment later — a seekable talking-head source the
trim/focal-point editor scrubs. Nothing in the project does either yet, so
there is no existing pattern to extend, and the choice made here is the one
ticket 13 inherits rather than re-decides.

Two real candidates exist: the Tauri asset protocol (`convertFileSrc`, a
custom `asset:`/`http://asset.localhost` URL the webview loads directly), or a
new authenticated backend endpoint serving the file over HTTP with range
support.

The backend option runs into the app's own auth model. Every route sits under
one router-wide `RequireToken` dependency with an explicit no-exemptions
policy (`core/routes/__init__.py`, Q43) — but a native `<img src>` or
`<video src>` cannot attach the `Authorization: Bearer` header `apiFetch`
sends on every other request. Reaching a bearer-gated endpoint from a media
element means either putting the token in a URL query string, or fetching the
bytes through `apiFetch` and handing the webview a `blob:` URL — which loads
the whole file into memory before playback can start, defeating the native
HTTP range seeking ticket 13's scrubber needs. There is also no
`StreamingResponse`/`Range`/`Content-Range` handling anywhere in the backend
to build that on top of.

The asset protocol has the opposite shape: it implements range-based file
serving already, but its access scope has to be granted from _somewhere_, and
neither the workspace root nor a recording's source path exists until
runtime — the workspace is user-picked at first launch (`workspace::validate`,
Rust-owned) and every source file is user-picked through the native file
dialog (`dialog:allow-open`, already in `src-tauri/capabilities/main.json`).
Nothing about either path can be declared as a static glob in
`tauri.conf.json` ahead of time.

## Decision

Use the Tauri asset protocol for both the cached preview frame (ticket 09) and
the seekable talking-head source (ticket 13), through one shared frontend
module and one new Rust command:

- `tauri.conf.json`'s `app.security.assetProtocol` is enabled with an
  **empty** static `scope`. Nothing is granted by configuration.
- A new command, `allow_media_path(path)`, calls
  `app.asset_protocol_scope().allow_file(path)` at runtime — additive,
  idempotent, and scoped to exactly the one file passed in.
- `frontend/src/core/media/asset-url.ts` (`mediaSrc`) is the single call
  site: it invokes `allow_media_path` for a path once, then returns
  `convertFileSrc(path)`. Every screen that shows user media goes through it.

The trust model mirrors `dialog:allow-open` rather than inventing a new one:
Rust already trusts whatever path the native file dialog hands back without
re-validating it against anything. `allow_media_path` extends that same trust
to paths that came back from the _authenticated_ backend (`RecordingDetail`,
`TalkingHeadDetail`, and the new `PreviewFrameResponse.frame_path`) — the
frontend never calls it with a path the user typed or a page supplied.

## Alternatives considered

- **Authenticated backend endpoint with HTTP range support.** Rejected: no
  native media element can attach the bearer header the rest of the app
  requires, and the alternatives (token in the URL, or a `blob:` URL built
  from a full in-memory fetch) either leak the secret into logs or break
  seeking on a multi-minute source video.
- **Static `assetProtocol.scope` globs naming the workspace and common source
  drives.** Rejected: the workspace root is chosen at runtime and can be
  anywhere, including a sync-folder path Q14's warnings already treat as
  unusual; a glob wide enough to cover arbitrary user-picked source files
  everywhere on disk is not "no wider than... the campaign's referenced
  sources" — it is everything.
- **A `tauri-plugin-fs` read command returning bytes, converted to a `blob:`
  URL.** Rejected for the same reason as the backend option: no range
  support, and ADR-0003 already rejected adding plugins beyond the named P0
  set without a concrete need — this ticket's need (seeking) is exactly what
  the plugin route can't provide.

## Consequences

- `src-tauri/Cargo.toml`: `tauri`'s `protocol-asset` feature, off by default
  in the crate, is now enabled — the one Cargo change this decision requires.
- `src-tauri/tauri.conf.json`: `assetProtocol.enable: true` with `scope: []`;
  `csp`/`devCsp` gain `asset: http://asset.localhost` on `img-src` and a new
  `media-src` directive for the same origin.
- `src-tauri/src/commands.rs` gains one command, `allow_media_path`, and nothing
  else changes about the backend's authenticated surface — it stays exactly as
  scoped as it was before this ticket.
- Scope grants are per-process and in-memory only. A relaunch starts empty;
  the frontend re-grants on first render of a path, which is already what
  happens on every fresh navigation to the campaign screen.
- Ticket 13's player calls `core/media`'s `mediaSrc`/`useMediaSrc` unchanged —
  no second transport decision, per this ticket's explicit instruction not to
  let ticket 13 rediscover the problem.

## References

Tickets/09-split-view-preview-background.md, Tickets/13-talking-head-editor.md.
ADR-0003 (Tauri plugin set). `core/routes/__init__.py` Q43 (router-wide auth,
no exemptions). `core/api/client.ts` Q56/Q96 (the bearer token's custody).
