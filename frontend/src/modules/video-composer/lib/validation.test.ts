import { describe, expect, it } from 'vitest';

import type { ValidationIssue } from '@/core/api/types';
import { allWarnings } from '@/modules/video-composer/lib/validation';

describe('allWarnings', () => {
  const issues: ValidationIssue[] = [
    {
      code: 'no_talking_head',
      severity: 'blocking',
      message: 'Assign a talking-head video before generating.',
    },
    {
      code: 'aspect_ratio_not_16_9',
      severity: 'warning',
      message: 'This recording is not 16:9.',
      asset_id: 'rec-1',
    },
    {
      code: 'duplicate_company_name',
      severity: 'warning',
      message: 'Name was auto-suffixed.',
      asset_id: 'rec-2',
    },
  ];

  it('returns every warning regardless of asset scope', () => {
    expect(allWarnings(issues)).toHaveLength(2);
  });

  it('returns an empty list when there are no warnings', () => {
    expect(allWarnings(issues.slice(0, 1))).toEqual([]);
    expect(allWarnings(undefined)).toEqual([]);
  });
});
