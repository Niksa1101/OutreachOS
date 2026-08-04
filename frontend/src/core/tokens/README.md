# `core/tokens/`

The single source of every colour, space, size, and duration in the
application. Tech.md §3.3: **hardcoded colours and spacing values are a review
failure.**

## Two files, and why

| File                 | Holds                                                       |
| -------------------- | ----------------------------------------------------------- |
| `tokens.css`         | The **values**. Semantic names: `--color-bg`, `--space-4`.  |
| `shadcn-aliases.css` | The **mapping** onto shadcn's names. Every value a `var()`. |

`components.json` points its `css` field at **`shadcn-aliases.css`**, never at
`tokens.css`. That is the entire reason they are separate files (Q125):
`npx shadcn@latest add` rewrites the file it is given, so it must be given the
one that holds no palette.

A literal colour appearing in `shadcn-aliases.css` is the bug this split exists
to prevent.

## Why an alias layer at all

Q91: shadcn's components hardcode its own variable names — `--background`,
`--foreground`, `--card`, `--primary`, `--muted`, `--border`, `--ring`. If our
tokens do not feed those, every `shadcn add` needs hand-editing forever. So both
vocabularies exist over one set of values.

One name collides and means something different on each side:
**shadcn's `--accent` is a hover/highlight surface, not a brand colour.** It is
mapped to `--color-surface-hover`. Mapping it to our `--color-accent` would tint
every hovered menu row blue.

## Verifying it

- `/dev/tokens` renders both tiers side by side, so a mismatch is visible rather
  than inferred. Registered behind `import.meta.env.DEV`, so it tree-shakes out
  of a production build.
- `tokens.test.ts` parses the CSS statically and asserts every shadcn-expected
  variable is defined and every alias `var()` resolves. Q108 requires a **static
  parse**, not a jsdom `getComputedStyle` check — jsdom's `var()` chain
  resolution is unreliable and you would end up debugging the test rather than
  the tokens.

## Motion

`--motion-*` are the only duration values in the application. That is what makes
the `prefers-reduced-motion` block in `tokens.css` complete rather than
best-effort: nothing can bypass it, because nothing else names a duration.

They resolve to `0.01ms`, not `0`. A zero-duration transition never fires
`transitionend`, so a component waiting for one would hang instead of degrade.

## Dark-only, light-ready

Q27/Q123: V1 ships dark only. The names carry no lightness (`--color-bg`, not
`--color-zinc-950`), so adding a light theme is a second block in `tokens.css`
plus making the `class="dark"` on `<html>` dynamic. Nothing else changes.

See `docs/decisions/0001-shadcn-preset-vite.md` for what the preset contributed
and what was overridden.
