/** Human-readable labels for probed media metadata. */

export function formatDurationMs(durationMs: number): string {
  if (!Number.isFinite(durationMs)) {
    return '—';
  }

  const totalSeconds = Math.max(0, Math.round(durationMs / 1000));

  if (totalSeconds >= 3600) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

export function formatResolution(width: number, height: number): string {
  return `${width}×${height}`;
}

export function formatFps(fps: number): string {
  return `${fps.toFixed(fps % 1 === 0 ? 0 : 1)} fps`;
}
