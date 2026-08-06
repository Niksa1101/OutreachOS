import type { ValidationIssue } from '@/core/api/types';

function issuesForAsset(issues: ValidationIssue[] | undefined, assetId: string): ValidationIssue[] {
  return (issues ?? []).filter((issue) => issue.asset_id === assetId);
}

export function warningIssuesForAsset(
  issues: ValidationIssue[] | undefined,
  assetId: string,
): ValidationIssue[] {
  return issuesForAsset(issues, assetId).filter((issue) => issue.severity === 'warning');
}

export function allWarnings(issues: ValidationIssue[] | undefined): ValidationIssue[] {
  return (issues ?? []).filter((issue) => issue.severity === 'warning');
}
