<script lang="ts">
  import { onMount } from 'svelte';
  import {
    config,
    currentPath,
    dirty,
    canUndo,
    canRedo,
    loadInto,
    markSaved,
    undo,
    redo,
    inspectorExpanded,
    emptyConfig,
  } from './lib/store';
  import { listConfigs, loadConfig, saveConfig } from './lib/api';
  import ActionLibrary from './components/ActionLibrary.svelte';
  import ActionInspector from './components/ActionInspector.svelte';
  import BindingMenu from './components/BindingMenu.svelte';
  import ControllerView from './components/ControllerView.svelte';
  import ExportMenu from './components/ExportMenu.svelte';
  import { theme, setTheme, initTheme, THEMES } from './lib/theme';
  import type { ThemeName } from './lib/api';
  import raptaconLogo from './assets/raptacon-gear.png';

  let centerTab = $state<'controller' | 'list'>('controller');
  let activePort = $state(0);

  let configs = $state<string[]>([]);
  let chosen = $state<string>('');
  let status = $state<string>('');
  let loading = $state(false);

  async function refreshConfigs(): Promise<void> {
    try {
      const r = await listConfigs();
      configs = r.configs;
      if (!chosen && configs.length > 0) chosen = configs[0];
    } catch (e) {
      status = `Error listing configs: ${(e as Error).message}`;
    }
  }

  async function doLoad(): Promise<void> {
    if (!chosen) return;
    loading = true;
    status = `Loading ${chosen}…`;
    try {
      const c = await loadConfig(chosen);
      loadInto(c, chosen);
      status = `Loaded ${chosen}`;
    } catch (e) {
      status = `Error: ${(e as Error).message}`;
    } finally {
      loading = false;
    }
  }

  function doNew(): void {
    const raw = prompt('New config filename (saved under data/):', 'new.yaml')?.trim();
    if (!raw) return;
    const path = raw.endsWith('.yaml') || raw.endsWith('.yml') ? raw : `${raw}.yaml`;
    if (configs.includes(path)) {
      if (!confirm(`'${path}' already exists.  Overwrite with a blank config when you Save?`)) return;
    }
    // Spin up a fresh in-memory config bound to the new path.  Nothing is
    // written to disk until the user clicks Save.  Mark dirty so the Save
    // button enables immediately -- the user clearly wants this file to
    // exist on disk.
    loadInto(emptyConfig(), path);
    dirty.set(true);
    if (!configs.includes(path)) configs = [...configs, path];
    chosen = path;
    status = `New config: ${path} (unsaved -- click Save to write to disk)`;
  }

  async function doSave(): Promise<void> {
    if (!$currentPath) return;
    status = `Saving ${$currentPath}…`;
    try {
      await saveConfig($currentPath, $config);
      markSaved();
      status = `Saved ${$currentPath}`;
    } catch (e) {
      status = `Error: ${(e as Error).message}`;
    }
  }

  function onKeydown(e: KeyboardEvent): void {
    const meta = e.ctrlKey || e.metaKey;
    if (!meta) return;
    if (e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
    else if ((e.key === 'z' && e.shiftKey) || e.key === 'y') { e.preventDefault(); redo(); }
    else if (e.key === 's') { e.preventDefault(); doSave(); }
  }

  onMount(() => {
    initTheme();
    refreshConfigs();
  });

  function onThemeChange(e: Event): void {
    const value = (e.currentTarget as HTMLSelectElement).value as ThemeName;
    setTheme(value);
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="app">
  <header class="top">
    <img class="brand-logo" src={raptaconLogo} alt="Raptacon 3200" />
    <strong>Controller Editor</strong>
    <span class="spacer"></span>
    <label class="row" title="Color theme">
      <span>Theme</span>
      <select value={$theme} onchange={onThemeChange}>
        {#each THEMES as t (t.value)}
          <option value={t.value}>{t.label}</option>
        {/each}
      </select>
    </label>
    <label class="row">
      <span>Config</span>
      <select bind:value={chosen}>
        {#each configs as p (p)}
          <option value={p}>{p}</option>
        {/each}
      </select>
    </label>
    <button onclick={doNew}>New</button>
    <button onclick={doLoad} disabled={loading || !chosen}>Load</button>
    <button class="primary" onclick={doSave} disabled={!$currentPath || !$dirty}>
      Save{$dirty ? ' •' : ''}
    </button>
    <button onclick={undo} disabled={!$canUndo} title="Ctrl+Z">Undo</button>
    <button onclick={redo} disabled={!$canRedo} title="Ctrl+Shift+Z">Redo</button>
    <ExportMenu />
    <span class="muted status">{status}</span>
  </header>

  <main class:inspector-expanded={$inspectorExpanded}>
    <ActionLibrary />
    <section class="center">
      <div class="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={centerTab === 'controller'}
          class:active={centerTab === 'controller'}
          onclick={() => (centerTab = 'controller')}
        >Controller</button>
        <button
          role="tab"
          aria-selected={centerTab === 'list'}
          class:active={centerTab === 'list'}
          onclick={() => (centerTab = 'list')}
        >List</button>
      </div>
      <div class="tab-body">
        {#if centerTab === 'controller'}
          <ControllerView bind:port={activePort} />
        {:else}
          <BindingMenu bind:port={activePort} />
        {/if}
      </div>
    </section>
    <ActionInspector />
  </main>
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .top {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.75rem;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
  }
  .brand-logo {
    height: 1.8rem;
    width: 1.8rem;
    object-fit: contain;
    border-radius: 4px;
    margin-right: 0.1rem;
    flex-shrink: 0;
  }
  .spacer { flex: 1; }
  .status {
    margin-left: 0.5rem;
    font-size: 0.85em;
    max-width: 20rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  main {
    flex: 1;
    display: grid;
    grid-template-columns: minmax(16rem, 22rem) 1fr minmax(18rem, 24rem);
    min-height: 0;
    transition: grid-template-columns 180ms ease;
  }
  /* Inspector expanded: take roughly twice the room from the center pane
     so the curve editor + live preview have a column of their own.  The
     library on the left stays at its normal width. */
  main.inspector-expanded {
    grid-template-columns: minmax(16rem, 22rem) 1fr minmax(38rem, 48rem);
  }
  .center {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
  .tabs {
    display: flex;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
  }
  .tabs button {
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 0.5rem 1rem;
    color: var(--text-dim);
    cursor: pointer;
  }
  .tabs button.active {
    color: var(--text);
    border-bottom-color: var(--accent);
  }
  .tab-body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
</style>
