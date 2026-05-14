<script lang="ts">
  import {
    groupedActions,
    selectedAction,
    mutate,
    moveActionToGroup,
    renameGroup,
    deleteGroup,
  } from '../lib/store';
  import { qualifiedName, newAction, InputType } from '../lib/types';
  import type { ActionDefinition } from '../lib/types';
  import { draggedAction } from '../lib/dragdrop';

  let query = $state('');
  const filtered = $derived(
    $groupedActions
      .map((g) => ({
        group: g.group,
        actions: g.actions.filter((a) =>
          query.trim() === ''
            ? true
            : `${qualifiedName(a)} ${a.description}`
                .toLowerCase()
                .includes(query.toLowerCase()),
        ),
      }))
      .filter((g) => g.actions.length > 0 || query.trim() === ''),
  );

  function select(a: ActionDefinition) {
    selectedAction.set(qualifiedName(a));
  }

  function addGroup() {
    const name = prompt('New group name')?.trim();
    if (!name) return;
    mutate(`add group ${name}`, (c) => {
      if (!c.empty_groups.includes(name)) c.empty_groups.push(name);
    });
  }

  function addAction(group: string) {
    const name = prompt(`New action name in '${group}'`)?.trim();
    if (!name) return;
    const action = newAction(group, name);
    action.input_type = InputType.Button;
    const qname = qualifiedName(action);
    mutate(`add ${qname}`, (c) => {
      if (c.actions[qname]) return;
      c.actions[qname] = action;
      c.empty_groups = c.empty_groups.filter((g) => g !== group);
    });
    selectedAction.set(qname);
  }

  // Inline group rename.  Double-click the name (or hit the pencil) to
  // enter edit mode; Enter commits, Esc cancels.
  let editingGroup = $state<string | null>(null);
  let editingName = $state('');

  function startRename(group: string): void {
    editingGroup = group;
    editingName = group;
  }

  function commitRename(): void {
    if (editingGroup === null) return;
    const trimmed = editingName.trim();
    const original = editingGroup;
    editingGroup = null;
    if (!trimmed || trimmed === original) return;
    renameGroup(original, trimmed);
  }

  function cancelRename(): void {
    editingGroup = null;
  }

  function onRenameKey(ev: KeyboardEvent): void {
    if (ev.key === 'Enter') { ev.preventDefault(); commitRename(); }
    else if (ev.key === 'Escape') { ev.preventDefault(); cancelRename(); }
  }

  // Programmatic focus on the rename input.  Avoids the autofocus
  // attribute (which fires on every mount and the a11y linter flags).
  function focusOnMount(node: HTMLInputElement): void {
    node.focus();
    node.select();
  }

  function removeGroup(group: string): void {
    if (!confirm(`Delete group '${group}' and all actions in it?`)) return;
    deleteGroup(group);
  }

  // Drag-and-drop between groups.  The action being dragged was already
  // recorded in the draggedAction store by ondragstart on the row.
  let dropTarget = $state<string | null>(null);

  function isMoveDrop(): boolean {
    return $draggedAction !== null;
  }

  function onGroupDragOver(group: string, ev: DragEvent): void {
    if (!isMoveDrop()) return;
    const qn = $draggedAction;
    if (!qn) return;
    const dot = qn.indexOf('.');
    const srcGroup = dot < 0 ? '' : qn.slice(0, dot);
    if (srcGroup === group) return;       // same group is a no-op
    ev.preventDefault();
    if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'move';
    dropTarget = group;
  }

  function onGroupDragLeave(group: string): void {
    if (dropTarget === group) dropTarget = null;
  }

  function onGroupDrop(group: string, ev: DragEvent): void {
    ev.preventDefault();
    const qn = $draggedAction;
    dropTarget = null;
    draggedAction.set(null);
    if (!qn) return;
    moveActionToGroup(qn, group);
  }
</script>

<aside class="library">
  <header class="row">
    <input
      type="search"
      placeholder="Search actions…"
      bind:value={query}
      aria-label="Search actions"
    />
    <button title="Add group" onclick={addGroup}>＋ group</button>
  </header>

  <div class="groups">
    {#each filtered as g (g.group)}
      <section
        class="group"
        class:drop-target={dropTarget === g.group}
        ondragover={(e: DragEvent) => onGroupDragOver(g.group, e)}
        ondragleave={() => onGroupDragLeave(g.group)}
        ondrop={(e: DragEvent) => onGroupDrop(g.group, e)}
        role="group"
      >
        <header>
          {#if editingGroup === g.group}
            <input
              class="group-rename"
              type="text"
              bind:value={editingName}
              use:focusOnMount
              onkeydown={onRenameKey}
              onblur={commitRename}
            />
          {:else}
            <button
              class="group-name"
              title="Double-click to rename"
              ondblclick={() => startRename(g.group)}
            >{g.group}</button>
          {/if}
          <span class="group-actions">
            <button class="ghost" title="Rename group" onclick={() => startRename(g.group)}>✎</button>
            <button class="ghost danger-ghost" title="Delete group" onclick={() => removeGroup(g.group)}>×</button>
            <button class="ghost" title="Add action" onclick={() => addAction(g.group)}>＋</button>
          </span>
        </header>
        {#if g.actions.length === 0}
          <p class="muted empty">(empty group · drop here to move)</p>
        {:else}
          <ul>
            {#each g.actions as a (qualifiedName(a))}
              {@const qn = qualifiedName(a)}
              <li>
                <button
                  class="action-row"
                  class:selected={$selectedAction === qn}
                  draggable="true"
                  ondragstart={(e: DragEvent) => {
                    draggedAction.set(qn);
                    if (e.dataTransfer) {
                      // 'linkMove' covers both targets: link onto a
                      // controller region (bind) or move into a group.
                      e.dataTransfer.effectAllowed = 'linkMove';
                      e.dataTransfer.setData('text/plain', qn);
                    }
                  }}
                  ondragend={() => draggedAction.set(null)}
                  onclick={() => select(a)}
                >
                  <span class="action-name">{a.name}</span>
                  <span class="action-type">{a.input_type}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    {/each}
    {#if filtered.length === 0}
      <p class="muted" style="padding: 0.5rem;">No actions match.</p>
    {/if}
  </div>
</aside>

<style>
  .library {
    display: flex;
    flex-direction: column;
    background: var(--panel);
    border-right: 1px solid var(--border);
    min-width: 16rem;
    max-width: 22rem;
    height: 100%;
    overflow: hidden;
  }
  header.row {
    padding: 0.5rem;
    gap: 0.5rem;
    border-bottom: 1px solid var(--border);
  }
  header.row input { flex: 1; }

  .groups {
    flex: 1;
    overflow-y: auto;
    padding: 0.25rem 0;
  }
  .group { margin: 0.5rem 0; }
  .group.drop-target {
    background: rgba(255, 184, 77, 0.08);
    outline: 1px dashed rgba(255, 184, 77, 0.55);
    outline-offset: -2px;
  }
  .group > header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.15rem 0.5rem;
    color: var(--text-dim);
    font-size: 0.85em;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    gap: 0.4rem;
  }
  .group-name {
    font-weight: 600;
    background: transparent;
    border: 0;
    padding: 0;
    color: inherit;
    text-transform: inherit;
    letter-spacing: inherit;
    font: inherit;
    font-weight: 600;
    cursor: text;
    text-align: left;
    flex: 1;
  }
  .group-name:hover {
    color: var(--text);
  }
  .group-rename {
    flex: 1;
    font: inherit;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0.1rem 0.35rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .group-actions {
    display: inline-flex;
    gap: 0.15rem;
  }
  .danger-ghost:hover {
    color: var(--danger, #ff8a7a);
  }
  ul { list-style: none; margin: 0; padding: 0; }
  .action-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 0.3rem 0.6rem;
    background: transparent;
    border: 0;
    border-radius: 0;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }
  .action-row:hover { background: var(--panel-2); }
  .action-row.selected { background: var(--selected); }
  .action-name { font-weight: 500; }
  .action-type {
    font-size: 0.75em;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .ghost {
    background: transparent;
    border: 1px solid transparent;
    padding: 0 0.4rem;
    line-height: 1;
  }
  .ghost:hover { background: var(--panel-2); border-color: var(--border); }
  .empty { padding: 0 0.6rem; font-style: italic; }
</style>
