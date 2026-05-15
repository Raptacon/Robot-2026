// Hitbox layouts are fetched from the Python server (not bundled into the
// SPA) so saving from the editor persists across reloads on every machine.
//
// The canonical files live at host/controller_web_editor/hitboxes/<name>.json.

import { writable, type Writable } from 'svelte/store';

export type HitShape =
  | { shape: 'circle'; cx: number; cy: number; r: number }
  | { shape: 'ellipse'; cx: number; cy: number; rx: number; ry: number }
  | { shape: 'rect'; x: number; y: number; width: number; height: number };

export interface LabelOffset {
  dx: number;
  dy: number;
}

export interface FontSettings {
  input_name: number;   // monospace per-region name shown in show/edit modes
  action_label: number; // bound action chip rendered near each region
}

// Default: label sits at the region center, matching the position the
// name-label uses when no action is bound.  Custom offsets in the layout
// file's `labels` map (or in-editor drags) override this per region.
export const DEFAULT_LABEL_OFFSET: LabelOffset = { dx: 0, dy: 0 };
export const DEFAULT_FONTS: FontSettings = { input_name: 7, action_label: 10 };

export interface HitboxFile {
  viewBox: string;
  _note?: string;
  regions: Record<string, HitShape>;
  labels?: Record<string, LabelOffset>;
  fonts?: Partial<FontSettings>;
}

export function regionCenter(shape: HitShape): { x: number; y: number } {
  switch (shape.shape) {
    case 'circle':
    case 'ellipse':
      return { x: shape.cx, y: shape.cy };
    case 'rect':
      return { x: shape.x + shape.width / 2, y: shape.y + shape.height / 2 };
  }
}

export function effectiveFonts(file: HitboxFile | null): FontSettings {
  return {
    input_name: file?.fonts?.input_name ?? DEFAULT_FONTS.input_name,
    action_label: file?.fonts?.action_label ?? DEFAULT_FONTS.action_label,
  };
}

export function effectiveLabelOffset(
  file: HitboxFile | null,
  input: string,
): LabelOffset {
  const ov = file?.labels?.[input];
  if (!ov) return DEFAULT_LABEL_OFFSET;
  return {
    dx: typeof ov.dx === 'number' ? ov.dx : DEFAULT_LABEL_OFFSET.dx,
    dy: typeof ov.dy === 'number' ? ov.dy : DEFAULT_LABEL_OFFSET.dy,
  };
}

// Reactive store that components subscribe to.  `null` while the initial
// fetch is in flight.
export const hitboxes: Writable<HitboxFile | null> = writable(null);

export async function fetchHitboxes(layout = 'xbox'): Promise<HitboxFile> {
  const resp = await fetch(`/api/hitboxes?layout=${encodeURIComponent(layout)}`);
  if (!resp.ok) {
    let detail = '';
    try { detail = (await resp.json()).error ?? ''; } catch { detail = await resp.text(); }
    throw new Error(`load failed: ${resp.status}${detail ? ': ' + detail : ''}`);
  }
  const data = (await resp.json()) as HitboxFile;
  hitboxes.set(data);
  return data;
}

export async function saveHitboxes(data: HitboxFile, layout = 'xbox'): Promise<void> {
  const resp = await fetch(`/api/hitboxes?layout=${encodeURIComponent(layout)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!resp.ok) {
    let detail = '';
    try { detail = (await resp.json()).error ?? ''; } catch { detail = await resp.text(); }
    throw new Error(`save failed: ${resp.status}${detail ? ': ' + detail : ''}`);
  }
  hitboxes.set(data);
}
