import { Link } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { Copy, Pencil, Trash2 } from 'lucide-react';

import { errorMessage } from '@/core/api/error-message';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/core/components/ui/table';
import type { CampaignStatus, CampaignSummary } from '@/core/api/types';
import { InlineError } from '@/core/ui/InlineError';
import { useDuplicateCampaign, useRenameCampaign } from '@/modules/video-composer/api/campaigns';
import { DeleteCampaignDialog } from '@/modules/video-composer/components/DeleteCampaignDialog';

const STATUS_LABELS: Record<CampaignStatus, string> = {
  draft: 'Draft',
  ready: 'Ready',
  blocked: 'Blocked',
  has_rendered: 'Has rendered',
};

function formatLastRendered(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function CampaignNameCell({ campaign }: { campaign: CampaignSummary }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(campaign.name);
  const [renameError, setRenameError] = useState<string | null>(null);
  const rename = useRenameCampaign();

  useEffect(() => {
    setDraft(campaign.name);
  }, [campaign.name]);

  const cancel = () => {
    setDraft(campaign.name);
    setRenameError(null);
    setEditing(false);
  };

  const commit = () => {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === campaign.name) {
      cancel();
      return;
    }

    setRenameError(null);
    rename.mutate(
      { id: campaign.id, name: trimmed },
      {
        onSuccess: () => setEditing(false),
        onError: (error) => setRenameError(errorMessage(error)),
      },
    );
  };

  if (editing) {
    return (
      <div className="min-w-0 space-y-1">
        <Input
          autoFocus
          value={draft}
          aria-label="Campaign name"
          aria-invalid={renameError != null}
          disabled={rename.isPending}
          onChange={(event) => {
            setDraft(event.target.value);
            if (renameError) {
              setRenameError(null);
            }
          }}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              commit();
            }
            if (event.key === 'Escape') {
              event.preventDefault();
              cancel();
            }
          }}
        />
        <InlineError message={renameError} className="text-xs text-destructive" />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <Link
        to="/video-composer/campaigns/$campaignId"
        params={{ campaignId: campaign.id }}
        className="min-w-0 flex-1 rounded-lg px-1 py-0.5 text-left font-medium hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
      >
        {campaign.name}
      </Link>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={`Rename ${campaign.name}`}
        onClick={() => setEditing(true)}
      >
        <Pencil aria-hidden />
      </Button>
    </div>
  );
}

interface Props {
  campaigns: CampaignSummary[];
}

function CampaignActionsCell({ campaign }: { campaign: CampaignSummary }) {
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);
  const duplicate = useDuplicateCampaign();

  return (
    <>
      <div className="flex flex-col items-end gap-1">
        <div className="flex items-center justify-end gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Duplicate ${campaign.name}`}
            disabled={duplicate.isPending}
            onClick={() => {
              setDuplicateError(null);
              duplicate.mutate(campaign.id, {
                onError: (error) => setDuplicateError(errorMessage(error)),
              });
            }}
          >
            <Copy aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Delete ${campaign.name}`}
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 aria-hidden />
          </Button>
        </div>
        <InlineError
          message={duplicateError}
          className="max-w-48 text-right text-xs text-destructive"
        />
      </div>
      <DeleteCampaignDialog
        campaignId={campaign.id}
        campaignName={campaign.name}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
    </>
  );
}

export function CampaignsTable({ campaigns }: Props) {
  return (
    <div className="mt-6 overflow-hidden rounded-2xl border border-border">
      <Table>
        <TableHeader>
          <TableRow className="border-b border-border bg-muted/40 hover:bg-muted/40">
            <TableHead className="px-4 py-3 font-medium text-muted-foreground">Name</TableHead>
            <TableHead className="px-4 py-3 font-medium text-muted-foreground">
              Recordings
            </TableHead>
            <TableHead className="px-4 py-3 font-medium text-muted-foreground">
              Last rendered
            </TableHead>
            <TableHead className="px-4 py-3 font-medium text-muted-foreground">Status</TableHead>
            <TableHead className="px-4 py-3 font-medium text-muted-foreground">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {campaigns.map((campaign) => (
            <TableRow key={campaign.id} className="border-b border-border last:border-0">
              <TableCell className="px-4 py-3 whitespace-normal">
                <CampaignNameCell campaign={campaign} />
              </TableCell>
              <TableCell className="px-4 py-3 tabular-nums text-muted-foreground">
                {campaign.recording_count}
              </TableCell>
              <TableCell className="px-4 py-3 text-muted-foreground">
                {formatLastRendered(campaign.last_rendered_at)}
              </TableCell>
              <TableCell className="px-4 py-3 text-muted-foreground">
                {STATUS_LABELS[campaign.status]}
              </TableCell>
              <TableCell className="px-4 py-3 text-right">
                <CampaignActionsCell campaign={campaign} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
