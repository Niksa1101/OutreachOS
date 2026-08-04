#!/usr/bin/env node
/**
 * Propagate the authoritative version from the root package.json.
 *
 * The root package.json is the single source of truth (Q97-B'):
 *   - `pnpm version <major|minor|patch>` bumps and git-tags in one command,
 *     which no other candidate file offers.
 *   - tauri.conf.json reads `"version": "../package.json"` natively and needs
 *     no syncing at all.
 *
 * So this script has exactly two targets, plus Cargo.toml which arrives with
 * the Tauri shell in checkpoint 2.
 *
 * Usage:
 *   node scripts/sync-version.mjs           write the version into every target
 *   node scripts/sync-version.mjs --check   fail if any target has drifted (CI)
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CHECK_ONLY = process.argv.includes('--check');
const SEMVER = /^\d+\.\d+\.\d+$/;

/** @type {{ file: string, pattern: RegExp, label: string }[]} */
const TARGETS = [
  {
    file: 'backend/pyproject.toml',
    // The `version` key inside [project] specifically — never `target-version`
    // (ruff) or `python_version` (mypy), which also live in this file.
    pattern: /(\[project\][\s\S]*?\nversion\s*=\s*")([^"]+)(")/,
    label: '[project].version',
  },
  {
    file: 'backend/src/outreachos_backend/_version.py',
    pattern: /(__version__\s*=\s*")([^"]+)(")/,
    label: '__version__',
  },
  {
    file: 'src-tauri/Cargo.toml',
    // Scoped to [package] so a dependency's own `version = "..."` is never hit.
    pattern: /(\[package\][\s\S]*?\nversion\s*=\s*")([^"]+)(")/,
    label: '[package].version',
  },
];

function fail(message) {
  console.error(`sync-version: ${message}`);
  process.exit(1);
}

const rootPackagePath = join(REPO_ROOT, 'package.json');
const version = JSON.parse(readFileSync(rootPackagePath, 'utf8')).version;

if (typeof version !== 'string' || !SEMVER.test(version)) {
  fail(`root package.json version is not a plain semver string: ${JSON.stringify(version)}`);
}

let drifted = 0;
let updated = 0;

for (const target of TARGETS) {
  const absolute = join(REPO_ROOT, target.file);

  if (!existsSync(absolute)) {
    // Cargo.toml does not exist until checkpoint 2. Say so rather than
    // passing silently — a target that vanishes should be visible.
    console.warn(`sync-version: skipping ${target.file} (not present yet)`);
    continue;
  }

  const original = readFileSync(absolute, 'utf8');
  const match = original.match(target.pattern);

  if (!match) {
    fail(`could not find ${target.label} in ${target.file}`);
  }

  const current = match[2];
  if (current === version) {
    continue;
  }

  if (CHECK_ONLY) {
    console.error(`sync-version: ${target.file} has ${current}, expected ${version}`);
    drifted += 1;
    continue;
  }

  writeFileSync(absolute, original.replace(target.pattern, `$1${version}$3`), 'utf8');
  console.log(`sync-version: ${target.file}  ${current} -> ${version}`);
  updated += 1;
}

if (CHECK_ONLY) {
  if (drifted > 0) {
    fail(`${drifted} file(s) drifted from the authoritative version. Run \`pnpm sync-version\`.`);
  }
  console.log(`sync-version: all targets at ${version}`);
} else {
  console.log(
    updated > 0
      ? `sync-version: ${updated} file(s) updated`
      : `sync-version: already at ${version}`,
  );
}
