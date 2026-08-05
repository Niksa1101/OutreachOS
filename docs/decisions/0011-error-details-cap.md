# ADR-0011: FFmpeg stderr cap in stored error details

**Status:** Accepted — **supersedes DB.md §3.3**

---

## Context

DB.md §3.3 defines `render_jobs.error_details` as **full FFmpeg stderr**. A failed
NVENC trial or a verbose filtergraph can emit hundreds of kilobytes. SQLite rows
that large hurt query performance and the diagnostics UI; the full text is still
required for debugging.

PRD §6.8 already requires a rolling workspace log.

## Decision

Store **at most 64 KiB** in `error_details` — head plus tail with an inline
elision marker recording how many bytes were omitted. Write the **uncapped copy**
to the rolling log (`<workspace>/logs/outreachos.log`) at ERROR level.

The P1 CLI applies the same cap to stderr printed on failure; the log file always
gets the full stream.

## Alternatives considered

- **Uncapped in DB.** Rejected: unbounded row growth on repeated failures.
- **Summary only in DB.** Rejected: loses the actionable tail (the actual FFmpeg
  error line is usually last).

## Consequences

- `rendering/errors.py` exposes `cap_stderr()` used by CLI now and P4 job persistence
  later.
- P4 queue worker must log full stderr before capping for DB insert.

## References

p1-questionnaire Q156–Q160. DB.md §3.3. PRD §6.8.
