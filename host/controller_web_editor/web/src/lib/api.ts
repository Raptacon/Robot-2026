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
