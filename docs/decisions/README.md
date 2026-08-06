# Decision records

Two kinds of document live here, and the distinction is deliberate.

**`p0-questionnaire.md`** — the verbatim record of the 126-question specification
interview that preceded P0 code. Every item that _elaborates_ the locked specs
belongs there and nowhere else.

**`p1-questionnaire.md`** — the 75-item interview (Q127–Q201) that preceded P1.
Same notation and rationale-first rule as P0.

**ADRs (`NNNN-*.md`)** — one per decision that _contradicts_ a locked
specification document, plus any decision substantial enough to want revisiting
later. A contradicting ADR names the superseded section in its Status line.

`PRD.md`, `Tech.md`, and `DB.md` stay **byte-identical**. They are the contract.
Anyone reading a superseded section finds what overrode it through this index —
the spec is never edited in place.

> A decision is not changed by writing different code. It is changed by writing a
> new ADR. — PRD §10

## Index

| ADR                                       | Subject                                                     | Status                                        |
| ----------------------------------------- | ----------------------------------------------------------- | --------------------------------------------- |
| [0000](0000-template.md)                  | Template                                                    | —                                             |
| [0001](0001-shadcn-preset-vite.md)        | shadcn preset `b51GFh7y6` against a Vite target             | Pending — checkpoint 6                        |
| [0002](0002-port-allocation-in-python.md) | The backend allocates its own port                          | Accepted — supersedes Tech.md §2              |
| [0003](0003-tauri-plugin-set.md)          | Tauri plugin set — no `shell`, plus `clipboard-manager`     | Accepted — supersedes Tech.md §2              |
| [0004](0004-backend-package-layout.md)    | Backend package layout and FFmpeg location                  | Accepted — supersedes Tech.md §4.3            |
| [0005](0005-sse-client-library.md)        | SSE client is `eventsource` v3                              | Accepted                                      |
| [0006](0006-pyinstaller-onedir.md)        | PyInstaller `onedir`, not `onefile`                         | Accepted — supersedes Tech.md §4, PRD §7 (P6) |
| [0007](0007-ffmpeg-gpl-build.md)          | FFmpeg GPL static build (BtbN `win64-gpl`)                  | Accepted — supersedes p0-questionnaire Q52    |
| [0008](0008-alpha-clip-bleed-box.md)      | Alpha clip at bleed box, not bounding box                   | Accepted — supersedes PRD §6.3                |
| [0009](0009-determinism-definition.md)    | Determinism: byte-identical locally, tolerant cross-machine | Accepted — supersedes PRD §2 (Principle 6)    |
| [0010](0010-cache-shape.md)               | Three asset layers; nested cache keys                       | Accepted — supersedes DB.md §1, §5            |
| [0011](0011-error-details-cap.md)         | 64 KiB cap on stored FFmpeg stderr                          | Accepted — supersedes DB.md §3.3              |
| [0012](0012-local-media-transport.md)     | Local media transport — Tauri asset protocol                | Accepted                                      |

## Superseded specification sections

Quick reverse lookup for a reader who starts from the spec.

| Spec section                                                | Overridden by |
| ----------------------------------------------------------- | ------------- |
| Tech.md §2 — "Port allocation" as a Tauri responsibility    | ADR-0002      |
| Tech.md §2 — sidecar management via the shell plugin        | ADR-0003      |
| Tech.md §4 — "single sidecar executable"                    | ADR-0006      |
| Tech.md §4.3 — `backend/app/` tree, nested `vendor/ffmpeg/` | ADR-0004      |
| PRD §7 (P6) — "single sidecar executable"                   | ADR-0006      |
| PRD §6.3 — alpha clip at overlay bounding-box size          | ADR-0008      |
| PRD §2 Principle 6 — byte-identical outputs everywhere      | ADR-0009      |
| DB.md §1 — two PNG assets per cache key                     | ADR-0010      |
| DB.md §5 — single flat alpha cache key                      | ADR-0010      |
| DB.md §3.3 — full FFmpeg stderr in `error_details`          | ADR-0011      |
| p0-questionnaire Q52 — LGPL FFmpeg build                    | ADR-0007      |
