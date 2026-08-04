/**
 * `/dev/tokens` — both token tiers, and every shadcn primitive.
 *
 * Q91: rendering **both** vocabularies is the point. The alias layer maps
 * shadcn's names onto ours, and a mismatch there is otherwise invisible until
 * some component renders the wrong colour weeks later. Here the two sit next to
 * each other, so a broken alias is a visibly missing swatch.
 *
 * `tokens.test.ts` is the automated half of the same guarantee; this is the
 * half that catches "the alias resolves, but to the wrong thing".
 *
 * Registered behind `import.meta.env.DEV`, so it tree-shakes out of a
 * production build entirely (Q91).
 */

import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Separator } from '@/core/components/ui/separator';
import { Skeleton } from '@/core/components/ui/skeleton';

/** The semantic tier — ours, from `tokens.css`. */
const SEMANTIC_COLORS = [
  '--color-bg',
  '--color-bg-subtle',
  '--color-surface',
  '--color-surface-hover',
  '--color-border',
  '--color-border-strong',
  '--color-fg',
  '--color-fg-muted',
  '--color-fg-subtle',
  '--color-accent',
  '--color-accent-hover',
  '--color-accent-active',
  '--color-danger',
  '--color-warning',
  '--color-success',
  '--color-focus-ring',
];

/** shadcn's tier — the alias layer. Every one of these must resolve. */
const ALIAS_COLORS = [
  '--background',
  '--foreground',
  '--card',
  '--card-foreground',
  '--popover',
  '--popover-foreground',
  '--primary',
  '--primary-foreground',
  '--secondary',
  '--secondary-foreground',
  '--muted',
  '--muted-foreground',
  '--accent',
  '--accent-foreground',
  '--destructive',
  '--border',
  '--input',
  '--ring',
  '--sidebar',
  '--sidebar-foreground',
  '--sidebar-primary',
  '--sidebar-accent',
  '--sidebar-border',
  '--sidebar-ring',
];

const SPACING = ['--space-1', '--space-2', '--space-3', '--space-4', '--space-6', '--space-8'];
const RADII = ['--radius-sm', '--radius', '--radius-lg'];
const MOTION = ['--motion-fast', '--motion-base', '--motion-slow'];

export function DevTokensScreen() {
  return (
    <div className="mx-auto grid max-w-4xl gap-8 p-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Design tokens</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Both tiers. A blank or black swatch in the second group means an alias does not resolve.
        </p>
      </header>

      <Swatches title="Semantic tier (tokens.css)" names={SEMANTIC_COLORS} />
      <Swatches title="shadcn alias tier (shadcn-aliases.css)" names={ALIAS_COLORS} />

      <Group title="Typography">
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: 'var(--text-xl)' }}>
          Inter Variable — 1234567890
        </p>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-base)' }}>
          JetBrains Mono — 127.0.0.1:56721
        </p>
        <p className="text-xs text-muted-foreground">
          Both self-hosted and subset to latin. If either falls back to a system font here, the
          packaged build will do the same silently.
        </p>
      </Group>

      <Group title="Spacing">
        <div className="flex items-end gap-2">
          {SPACING.map((name) => (
            <div key={name} className="grid gap-1 text-center">
              <div
                style={{ width: `var(${name})`, height: `var(${name})` }}
                className="bg-primary"
              />
              <code className="text-[0.625rem] text-muted-foreground">{name.slice(8)}</code>
            </div>
          ))}
        </div>
      </Group>

      <Group title="Radius">
        <div className="flex gap-3">
          {RADII.map((name) => (
            <div key={name} className="grid gap-1 text-center">
              <div style={{ borderRadius: `var(${name})` }} className="size-14 border bg-card" />
              <code className="text-[0.625rem] text-muted-foreground">{name}</code>
            </div>
          ))}
        </div>
      </Group>

      <Group title="Motion">
        <p className="text-xs text-muted-foreground">
          Hover a square. Under <code>prefers-reduced-motion</code> all three resolve to 0.01ms —
          tokens are the only motion values, so nothing can bypass that.
        </p>
        <div className="flex gap-3">
          {MOTION.map((name) => (
            <div key={name} className="grid gap-1 text-center">
              <div
                className="size-14 rounded-md bg-secondary transition-colors hover:bg-primary"
                style={{ transitionDuration: `var(${name})` }}
              />
              <code className="text-[0.625rem] text-muted-foreground">{name}</code>
            </div>
          ))}
        </div>
      </Group>

      <Group title="Primitives">
        <div className="flex flex-wrap items-center gap-2">
          <Button>Default</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="link">Link</Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm">Small</Button>
          <Button size="lg">Large</Button>
          <Button disabled>Disabled</Button>
        </div>
        <Input placeholder="An input" className="max-w-sm" />
        <Separator />
        <div className="flex gap-2">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-8 w-20" />
        </div>
      </Group>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Swatches({ title, names }: { title: string; names: string[] }) {
  return (
    <Group title={title}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {names.map((name) => (
          <div key={name} className="grid gap-1">
            <div
              className="h-10 rounded-md border"
              style={{ backgroundColor: `var(${name})` }}
              title={name}
            />
            <code className="truncate text-[0.625rem] text-muted-foreground">{name}</code>
          </div>
        ))}
      </div>
    </Group>
  );
}
