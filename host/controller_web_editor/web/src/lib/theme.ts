// Theme dropdown state + persistence.
//
// The active theme is mirrored to the <html> element's `data-theme`
// attribute so app.css picks up the matching :root override.  Server
// persistence is best-effort -- if /api/prefs is unreachable the UI
// still works, the choice just doesn't survive a reload.

import { writable, get } from 'svelte/store';
import { loadPrefs, savePrefs, type ThemeName } from './api';

export const THEMES: { value: ThemeName; label: string }[] = [
  { value: 'dark', label: 'Dark' },
  { value: 'light', label: 'Light' },
  { value: 'raptacon', label: 'Raptacon' },
  { value: 'solarized-dark', label: 'Solarized Dark' },
  { value: 'high-contrast', label: 'High Contrast' },
];

export const DEFAULT_THEME: ThemeName = 'dark';

export const theme = writable<ThemeName>(DEFAULT_THEME);

function applyToDom(t: ThemeName): void {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', t);
  }
}

// Whenever the store changes, mirror to the DOM.  No await -- the
// caller can decide whether to also persist.
theme.subscribe(applyToDom);

export async function initTheme(): Promise<void> {
  try {
    const prefs = await loadPrefs();
    if (prefs.theme && THEMES.some((t) => t.value === prefs.theme)) {
      theme.set(prefs.theme);
    } else {
      // No persisted value yet: still apply the default so the DOM
      // attribute exists (downstream CSS can rely on it).
      applyToDom(DEFAULT_THEME);
    }
  } catch {
    // /api/prefs unreachable -- fall back to whatever is currently set.
    applyToDom(get(theme));
  }
}

export async function setTheme(next: ThemeName): Promise<void> {
  theme.set(next);
  try {
    await savePrefs({ theme: next });
  } catch {
    // Persistence failures are silent; the UI is unaffected.
  }
}
