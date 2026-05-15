<script lang="ts">
  import { currentPath, dirty } from '../lib/store';
  import {
    downloadExport,
    type ExportFormat,
    type ExportOrientation,
  } from '../lib/api';

  let open = $state(false);
  let busy = $state(false);
  let hideUnassigned = $state(false);
  let error = $state('');

  // Server reads from disk -- can't export unsaved drafts.
  const blocked = $derived(!$currentPath || $dirty);
  const blockReason = $derived(
    !$currentPath ? 'Load or save a config first.'
      : $dirty ? 'Save changes before exporting -- the server reads from disk.'
        : '',
  );

  function close(): void {
    open = false;
  }

  async function go(orientation: ExportOrientation, fmt: ExportFormat): Promise<void> {
    if (!$currentPath || busy) return;
    busy = true;
    error = '';
    try {
      await downloadExport({
        path: $currentPath,
        orientation,
        format: fmt,
        hideUnassigned,
      });
      close();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  function onDocClick(e: MouseEvent): void {
    if (!open) return;
    const target = e.target as Element | null;
    if (target?.closest('.export-menu')) return;
    close();
  }
</script>

<svelte:window onclick={onDocClick} />

<div class="export-menu">
  <button
    type="button"
    onclick={() => (open = !open)}
    disabled={blocked}
    title={blocked ? blockReason : 'Export controllers to PNG/PDF'}
  >
    Export {open ? '▴' : '▾'}
  </button>

  {#if open}
    <div class="popover" role="menu">
      <label class="row">
        <input type="checkbox" bind:checked={hideUnassigned} />
        <span>Hide unassigned inputs</span>
      </label>

      <div class="grid">
        <button type="button" disabled={busy} onclick={() => go('landscape', 'pdf')}>
          Landscape PDF
        </button>
        <button type="button" disabled={busy} onclick={() => go('landscape', 'png')}>
          Landscape PNG
        </button>
        <button type="button" disabled={busy} onclick={() => go('portrait', 'pdf')}>
          Portrait PDF
        </button>
        <button type="button" disabled={busy} onclick={() => go('portrait', 'png')}>
          Portrait PNG
        </button>
      </div>

      {#if busy}
        <div class="status">Rendering…</div>
      {/if}
      {#if error}
        <div class="status error">{error}</div>
      {/if}
      <div class="hint">
        PNG is single-page only — choose PDF when more than one controller fits on the layout.
      </div>
    </div>
  {/if}
</div>

<style>
  .export-menu {
    position: relative;
  }
  .popover {
    position: absolute;
    right: 0;
    top: calc(100% + 4px);
    min-width: 22rem;
    background: var(--panel, #fff);
    border: 1px solid var(--border, #888);
    border-radius: 6px;
    padding: 0.6rem 0.7rem;
    z-index: 50;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.9em;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.4rem;
  }
  .status {
    font-size: 0.85em;
    color: var(--text-dim, #666);
  }
  .status.error {
    color: #c33;
  }
  .hint {
    font-size: 0.78em;
    color: var(--text-dim, #888);
  }
</style>
