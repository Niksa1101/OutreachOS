/**
 * The automated guard for Q91's alias layer.
 *
 * Without it, the mapping between our tokens and shadcn's names is verified
 * only by looking at `/dev/tokens` and remembering to.
 *
 * Q108 constrains the technique: **a static parse, not a jsdom
 * `getComputedStyle` check.** jsdom's `var()` chain resolution is unreliable,
 * so that version fails for reasons that have nothing to do with the tokens and
 * you end up debugging the test instead.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const TOKENS = readFileSync(fileURLToPath(new URL('./tokens.css', import.meta.url)), 'utf8');
const ALIASES = readFileSync(
  fileURLToPath(new URL('./shadcn-aliases.css', import.meta.url)),
  'utf8',
);

/** Strip comments so a variable named in prose is not mistaken for a declaration. */
function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '');
}

/** Every `--name:` declaration in a stylesheet. */
function declaredVariables(css: string): Set<string> {
  const names = new Set<string>();
  for (const match of stripComments(css).matchAll(/(--[\w-]+)\s*:/g)) {
    names.add(match[1] as string);
  }
  return names;
}

/** Every `var(--name)` reference in a stylesheet. */
function referencedVariables(css: string): Set<string> {
  const names = new Set<string>();
  for (const match of stripComments(css).matchAll(/var\(\s*(--[\w-]+)/g)) {
    names.add(match[1] as string);
  }
  return names;
}

const tokenNames = declaredVariables(TOKENS);
const aliasNames = declaredVariables(ALIASES);
const allDeclared = new Set([...tokenNames, ...aliasNames]);

/**
 * The names shadcn's components hardcode.
 *
 * Q91: if our tokens do not feed these, every `shadcn add` needs hand-editing
 * forever. This list is the contract.
 */
const SHADCN_REQUIRED = [
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
  '--radius',
  '--sidebar',
  '--sidebar-foreground',
  '--sidebar-primary',
  '--sidebar-primary-foreground',
  '--sidebar-accent',
  '--sidebar-accent-foreground',
  '--sidebar-border',
  '--sidebar-ring',
];

describe('design tokens', () => {
  it('defines every variable shadcn components hardcode', () => {
    const missing = SHADCN_REQUIRED.filter((name) => !allDeclared.has(name));
    expect(missing, `shadcn expects these and nothing defines them: ${missing.join(', ')}`).toEqual(
      [],
    );
  });

  it('resolves every var() the alias layer references', () => {
    // The failure this catches: renaming a token in `tokens.css` and leaving
    // the alias pointing at the old name. CSS does not error on an unresolved
    // `var()`, it computes to nothing — so the component renders transparent
    // and nobody finds out until someone looks at that screen.
    const unresolved = [...referencedVariables(ALIASES)].filter((name) => !allDeclared.has(name));

    expect(unresolved, `alias layer references undefined tokens: ${unresolved.join(', ')}`).toEqual(
      [],
    );
  });

  it('keeps the palette out of the alias layer', () => {
    // Q125: `components.json` points `shadcn add` at the alias file, so it
    // rewrites that one. A literal colour there would be overwritten without
    // warning — and, worse, would mean the palette had a second home.
    const literals = [
      ...stripComments(ALIASES).matchAll(/(#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\()/g),
    ].map((match) => match[0]);

    expect(literals, `move these into tokens.css: ${literals.join(', ')}`).toEqual([]);
  });

  it('defines the semantic tier that the rest of the application uses', () => {
    // Q91's names. Application code references these, never shadcn's.
    for (const name of [
      '--color-bg',
      '--color-bg-subtle',
      '--color-surface',
      '--color-border',
      '--color-fg',
      '--color-fg-muted',
      '--color-accent',
      '--color-danger',
      '--color-warning',
    ]) {
      expect(tokenNames.has(name), `${name} is missing from tokens.css`).toBe(true);
    }
  });

  it('zeroes motion under prefers-reduced-motion', () => {
    // The locked assumption: `--motion-*` tokens zero out, and tokens are the
    // only motion values, so nothing can bypass it.
    const reducedMotionBlock = /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?)\n\}/m;
    const match = reducedMotionBlock.exec(TOKENS);

    expect(match, 'tokens.css has no prefers-reduced-motion block').not.toBeNull();

    const block = match?.[1] ?? '';
    const motionTokens = [...tokenNames].filter((name) => name.startsWith('--motion-'));

    expect(motionTokens.length, 'no --motion-* tokens are defined').toBeGreaterThan(0);

    for (const name of motionTokens) {
      expect(block, `${name} is not overridden under prefers-reduced-motion`).toContain(name);
    }
  });

  it('derives the radius scale from one base value', () => {
    // Q27: 0.5rem base with sm/lg derived. Derived rather than three literals,
    // so changing the base changes the scale instead of two thirds of it.
    expect(TOKENS).toMatch(/--radius:\s*0\.5rem/);
    expect(TOKENS).toMatch(/--radius-sm:\s*calc\(var\(--radius\)/);
    expect(TOKENS).toMatch(/--radius-lg:\s*calc\(var\(--radius\)/);
  });

  it('uses oklch for colour', () => {
    // Q27/Q45. Hover and active states are derived by moving lightness, which
    // only stays perceptually even in a perceptual space.
    const colourTokens = [...stripComments(TOKENS).matchAll(/(--color-[\w-]+)\s*:\s*([^;]+);/g)];
    const nonOklch = colourTokens
      .filter(([, , value]) => !(value as string).includes('oklch'))
      .map(([, name]) => name as string);

    expect(nonOklch, `these are not in oklch: ${nonOklch.join(', ')}`).toEqual([]);
  });
});
