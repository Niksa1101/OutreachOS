import { describe, expect, it } from 'vitest';

import {
  describeExportConfirmation,
  describeExportableCount,
  describeExportResult,
  describeStagedOutputs,
} from '@/modules/video-composer/lib/export';

describe('describeExportableCount', () => {
  it('describes zero, one, and many', () => {
    expect(describeExportableCount(0)).toContain('No completed renders');
    expect(describeExportableCount(1)).toContain('1 completed render');
    expect(describeExportableCount(3)).toContain('3 completed renders');
  });
});

describe('describeExportConfirmation', () => {
  it('states file count and destination', () => {
    expect(describeExportConfirmation(2, 'D:/Exports')).toContain('2 files will move');
    expect(describeExportConfirmation(2, 'D:/Exports')).toContain('D:/Exports');
  });
});

describe('describeStagedOutputs', () => {
  it('describes empty and non-empty staging', () => {
    expect(describeStagedOutputs(0, 0)).toContain('No un-exported');
    expect(describeStagedOutputs(2, 2048)).toContain('2 un-exported renders');
  });
});

describe('describeExportResult', () => {
  it('summarizes moved files, conflicts, and failures', () => {
    expect(describeExportResult(0, [])).toContain('Nothing was exported');
    expect(describeExportResult(2, [])).toContain('2 files exported');
    expect(describeExportResult(1, ['Acme.mp4'])).toContain('Acme.mp4');
    expect(
      describeExportResult(0, [], [{ filename: 'Beta.mp4', reason: 'disk full' }]),
    ).toContain('Beta.mp4');
  });
});
