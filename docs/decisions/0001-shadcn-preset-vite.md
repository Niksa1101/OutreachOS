# ADR-0001: shadcn preset `b51GFh7y6` against a Vite target

**Status:** Accepted — checkpoint 6.

Reserved at checkpoint 1 so the number stayed stable; it has been referenced as
ADR-0001 since the specification interview.

---

## Context

PRD §3 and Tech.md §3.1 both mandate:

```bash
npx shadcn@latest init --preset b51GFh7y6 --template next --pointer
```

The `--template next` flag names Next.js. This project is Vite + Tauri. PRD §9
lists this as risk #6, to be resolved in P0 with the fallback "keep the preset ID
(it carries the design configuration), adjust only the template target."

The preset ID was opaque at decision time — a short registry identifier whose
contents could not be known offline.

## Decision

**The preset ID was kept. `--template next` was dropped. The preset's token
architecture was adopted; its palette, fonts and icon library were overridden.**

### 1. The template flag

`--template next` scaffolds a _new_ Next.js application: it prompts for a
project name and creates a directory. There is no form of it that targets an
existing tree, so it could not be reconciled — it was dropped and the preset ID
kept, exactly as PRD §9 anticipated.

The command that ran:

```bash
npx shadcn@latest init --preset b51GFh7y6 --yes
```

It requires Tailwind to already be present, which is why Tailwind v4 and
`@tailwindcss/vite` were installed first (Q45).

`--pointer` was also dropped: the current CLI does not accept it.

### 2. What the preset contributed

Committed unedited as its own commit before anything was changed (Q125), so this
is a diff citable by SHA rather than a prose reconstruction that goes stale:

> `build(ui): raw shadcn init --preset b51GFh7y6 output, unedited`

Summarised: style `base-luma`, base colour `mist`, **Phosphor** icons, **Public
Sans**, a **light-first palette with a rose primary**
(`oklch(0.514 0.222 16.935)`), radius `0.625rem`, and a full `@theme inline`
block mapping every shadcn variable name.

Structurally it also revealed that this preset's primitives are built on **Base
UI, not Radix** — `render={<X/>}` where Radix has `asChild`, `delay` where Radix
has `delayDuration`. Worth recording, because every shadcn example on the web
assumes the Radix API.

### 3. What was kept

The **token architecture**: a `@theme inline` block mapping shadcn's variable
names, `--radius` derived into a scale rather than restated, and
`cssVariables: true`. That structure is now `shadcn-aliases.css`, unchanged in
shape.

`@theme inline` specifically — not plain `@theme` — because inline emits `var()`
references rather than copying resolved values, which is what will let a light
theme work by overriding tokens at runtime.

### 4. What was overridden, and why

Q123 gave an explicit escape hatch: _"If the preset ships a palette that is
demonstrably better than this, this ADR records the override and the preset's
values ship instead."_ It does not.

| Aspect   | Preset                         | Shipped                             | Reason                                                                                                                                                 |
| -------- | ------------------------------ | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Scheme   | Light-first                    | **Dark-only**                       | Q27/Q123: dark-only in V1. The preset's `.dark` block is a secondary theme; ours is the only one.                                                      |
| Primary  | Rose `oklch(0.514 0.222 16.9)` | **`oklch(0.58 0.15 255)`**          | Q27 asks for a desaturated blue "that reads as tooling". A rose accent reads as a consumer product; this is a batch render tool that runs for minutes. |
| Neutrals | `mist`                         | **zinc**                            | Q27.                                                                                                                                                   |
| Type     | Public Sans                    | **Inter Variable + JetBrains Mono** | Q27. The preset ships no monospace face, and this application puts ports, paths, `boot_id`s and log tails on screen constantly.                        |
| Icons    | Phosphor                       | **lucide-react**                    | A locked assumption. Not a judgement on Phosphor — a decision already made, and carrying two icon libraries is worse than either.                      |
| Radius   | `0.625rem`                     | **`0.5rem`**                        | Q27.                                                                                                                                                   |

The override cost was what Q123 predicted: one file of CSS, in the file
specifically designed to isolate those values.

### 5. The split that makes this safe

`components.json`'s `css` points at **`shadcn-aliases.css`**, and `tokens.css` is
a separate import owning the values (Q125).

Verified rather than assumed: running `shadcn add sidebar button separator
tooltip` after the split rewrote the alias file and left the palette untouched.

`tokens.test.ts` asserts the split statically — every shadcn-expected variable is
defined, every alias `var()` resolves, and **no literal colour appears in the
alias layer**. Q108 requires a static parse rather than a jsdom
`getComputedStyle` check, because jsdom's `var()` chain resolution is unreliable
enough that the test becomes the thing being debugged.

## Alternatives considered

- **Defer the identity decision to checkpoint 6 as well.** Rejected at Q123:
  Q91's alias layer means the token _structure_ is identical regardless of which
  palette wins, so the identity was never actually waiting on the preset.
- **Skip the preset entirely and hand-configure `components.json`.** Held in
  reserve for the case where the ID was unusable. It resolved, and its
  `@theme inline` structure was worth having.
- **Adopt the preset's palette wholesale.** Rejected on the grounds in the table
  above. It is a coherent palette; it is for a different kind of application.

## Consequences

- Every shadcn example found online uses `asChild` and `delayDuration`. This
  codebase uses `render` and `delay`. The primitives are Base UI.
- `shadcn add` writes into `src/core/components/ui/`, which is generated code.
  ESLint's `react-refresh/only-export-components` is switched off for that
  directory only — an edit made to satisfy it would be overwritten by the next
  `add`.
- Fonts are bundled, not linked. A Google Fonts `<link>` fails silently in a
  packaged build, where there is no network, and the app falls back to a system
  font with nothing reporting it.
- `--accent` means different things on the two sides. shadcn's is a
  hover/highlight surface; ours is the brand colour. The alias maps shadcn's to
  `--color-surface-hover`, and mapping it to `--color-accent` would tint every
  hovered menu row blue.

## References

Questionnaire Q25, Q26, Q27, Q45, Q72, Q91, Q108, Q123, Q125.
PRD §3, §9 risk 6; Tech.md §3.1, §3.3.
