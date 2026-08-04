# ADR-0002: The backend allocates its own port

**Status:** Accepted — **supersedes Tech.md §2**, which lists "Port allocation
and shared-secret token generation" among Tauri's responsibilities.

Token _generation_ remains Tauri's. Only allocation moves.

---

## Context

Tech.md §2 assigns port allocation to Rust, and PRD's P0 deliverables say
"loopback binding, random free port."

The natural Rust implementation is: bind a socket to port 0, read the assigned
port, close the socket, pass the number to Python, and have Python bind it again.
That gap between close and re-bind is a genuine race — small, but real, and on
Windows the failure mode is an opaque bind error at startup.

A stdout channel from Python to Rust is needed regardless, because Rust has to
learn _something_ about readiness.

## Decision

Python binds port 0 itself, hands the already-bound socket directly to uvicorn
via `Server.run(sockets=[sock])`, and reports the resolved port to Rust on the
`@@OOS` control line.

The socket is never closed and re-opened, so there is no window in which another
process can take the port.

## Alternatives considered

- **Rust allocates, Python re-binds** (Tech.md as written). Rejected for the
  race. Roughly ten fewer lines, in exchange for a startup failure that would be
  rare enough to be very hard to reproduce.
- **Fixed port with a fallback scan.** Rejected: predictable ports are exactly
  what the loopback + token threat model is trying not to rely on, and a scan
  reintroduces the race per attempt.

## Consequences

- Rust must parse the control line before it can poll `/health`. The handshake
  therefore has two budgets rather than one: `PORT` within 10s, `/health` 200
  within a further 20s. A miss on either surfaces as `handshake_timeout`, with
  the detail field distinguishing which.
- `OOS_PORT` remains supported as a dev override. Python still reports the
  resolved port on the control line whether it chose the port or was told it.

## References

Questionnaire Q8, Q10, Q39, Q76. Tech.md §2, §4.2; PRD §7 (P0).
