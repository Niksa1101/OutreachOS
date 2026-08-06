import { AlertTriangle } from 'lucide-react';

import type { ValidationIssue } from '@/core/api/types';

interface Props {
  issues: ValidationIssue[];
}

export function RecordingWarningIndicators({ issues }: Props) {
  if (issues.length === 0) {
    return null;
  }

  return (
    <ul className="mt-1 space-y-1" aria-label="Recording warnings">
      {issues.map((issue) => (
        <li
          key={`${issue.code}-${issue.asset_id ?? 'row'}`}
          className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-300"
        >
          <AlertTriangle aria-hidden className="mt-0.5 size-3 shrink-0" />
          <span>{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}
