import type { FullConfig } from './types';

async function jsonFetch<T>(input: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(input, init);
  if (!resp.ok) {
    let detail = '';
    try {
      detail = (await resp.json()).error ?? '';
    } catch {
      detail = await resp.text();
    }
    throw new Error(`${resp.status} ${resp.statusText}${detail ? ': ' + detail : ''}`);
  }
  return resp.json() as Promise<T>;
}

export function listConfigs(): Promise<{ configs: string[] }> {
  return jsonFetch('/api/configs');
}

export function loadConfig(path: string): Promise<FullConfig> {
  return jsonFetch(`/api/config?path=${encodeURIComponent(path)}`);
}

export function saveConfig(path: string, config: FullConfig): Promise<{ saved: string }> {
  return jsonFetch(`/api/config?path=${encodeURIComponent(path)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

export type ExportOrientation = 'portrait' | 'landscape';
export type ExportFormat = 'png' | 'pdf';

export interface ExportOptions {
  path: string;
  orientation: ExportOrientation;
  format: ExportFormat;
  hideUnassigned?: boolean;
}

export function exportUrl(opts: ExportOptions): string {
  const q = new URLSearchParams({
    path: opts.path,
    orientation: opts.orientation,
    format: opts.format,
    hide_unassigned: opts.hideUnassigned ? '1' : '0',
  });
  return `/api/export?${q.toString()}`;
}

export interface Prefs {
  theme?: ThemeName;
}

export type ThemeName =
  | 'dark'
  | 'light'
  | 'raptacon'
  | 'solarized-dark'
  | 'high-contrast';

export function loadPrefs(): Promise<Prefs> {
  return jsonFetch<Prefs>('/api/prefs');
}

export function savePrefs(prefs: Prefs): Promise<Prefs> {
  return jsonFetch<Prefs>('/api/prefs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(prefs),
  });
}

// Fetches the export and triggers a browser download.  Using fetch
// (instead of <a href> navigation) lets us surface server-side errors
// as a thrown exception rather than a blank file.
export async function downloadExport(opts: ExportOptions): Promise<string> {
  const resp = await fetch(exportUrl(opts));
  if (!resp.ok) {
    let detail = '';
    try {
      detail = (await resp.json()).error ?? '';
    } catch {
      detail = await resp.text();
    }
    throw new Error(
      `${resp.status} ${resp.statusText}${detail ? ': ' + detail : ''}`,
    );
  }
  const cd = resp.headers.get('Content-Disposition') ?? '';
  const m = /filename="([^"]+)"/.exec(cd);
  const filename = m?.[1]
    ?? `${opts.path.split('/').pop()?.replace(/\.ya?ml$/, '') ?? 'controllers'}_${opts.orientation}.${opts.format}`;
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Defer revoke so the click can complete before the URL goes away.
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return filename;
}
