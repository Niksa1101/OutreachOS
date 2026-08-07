import { describe, expect, it } from 'vitest';

import {
  formatBatchCompletionSummary,
  formatBatchCounts,
  formatEta,
} from '@/modules/video-composer/lib/batch-progress';

describe('formatEta', () => {
  it('shows a calm placeholder before throughput exists', () => {
    expect(formatEta(null)).toBe('Estimating…');
  });

  it('formats short and long remaining times', () => {
    expect(formatEta(0)).toBe('Done');
    expect(formatEta(45)).toBe('~45s left');
    expect(formatEta(90)).toBe('~1m 30s left');
    expect(formatEta(120)).toBe('~2m left');
    expect(formatEta(3600)).toBe('~1h left');
    expect(formatEta(3660)).toBe('~1h 1m left');
  });
});

describe('formatBatchCounts', () => {
  it('surfaces failures without making the user do arithmetic', () => {
    expect(formatBatchCounts({ completed: 28, failed: 2, total: 30 })).toBe(
      '30 of 30 · 2 failed',
    );
    expect(formatBatchCounts({ completed: 3, failed: 0, total: 10 })).toBe('3 of 10');
  });
});

describe('formatBatchCompletionSummary', () => {
  it('matches the PRD end-of-batch phrasing', () => {
    expect(formatBatchCompletionSummary({ completed: 28, failed: 2 })).toBe(
      '28 completed, 2 failed',
    );
    expect(formatBatchCompletionSummary({ completed: 5, failed: 0 })).toBe(
      '5 completed — queue idle.',
    );
  });
});
