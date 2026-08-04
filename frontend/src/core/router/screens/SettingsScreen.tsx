/**
 * Settings.
 *
 * Q90: read-only in P0 — workspace path, versions, `boot_id`, migration head,
 * log path. **No "Change workspace"**; that is P5, and shipping the button
 * before the kill-and-respawn path exists would be a dead control on the one
 * screen users go looking for it.
 *
 * This is the first screen reading live data through the generated client, and
 * therefore the proof that Q89's type pipeline actually closes: Pydantic model
 * → OpenAPI → `schema.d.ts` → this file, with nothing hand-maintained in
 * between.
 */

import { useQuery } from '@tanstack/react-query';

import { settingsQuery } from '@/core/api/queries';
import { BORDER, mono, pane, paneSurface } from '@/core/layout/bootStyles';

export function SettingsScreen() {
  const { data, error, isPending } = useQuery(settingsQuery);

  return (
    <main style={paneSurface}>
      <div style={pane}>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 600, margin: 0 }}>Settings</h1>

        {isPending ? <p style={{ margin: 0, opacity: 0.6 }}>Loading…</p> : null}

        {error ? (
          <p style={{ ...mono, color: '#f87171', margin: 0 }} role="alert">
            {error.message}
          </p>
        ) : null}

        {data ? (
          <>
            <Section title="Workspace">
              <Row label="Path" value={data.workspace_path} />
              <Row label="Database revision" value={data.migration_head ?? '—'} />
              <Row label="Log" value={data.backend_log_path} />
            </Section>

            <Section title="Rendering">
              <Row label="Quality preset" value={data.quality_preset} />
              {/* NULL means auto-detect (Tech.md §5.2: NVENC → QSV → AMF →
                  libx264). Rendering it as "Auto-detect" rather than as an
                  empty cell is the difference between "not set" and "broken". */}
              <Row label="Encoder" value={data.encoder_override ?? 'Auto-detect'} />
              <Row label="FFmpeg" value={data.ffmpeg_version ?? 'Not probed yet'} />
            </Section>

            <Section title="Build">
              <Row label="Application" value={data.app_version ?? '—'} />
              <Row label="Backend" value={data.backend_version} />
              <Row label="Boot" value={data.boot_id} />
            </Section>
          </>
        ) : null}
      </div>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ display: 'grid', gap: '0.5rem' }}>
      <h2
        style={{
          fontSize: '0.75rem',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          opacity: 0.5,
          margin: 0,
          borderBottom: `1px solid ${BORDER}`,
          paddingBottom: '0.5rem',
        }}
      >
        {title}
      </h2>
      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'max-content 1fr',
          gap: '0.375rem 1.5rem',
          margin: 0,
        }}
      >
        {children}
      </dl>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt style={{ fontSize: '0.875rem', opacity: 0.6 }}>{label}</dt>
      <dd style={{ ...mono, margin: 0, wordBreak: 'break-all' }}>{value}</dd>
    </>
  );
}
