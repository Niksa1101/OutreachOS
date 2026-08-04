/**
 * The honest empty state.
 *
 * A locked assumption: **P0 pages are honest empty states. No fake data, no
 * placeholder charts.** A screenshot of this application should never show a
 * feature that does not exist.
 *
 * Tech.md §3: custom components live in `core/ui/`, composed from shadcn
 * primitives and styled exclusively through tokens.
 */

import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

interface Props {
  icon: LucideIcon;
  title: string;
  /** One or two sentences. What would be here, and what puts it here. */
  description: string;
  /** The action that would populate it, once that action exists. */
  action?: ReactNode;
}

export function EmptyState({ icon: Icon, title, description, action }: Props) {
  return (
    <div className="flex min-h-[24rem] flex-col items-center justify-center gap-3 px-6 text-center">
      <Icon className="size-8 text-muted-foreground/50" aria-hidden />
      <h2 className="text-md font-semibold tracking-tight">{title}</h2>
      <p className="max-w-[42ch] text-sm leading-relaxed text-muted-foreground">{description}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
