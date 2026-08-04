# Decision records

Two kinds of document live here, and the distinction is deliberate.

**`p0-questionnaire.md`** — the verbatim record of the 126-question specification
interview that preceded any code. Every item that _elaborates_ the locked specs
belongs there and nowhere else.

**ADRs (`NNNN-*.md`)** — one per decision that _contradicts_ a locked
specification document, plus any decision substantial enough to want revisiting
later. A contradicting ADR names the superseded section in its Status line.

`PRD.md`, `Tech.md`, and `DB.md` stay **byte-identical**. They are the contract.
Anyone reading a superseded section finds what overrode it through this index —
the spec is never edited in place.

> A decision is not changed by writing different code. It is changed by writing a
> new ADR. — PRD §10

## Index

| ADR                                       | Subject                                                 | Status                                        |
| ----------------------------------------- | ------------------------------------------------------- | --------------------------------------------- |
| [0000](0000-template.md)                  | Template                                                | —                                             |
| [0001](0001-shadcn-preset-vite.md)        | shadcn preset `b51GFh7y6` against a Vite target         | Pending — checkpoint 6                        |
| [0002](0002-port-allocation-in-python.md) | The backend allocates its own port                      | Accepted — supersedes Tech.md §2              |
| [0003](0003-tauri-plugin-set.md)          | Tauri plugin set — no `shell`, plus `clipboard-manager` | Accepted — supersedes Tech.md §2              |
| [0004](0004-backend-package-layout.md)    | Backend package layout and FFmpeg location              | Accepted — supersedes Tech.md §4.3            |
| [0005](0005-sse-client-library.md)        | SSE client is `eventsource` v3                          | Accepted                                      |
| [0006](0006-pyinstaller-onedir.md)        | PyInstaller `onedir`, not `onefile`                     | Accepted — supersedes Tech.md §4, PRD §7 (P6) |

## Superseded specification sections

Quick reverse lookup for a reader who starts from the spec.

| Spec section                                                | Overridden by |
| ----------------------------------------------------------- | ------------- |
| Tech.md §2 — "Port allocation" as a Tauri responsibility    | ADR-0002      |
| Tech.md §2 — sidecar management via the shell plugin        | ADR-0003      |
| Tech.md §4 — "single sidecar executable"                    | ADR-0006      |
| Tech.md §4.3 — `backend/app/` tree, nested `vendor/ffmpeg/` | ADR-0004      |
| PRD §7 (P6) — "single sidecar executable"                   | ADR-0006      |
