/**
 * Composition root for the application shell.
 *
 * Checkpoint 1 placeholder. This becomes the boot gate in checkpoint 4
 * (no workspace -> /setup, unhealthy backend -> /diagnostics) and the sidebar
 * shell in checkpoint 6. It renders no styling of its own on purpose — design
 * tokens do not exist until checkpoint 6, and hardcoded values are a review
 * failure per PRD §4.
 */
export function AppRoot() {
  return (
    <main>
      <h1>OutreachOS</h1>
      <p>Checkpoint 1 — project skeleton. No features yet.</p>
    </main>
  );
}
