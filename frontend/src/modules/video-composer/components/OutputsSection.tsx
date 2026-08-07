import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FolderOutput } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { Skeleton } from '@/core/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/core/components/ui/table';
import { EmptyState } from '@/core/ui/EmptyState';
import { campaignOutputsQuery } from '@/modules/video-composer/api/export';
import { ExportAllDialog } from '@/modules/video-composer/components/ExportAllDialog';
import { formatBytes } from '@/core/lib/format';
import { describeStagedOutputs } from '@/modules/video-composer/lib/export';

interface Props {
  campaignId: string;
  exportNotice?: string | null;
  onExportNotice?: (notice: string | null) => void;
}

export function OutputsSection({ campaignId, exportNotice, onExportNotice }: Props) {
  const [exportOpen, setExportOpen] = useState(false);
  const outputs = useQuery(campaignOutputsQuery(campaignId));

  const count = outputs.data?.outputs?.length ?? 0;
  const exportableCount = outputs.data?.exportable_count ?? 0;

  return (
    <section>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Outputs</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Finished videos staged in the workspace until you export them.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={outputs.isPending || exportableCount === 0}
          onClick={() => {
            onExportNotice?.(null);
            setExportOpen(true);
          }}
        >
          Export All
        </Button>
      </div>

      {exportNotice ? (
        <p className="mt-3 text-sm text-muted-foreground" role="status">
          {exportNotice}
        </p>
      ) : null}

      <ExportAllDialog
        campaignId={campaignId}
        open={exportOpen}
        onOpenChange={setExportOpen}
        {...(onExportNotice ? { onExported: onExportNotice } : {})}
      />

      <div className="mt-4">
        {outputs.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : outputs.isError ? (
          <p className="text-sm text-destructive">Could not load staged outputs.</p>
        ) : count === 0 ? (
          <EmptyState
            icon={FolderOutput}
            title="No staged outputs"
            description="Completed renders appear here until you export them."
          />
        ) : (
          <>
            <p className="mb-3 text-sm text-muted-foreground">
              {describeStagedOutputs(count, outputs.data?.total_size_bytes ?? 0)}
            </p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Filename</TableHead>
                  <TableHead className="w-28 text-right">Size</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(outputs.data?.outputs ?? []).map((item) => (
                  <TableRow key={item.filename}>
                    <TableCell className="font-mono text-xs">{item.filename}</TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {formatBytes(item.size_bytes)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </div>
    </section>
  );
}
