# `core/tokens/`

The single source of every visual value: color, spacing, typography, radius,
elevation, motion.

Two files, deliberately separate:

- `tokens.css` — the semantic tier and the real values (`--color-bg`,
  `--color-accent`, `--motion-fast`, …). This is ours.
- `shadcn-aliases.css` — a thin alias layer mapping shadcn's hardcoded variable
  names (`--background`, `--border`, `--ring`, …) onto the semantic tier.

`components.json` points at the **alias file**, not at `tokens.css`. That is what
stops a future `npx shadcn@latest add` from ever reaching the palette.

Motion durations zero out under `prefers-reduced-motion`. Because tokens are the
only motion values in the application, nothing can bypass that.

Arrives in checkpoint 6, after `shadcn init` — see
`docs/decisions/0001-shadcn-preset-vite.md`.
