<script lang="ts">
  import { groupedActions, selectedAction, mutate } from '../lib/store';
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
      <section class="group">
        <header>
          <span class="group-name">{g.group}</span>
          <button class="ghost" title="Add action" onclick={() => addAction(g.group)}>＋</button>
        </header>
        {#if g.actions.length === 0}
          <p class="muted empty">(empty group)</p>
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
                      e.dataTransfer.effectAllowed = 'link';
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
  .group > header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.15rem 0.5rem;
    color: var(--text-dim);
    font-size: 0.85em;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .group-name { font-weight: 600; }
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
