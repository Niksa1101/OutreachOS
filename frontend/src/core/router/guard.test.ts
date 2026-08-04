import { describe, expect, it } from 'vitest';

import { DIAGNOSTICS_PATH, HOME_PATH, SETUP_PATH, resolveGate } from '@/core/router/guard';

describe('resolveGate', () => {
  it('sends a first run to the picker', () => {
    expect(resolveGate('awaiting_workspace', HOME_PATH, HOME_PATH)).toBe(SETUP_PATH);
  });

  it('leaves the picker alone once it is showing', () => {
    // Returning a target unconditionally would make every navigation a
    // redirect and defeat the router's own history handling.
    expect(resolveGate('awaiting_workspace', SETUP_PATH, HOME_PATH)).toBeNull();
  });

  it('sends a failed boot to diagnostics from anywhere', () => {
    expect(resolveGate('failed', HOME_PATH, HOME_PATH)).toBe(DIAGNOSTICS_PATH);
    expect(resolveGate('failed', SETUP_PATH, HOME_PATH)).toBe(DIAGNOSTICS_PATH);
  });

  it('leaves diagnostics alone once it is showing', () => {
    expect(resolveGate('failed', DIAGNOSTICS_PATH, HOME_PATH)).toBeNull();
  });

  it('returns to the remembered route when a retry succeeds', () => {
    // Q78: Retry re-runs the whole boot machine, and on success the user
    // should land back where they were rather than at the home route.
    expect(resolveGate('ready', DIAGNOSTICS_PATH, '/video-composer/campaigns')).toBe(
      '/video-composer/campaigns',
    );
  });

  it('falls back to home when the remembered route is itself a gate', () => {
    // First run: the user has never been anywhere but /setup, so there is no
    // meaningful route to return to.
    expect(resolveGate('ready', SETUP_PATH, SETUP_PATH)).toBe(HOME_PATH);
    expect(resolveGate('ready', DIAGNOSTICS_PATH, DIAGNOSTICS_PATH)).toBe(HOME_PATH);
  });

  it('does not redirect a healthy app that is already on a real route', () => {
    expect(resolveGate('ready', '/video-composer/campaigns', '/anything')).toBeNull();
  });

  it('leaves navigation alone while the boot is still in progress', () => {
    // The boot screen renders in place of the route tree during these phases.
    // Redirecting would rewrite the URL the user came back to before the app
    // knows whether it can honour it.
    for (const path of [HOME_PATH, SETUP_PATH, DIAGNOSTICS_PATH, '/video-composer']) {
      expect(resolveGate('starting', path, HOME_PATH)).toBeNull();
      expect(resolveGate('starting_backend', path, HOME_PATH)).toBeNull();
    }
  });

  it('sends a workspace that goes missing mid-session to diagnostics, not the picker', () => {
    // The distinction matters: diagnostics carries "Forget this workspace"
    // (Q40), and the picker alone would leave the stale pointer in place.
    expect(resolveGate('failed', '/video-composer/campaigns', HOME_PATH)).toBe(DIAGNOSTICS_PATH);
  });
});
