#!/usr/bin/env node
/**
 * Generate `frontend/src/core/api/schema.d.ts` from the backend's OpenAPI spec.
 *
 * Tech.md §4.4: Pydantic models are the single source of truth; TypeScript
 * interfaces are never hand-maintained.
 *
 * Q89 settles *how* the spec is obtained, and the answer is not "from a running
 * server". `app.openapi()` produces it in-process in about a second, with no
 * port to bind and no workspace to pick — which is what makes the CI staleness
 * check a plain command rather than a fixture that has to boot a sidecar.
 *
 * Usage:
 *   node scripts/gen-api-types.mjs           write the file
 *   node scripts/gen-api-types.mjs --check   fail if it is stale (CI)
 */

import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUTPUT = join(REPO_ROOT, 'frontend', 'src', 'core', 'api', 'schema.d.ts');
const CHECK_ONLY = process.argv.includes('--check');

const BANNER = `/**
 * Generated from the backend's OpenAPI schema. Do not edit.
 *
 * Regenerate with \`pnpm gen-api-types\` whenever a Pydantic model changes.
 * CI fails if this file has drifted, so a forgotten regeneration is caught at
 * the pull request rather than at runtime.
 */
`;

function run(command, args, options = {}) {
  return execFileSync(command, args, {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    maxBuffer: 32 * 1024 * 1024,
    ...options,
  });
}

// `execFile` does not apply PATHEXT, so a bare `uv` is not found on Windows
// even though the shell resolves it. Naming the extension is cheaper than
// enabling `shell: true`, which would then need the Python one-liner below to
// survive shell quoting on two platforms.
const UV = process.platform === 'win32' ? 'uv.exe' : 'uv';

/** Dump the spec without booting a server (Q89). */
function readSpec() {
  const script =
    'import json, sys; ' +
    'from outreachos_backend.main import app; ' +
    'sys.stdout.write(json.dumps(app.openapi()))';

  return run(UV, ['run', '--directory', 'backend', 'python', '-c', script]);
}

function generate(spec) {
  // The installed CLI, invoked through `node` directly rather than through
  // `npx`: a pinned devDependency cannot drift mid-review, and `npx` would
  // resolve a `.cmd` shim that `execFile` cannot launch on Windows.
  const cli = join(REPO_ROOT, 'node_modules', 'openapi-typescript', 'bin', 'cli.js');

  // Via a temp file rather than stdin. v7 treats its positional argument as a
  // path or URL and has no stdin mode, so `-` is read as a filename.
  const specFile = join(tmpdir(), `outreachos-openapi-${process.pid}.json`);
  writeFileSync(specFile, spec, 'utf8');

  try {
    return BANNER + run(process.execPath, [cli, specFile]);
  } finally {
    rmSync(specFile, { force: true });
  }
}

const generated = generate(readSpec());

if (CHECK_ONLY) {
  let existing = '';
  try {
    existing = readFileSync(OUTPUT, 'utf8');
  } catch {
    console.error('gen-api-types: schema.d.ts is missing. Run `pnpm gen-api-types`.');
    process.exit(1);
  }

  if (existing !== generated) {
    console.error(
      'gen-api-types: schema.d.ts is stale. Run `pnpm gen-api-types` and commit the result.',
    );
    process.exit(1);
  }

  console.log('gen-api-types: schema.d.ts is current');
} else {
  mkdirSync(dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, generated, 'utf8');
  console.log(`gen-api-types: wrote ${OUTPUT}`);
}
