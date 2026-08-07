import { useEffect, useState } from 'react';

import { Input } from '@/core/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/core/components/ui/select';
import { Slider } from '@/core/components/ui/slider';
import { Switch } from '@/core/components/ui/switch';
import {
  clampOverlayConfig,
  clampOverlayPadding,
  DEFAULT_CANVAS,
  type Anchor,
  type OverlayConfig,
  type Shape,
} from '@/modules/video-composer/lib/overlay-geometry';
import { sliderValueAt } from '@/modules/video-composer/lib/slider-value';

interface Props {
  overlay: OverlayConfig;
  onChange: (overlay: OverlayConfig) => void;
  onCommit: (overlay: OverlayConfig) => void;
  /** Ticket 21: read-only while the campaign has queued/active render jobs. */
  locked?: boolean;
}

const ANCHOR_LABELS: Record<Anchor, string> = {
  top_left: 'Top left',
  top_right: 'Top right',
  bottom_left: 'Bottom left',
  bottom_right: 'Bottom right',
};

const SHAPE_LABELS: Record<Shape, string> = {
  circle: 'Circle',
  rounded_rect: 'Rounded rectangle',
  rect: 'Rectangle',
};

const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;

/**
 * The full overlay property set (ticket 12): anchor/size/offset (ticket 11),
 * shape/opacity/border/shadow/background/padding/animation duration (ticket
 * 12). Every field commits through `clampOverlayConfig` so a typed or pasted
 * out-of-range value clamps visibly — the field redraws with the clamped
 * number — rather than being silently rejected.
 */
export function OverlayGeometryForm({ overlay, onChange, onCommit, locked = false }: Props) {
  /** Live draft only — for continuous input (slider drag, color-picker drag). */
  function changeField(next: OverlayConfig) {
    if (locked) return;
    onChange(clampOverlayConfig(next));
  }

  /** Draft + persist — for a released/finalized value. */
  function commitField(next: OverlayConfig) {
    if (locked) return;
    const clamped = clampOverlayConfig(next);
    onChange(clamped);
    onCommit(clamped);
  }

  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-4">
      <Field label="Anchor" className="col-span-2">
        <Select
          value={overlay.anchor}
          disabled={locked}
          onValueChange={(value) => commitField({ ...overlay, anchor: value as Anchor })}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(ANCHOR_LABELS) as Anchor[]).map((anchor) => (
              <SelectItem key={anchor} value={anchor}>
                {ANCHOR_LABELS[anchor]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <NumberField
        label="Width"
        value={overlay.size.width}
        min={1}
        max={DEFAULT_CANVAS.width}
        disabled={locked}
        onCommit={(width) => commitField({ ...overlay, size: { ...overlay.size, width } })}
      />
      <NumberField
        label="Height"
        value={overlay.size.height}
        min={1}
        max={DEFAULT_CANVAS.height}
        disabled={locked}
        onCommit={(height) => commitField({ ...overlay, size: { ...overlay.size, height } })}
      />
      <NumberField
        label="X offset"
        value={overlay.offset.x}
        min={0}
        max={DEFAULT_CANVAS.width}
        disabled={locked}
        onCommit={(x) => commitField({ ...overlay, offset: { ...overlay.offset, x } })}
      />
      <NumberField
        label="Y offset"
        value={overlay.offset.y}
        min={0}
        max={DEFAULT_CANVAS.height}
        disabled={locked}
        onCommit={(y) => commitField({ ...overlay, offset: { ...overlay.offset, y } })}
      />

      <SectionHeading>Shape</SectionHeading>

      <Field label="Shape" className="col-span-2">
        <Select
          value={overlay.shape}
          disabled={locked}
          onValueChange={(value) => commitField({ ...overlay, shape: value as Shape })}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(SHAPE_LABELS) as Shape[]).map((shape) => (
              <SelectItem key={shape} value={shape}>
                {SHAPE_LABELS[shape]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <NumberField
        label="Border radius"
        value={overlay.border_radius}
        min={0}
        max={Math.min(overlay.size.width, overlay.size.height) / 2}
        disabled={locked || overlay.shape !== 'rounded_rect'}
        onCommit={(border_radius) => commitField({ ...overlay, border_radius })}
      />
      <SliderField
        label="Opacity"
        value={overlay.opacity}
        min={0}
        max={1}
        step={0.01}
        disabled={locked}
        onChange={(opacity) => changeField({ ...overlay, opacity })}
        onCommit={(opacity) => commitField({ ...overlay, opacity })}
      />

      <SectionHeading>Style</SectionHeading>

      <Field label="Border" className="col-span-2 flex-row items-center justify-between">
        <Switch
          checked={overlay.border.enabled}
          disabled={locked}
          onCheckedChange={(enabled) =>
            commitField({ ...overlay, border: { ...overlay.border, enabled } })
          }
        />
      </Field>
      <NumberField
        label="Border width"
        value={overlay.border.width}
        min={0}
        max={64}
        disabled={locked || !overlay.border.enabled}
        onCommit={(width) => commitField({ ...overlay, border: { ...overlay.border, width } })}
      />
      <ColorField
        label="Border color"
        value={overlay.border.color}
        disabled={locked || !overlay.border.enabled}
        onChange={(color) => changeField({ ...overlay, border: { ...overlay.border, color } })}
        onCommit={(color) => commitField({ ...overlay, border: { ...overlay.border, color } })}
      />

      <Field label="Shadow" className="col-span-2 flex-row items-center justify-between">
        <Switch
          checked={overlay.shadow.enabled}
          disabled={locked}
          onCheckedChange={(enabled) =>
            commitField({ ...overlay, shadow: { ...overlay.shadow, enabled } })
          }
        />
      </Field>
      <NumberField
        label="Shadow blur"
        value={overlay.shadow.blur}
        min={0}
        max={128}
        disabled={locked || !overlay.shadow.enabled}
        onCommit={(blur) => commitField({ ...overlay, shadow: { ...overlay.shadow, blur } })}
      />
      <SliderField
        label="Shadow opacity"
        value={overlay.shadow.opacity}
        min={0}
        max={1}
        step={0.01}
        disabled={locked || !overlay.shadow.enabled}
        onChange={(opacity) => changeField({ ...overlay, shadow: { ...overlay.shadow, opacity } })}
        onCommit={(opacity) => commitField({ ...overlay, shadow: { ...overlay.shadow, opacity } })}
      />
      <NumberField
        label="Shadow offset X"
        value={overlay.shadow.offset_x}
        min={-128}
        max={128}
        disabled={locked || !overlay.shadow.enabled}
        onCommit={(offset_x) =>
          commitField({ ...overlay, shadow: { ...overlay.shadow, offset_x } })
        }
      />
      <NumberField
        label="Shadow offset Y"
        value={overlay.shadow.offset_y}
        min={-128}
        max={128}
        disabled={locked || !overlay.shadow.enabled}
        onCommit={(offset_y) =>
          commitField({ ...overlay, shadow: { ...overlay.shadow, offset_y } })
        }
      />
      <ColorField
        label="Shadow color"
        value={overlay.shadow.color}
        disabled={locked || !overlay.shadow.enabled}
        className="col-span-2"
        onChange={(color) => changeField({ ...overlay, shadow: { ...overlay.shadow, color } })}
        onCommit={(color) => commitField({ ...overlay, shadow: { ...overlay.shadow, color } })}
      />

      <Field label="Background" className="col-span-2 flex-row items-center justify-between">
        <Switch
          checked={overlay.background.enabled}
          disabled={locked}
          onCheckedChange={(enabled) =>
            commitField({
              ...overlay,
              background: { ...overlay.background, enabled },
            })
          }
        />
      </Field>
      <ColorField
        label="Background color"
        value={overlay.background.color}
        disabled={locked || !overlay.background.enabled}
        className="col-span-2"
        onChange={(color) =>
          changeField({ ...overlay, background: { ...overlay.background, color } })
        }
        onCommit={(color) =>
          commitField({ ...overlay, background: { ...overlay.background, color } })
        }
      />

      <SectionHeading>Padding</SectionHeading>

      <NumberField
        label="Padding"
        value={overlay.padding}
        min={0}
        // The field's ceiling, not a clamped value: `clampOverlayPadding` saturates
        // any padding at/above the true max, so feeding it +Infinity reads that max
        // back out — the same even-floored cap `service.py`'s `_clamp_padding` uses.
        max={clampOverlayPadding(Number.POSITIVE_INFINITY, overlay.size.width, overlay.size.height)}
        className="col-span-2"
        disabled={locked}
        onCommit={(padding) => commitField({ ...overlay, padding })}
      />

      <SectionHeading>Animation</SectionHeading>

      <NumberField
        label="Fade duration (ms)"
        value={overlay.animation.duration_ms}
        min={0}
        max={5000}
        className="col-span-2"
        disabled={locked}
        onCommit={(duration_ms) =>
          commitField({ ...overlay, animation: { ...overlay.animation, duration_ms } })
        }
      />
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="col-span-2 pt-1 text-xs font-semibold tracking-wide text-foreground/80 uppercase">
      {children}
    </div>
  );
}

function Field({
  label,
  className,
  children,
}: {
  label: string;
  className?: string | undefined;
  children: React.ReactNode;
}) {
  return (
    <label
      className={`flex flex-col gap-1.5 text-xs font-medium text-muted-foreground ${className ?? ''}`}
    >
      {label}
      {children}
    </label>
  );
}

/**
 * A locally-buffered numeric input. Typing is free-form (so "12" can become
 * "120" without the cursor fighting a live clamp); the value only commits —
 * and clamps — on blur or Enter, then the buffer resyncs to the clamped
 * result so the field visibly reflects what was actually applied.
 */
function NumberField({
  label,
  value,
  min,
  max,
  disabled,
  className,
  onCommit,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  disabled?: boolean;
  className?: string;
  onCommit: (value: number) => void;
}) {
  const [text, setText] = useState(String(value));

  useEffect(() => {
    setText(String(value));
  }, [value]);

  function commit() {
    const parsed = Number.parseInt(text, 10);
    const next = Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : value;
    setText(String(next));
    if (next !== value) onCommit(next);
  }

  return (
    <Field label={label} className={className}>
      <Input
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={text}
        disabled={disabled}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            commit();
          }
        }}
      />
    </Field>
  );
}

/**
 * A 0–1 slider (opacity-like values). `onChange` fires continuously while
 * dragging (live draft/preview only); `onCommit` fires once on release, so a
 * drag persists a single write instead of one per pointer tick.
 */
function SliderField({
  label,
  value,
  min,
  max,
  step,
  disabled,
  onChange,
  onCommit,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (value: number) => void;
  onCommit: (value: number) => void;
}) {
  return (
    <Field label={`${label} (${value.toFixed(2)})`}>
      <Slider
        value={[value]}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onValueChange={(next) => onChange(sliderValueAt(next, 0))}
        onValueCommitted={(next) => onCommit(sliderValueAt(next, 0))}
      />
    </Field>
  );
}

/**
 * A hex color field: a swatch (`<input type="color">`, the only native color
 * picker) paired with a buffered text input. The swatch fires `onChange`
 * continuously while the native picker is open (live draft/preview only)
 * and `onCommit` once on blur, when the picker closes — a drag inside the
 * OS color picker otherwise fires one `onChange` per pointer move. The text
 * input commits on blur/Enter, validating against `HEX_COLOR`.
 */
function ColorField({
  label,
  value,
  disabled,
  className,
  onChange,
  onCommit,
}: {
  label: string;
  value: string;
  disabled?: boolean;
  className?: string;
  onChange: (value: string) => void;
  onCommit: (value: string) => void;
}) {
  const [text, setText] = useState(value);

  useEffect(() => {
    setText(value);
  }, [value]);

  function commitText() {
    if (HEX_COLOR.test(text)) {
      if (text !== value) onCommit(text);
    } else {
      setText(value);
    }
  }

  return (
    <Field label={label} className={className}>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={HEX_COLOR.test(text) ? text : value}
          disabled={disabled}
          className="h-9 w-9 shrink-0 cursor-pointer rounded-md border border-transparent bg-input/50 disabled:cursor-not-allowed disabled:opacity-50"
          onChange={(event) => {
            setText(event.target.value);
            onChange(event.target.value);
          }}
          onBlur={(event) => onCommit(event.target.value)}
        />
        <Input
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onBlur={commitText}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              commitText();
            }
          }}
        />
      </div>
    </Field>
  );
}
