# `modules/`

One directory per product module. Each is self-contained and registers itself
with `core/registry`.

**Cross-module imports are forbidden** and enforced by ESLint. A module may
import `core/` and its own files, nothing else. When two modules need the same
behaviour, it moves to `core/` — it is never imported sideways.

V1 ships exactly one: `video-composer`. The isolation exists so that adding CRM
later is a folder plus one registry line, not a refactor.
