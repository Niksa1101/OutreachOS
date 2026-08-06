# Tickets by PRD phase

Which PRD phase each ticket belongs to. P0 and P1 are complete and have no tickets here.

The ticket numbers are **dependency order**, not phase order — they mostly agree, with one deliberate exception noted below.

---

## P2 — Campaign & Asset Management

| #   | Ticket                                          |
| --- | ----------------------------------------------- |
| 01  | Campaign CRUD end-to-end                        |
| 02  | Delete campaign with itemised confirmation      |
| 03  | Talking-head assignment with probe on add       |
| 04  | Batch screen-recording drop with parallel probe |
| 05  | Recordings table with inline editing            |
| 06  | File-missing detection and Relocate             |
| 07  | Central validation service                      |
| 08  | Duplicate Campaign                              |

## P3 — Overlay Editor

| #   | Ticket                                                  |
| --- | ------------------------------------------------------- |
| 09  | Split-view campaign layout with live preview background |
| 10  | Calibrated CSS overlay preview                          |
| 11  | Direct manipulation: drag, resize, snap                 |
| 12  | Full overlay property set                               |
| 13  | Talking Head Editor                                     |
| 14  | Preset library                                          |
| 21  | Editor locking — **see the note below**                 |

## P4 — Render Queue

| #   | Ticket                                                     |
| --- | ---------------------------------------------------------- |
| 15  | Worker pool, job enqueue, and the first render from the UI |
| 16  | Alpha-prepare as its own pinned queue row                  |
| 17  | Skip-completed and Re-render All                           |
| 18  | Batch progress, ETA, and sidebar active-job badge          |
| 19  | Queue controls: pause, resume, cancel, retry, reorder      |
| 20  | Failure surfacing and Retry failed                         |
| 22  | Crash and close recovery                                   |

## P5 — Export

| #   | Ticket                                           |
| --- | ------------------------------------------------ |
| 23  | Outputs staging view and Export All              |
| 24  | Company rename renames the output on disk        |
| 25  | Settings: quality, encoder, cache, export folder |
| 26  | Workspace relocation                             |

## P6 — Packaging

| #   | Ticket                                            |
| --- | ------------------------------------------------- |
| 27  | PyInstaller sidecar and bundled FFmpeg            |
| 28  | Windows installer and sidecar lifecycle hardening |
| 29  | Clean-machine validation                          |
| 30  | Production batch acceptance — V1 done             |

---

## Where the numbering and the phases disagree

**Ticket 21, Editor locking, is a P3 deliverable that lands in the middle of P4.**

The PRD says locking is implemented in P3 and exercised in P4. But the ticket's own acceptance criteria are _"a campaign with queued or active jobs reports itself as locked"_ and _"`Cancel Queue` unlocks editing"_ — and neither a queue nor a cancel exists until tickets 15 and 19. Built in P3 it would be unverifiable; it would sit there untested until P4 proved or disproved it.

So it is sequenced after ticket 19 and numbered accordingly. It is still a P3 deliverable, and P3 is not finished until it lands.

**Ticket 27, PyInstaller sidecar, has no real technical blocker.** It is sequenced after all of P5 to match the PRD's phase order, but it would build against today's code. If the PyInstaller freezing risk starts to look worrying, it can be pulled forward without waiting for P2–P5.
