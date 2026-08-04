# ADR-0001: shadcn preset `b51GFh7y6` against a Vite target

**Status:** Pending — checkpoint 6.

Reserved at checkpoint 1 so the number stays stable; it has been referenced as
ADR-0001 since the specification interview and renumbering would break every
citation in the questionnaire.

---

## Context

PRD §3 and Tech.md §3.1 both mandate:

```bash
npx shadcn@latest init --preset b51GFh7y6 --template next --pointer
```

The `--template next` flag names Next.js. This project is Vite + Tauri. PRD §9
lists this as risk #6, to be resolved in P0 with the fallback "keep the preset ID
(it carries the design configuration), adjust only the template target."

The preset ID is opaque — it is a short registry identifier whose contents cannot
be known offline, and there is no way to verify from here whose preset it is.

## Decision

_To be recorded at checkpoint 6._ The planned sequence:

1. Run `shadcn init` and **commit its raw output as its own commit**, before
   editing anything. "What the preset contributed" then becomes a diff citable by
   SHA rather than a prose reconstruction that goes stale immediately.
2. Keep the preset ID; adjust only the template target if `--template next`
   conflicts.
3. Adopt whatever token _architecture_ the preset establishes, then override the
   values with the approved palette (see below).
4. If the preset ID 404s or the fetch is blocked: **stop and ask**, do not guess.

The identity decision is already made and does not wait on the preset:

- Neutrals: zinc scale, `oklch`, dark-first
- Accent: `oklch(0.58 0.15 255)` — a desaturated blue that reads as tooling
- Type: Inter Variable (UI) + JetBrains Mono (logs, IDs, ports), both OFL, both
  self-hosted via `@fontsource-variable/*` subset to latin
- Radius: `0.5rem` base, with `sm`/`lg` derived

If the preset ships a palette that is demonstrably better than this, this ADR
records the override and the preset's values ship instead. That is a normal
outcome, not a failure of the decision.

## Alternatives considered

- **Defer the identity decision to checkpoint 6 as well.** Rejected: Q91's alias
  layer means the token _structure_ is identical regardless of which palette
  wins, so the identity was never actually waiting on the preset. Deferring
  bought only an open item carried into implementation, against a downside of one
  rewrite of roughly forty lines in the single file designed to isolate exactly
  those values.
- **Skip the preset entirely and hand-configure `components.json`.** Held in
  reserve for the case where the ID is unusable.

## Consequences

- `components.json`'s `css` points at the **alias layer** file, never at
  `tokens.css`. This is what stops a future `npx shadcn@latest add` from reaching
  the palette.
- No network at runtime means fonts must be bundled. A Google Fonts `<link>`
  would fail silently in packaged builds.

## References

Questionnaire Q25, Q26, Q27, Q72, Q91, Q123, Q125. PRD §3, §9 risk 6; Tech.md §3.1, §3.3.
