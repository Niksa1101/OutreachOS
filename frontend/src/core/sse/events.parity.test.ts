/**
 * Q114: the cross-language parity test for the SSE vocabulary.
 *
 * `/events` is excluded from the OpenAPI schema, so nothing generates these
 * types and nothing else would notice the two sides drifting. A renamed event
 * on the Python side produces a client that silently stops reacting — no error,
 * no failed request, just a screen that quietly stops updating.
 *
 * Scoped deliberately to **the set of names and the required envelope keys**.
 * Full payload-shape parity across two languages is where this gets fragile and
 * starts wanting a generator, which is more machinery than two lists deserve.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { ENVELOPE_REQUIRED_KEYS, SERVER_EVENT_NAMES } from '@/core/sse/events';

const EVENTS_PY = fileURLToPath(
  new URL('../../../../backend/src/outreachos_backend/core/events.py', import.meta.url),
);

/** Pull a `NAME: Final = ("a", "b")` tuple out of the Python source. */
function readPythonTuple(source: string, name: string): string[] {
  const match = new RegExp(`^${name}:\\s*Final\\s*=\\s*\\(([^)]*)\\)`, 'm').exec(source);
  if (!match?.[1]) {
    throw new Error(
      `${name} is not declared in events.py as \`${name}: Final = (...)\`. ` +
        'This test reads that literal; if the declaration moved, update both.',
    );
  }

  const body = match[1];
  const literals = [...body.matchAll(/"([^"]+)"/g)].map((entry) => entry[1] as string);
  if (literals.length > 0) {
    return literals;
  }

  // Publishers use named Final constants; EVENT_NAMES may list those names.
  const refs = [...body.matchAll(/\b([A-Z][A-Z0-9_]*)\b/g)].map((entry) => entry[1] as string);
  return refs.map((ref) => {
    const constMatch = new RegExp(`^${ref}:\\s*Final\\s*=\\s*"([^"]+)"`, 'm').exec(source);
    if (!constMatch?.[1]) {
      throw new Error(`Could not resolve ${ref} referenced by ${name} in events.py.`);
    }
    return constMatch[1];
  });
}

describe('SSE vocabulary parity with the backend', () => {
  const source = readFileSync(EVENTS_PY, 'utf8');

  it('declares the same event names as the backend', () => {
    expect([...SERVER_EVENT_NAMES].sort()).toEqual(readPythonTuple(source, 'EVENT_NAMES').sort());
  });

  it('declares the same required envelope keys as the backend', () => {
    expect([...ENVELOPE_REQUIRED_KEYS].sort()).toEqual(
      readPythonTuple(source, 'ENVELOPE_REQUIRED_KEYS').sort(),
    );
  });

  it('still finds the declarations it depends on', () => {
    // If the regex above silently matched nothing, the two tests would compare
    // an empty list against an empty list and pass forever.
    expect(readPythonTuple(source, 'EVENT_NAMES').length).toBeGreaterThan(0);
    expect(readPythonTuple(source, 'ENVELOPE_REQUIRED_KEYS').length).toBeGreaterThan(0);
  });
});
