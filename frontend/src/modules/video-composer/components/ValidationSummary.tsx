import { AlertTriangle } from 'lucide-react';

import type { CampaignValidation } from '@/core/api/types';
import { allWarnings } from '@/modules/video-composer/lib/validation';

interface Props {
  validation: CampaignValidation;
}

export function ValidationSummary({ validation }: Props) {
  const warnings = allWarnings(validation.issues);

  if (warnings.length === 0) {
    return null;
  }

  return (
    <section
      className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3"
      aria-live="polite"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-amber-600" />
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-medium text-amber-950 dark:text-amber-100">
            {warnings.length === 1
              ? '1 warning before generating'
              : `${warnings.length} warnings before generating`}
          </p>
          <ul className="list-inside list-disc text-sm text-amber-950/80 dark:text-amber-100/80">
            {warnings.map((issue) => (
              <li key={`${issue.code}-${issue.asset_id ?? 'campaign'}`}>{issue.message}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
