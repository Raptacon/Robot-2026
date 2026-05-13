<script lang="ts">
  import {
    config,
    selectedAction,
    upsertAction,
    renameAction,
    deleteAction,
  } from '../lib/store';
  import {
    InputType,
    BUTTON_TRIGGER_MODES,
    ANALOG_TRIGGER_MODES,
    defaultTriggerModeFor,
    isAnalogLike,
  } from '../lib/types';
  import type { ActionDefinition, TriggerMode } from '../lib/types';

  const original = $derived(
    $selectedAction ? $config.actions[$selectedAction] ?? null : null,
  );

  // Editable copy.  Resets when the selection changes.
  let draft = $state<ActionDefinition | null>(null);
  let originalQname = $state<string | null>(null);

  $effect(() => {
    if (original && originalQname !== `${original.group}.${original.name}`) {
      draft = structuredClone(original);
      originalQname = `${original.group}.${original.name}`;
    } else if (!original) {
      draft = null;
      originalQname = null;
    }
  });

  const validTriggerModes = $derived<readonly TriggerMode[]>(
    draft && isAnalogLike(draft.input_type) ? ANALOG_TRIGGER_MODES : BUTTON_TRIGGER_MODES,
  );

  const usesShaping = $derived(
    draft &&
      isAnalogLike(draft.input_type) &&
      draft.trigger_mode !== 'raw',
  );

  function onInputTypeChange(): void {
    if (!draft) return;
    const modes = isAnalogLike(draft.input_type)
      ? ANALOG_TRIGGER_MODES
      : BUTTON_TRIGGER_MODES;
    if (!(modes as readonly string[]).includes(draft.trigger_mode)) {
      draft.trigger_mode = defaultTriggerModeFor(draft.input_type);
    }
  }

  function apply(): void {
    if (!draft || !originalQname) return;
    const trimmedName = draft.name.trim();
    const trimmedGroup = draft.group.trim();
    if (!trimmedName || trimmedName.includes('.')) {
      alert('Name cannot be empty or contain a dot.');
      return;
    }
    if (!trimmedGroup) {
      alert('Group cannot be empty.');
      return;
    }
    const next: ActionDefinition = {
      ...draft,
      name: trimmedName,
      group: trimmedGroup,
    };
    const newQname = `${trimmedGroup}.${trimmedName}`;
    if (newQname !== originalQname && $config.actions[newQname]) {
      alert(`An action named '${newQname}' already exists.`);
      return;
    }
    if (newQname === originalQname) {
      upsertAction(next);
    } else {
      renameAction(originalQname, next);
      selectedAction.set(newQname);
    }
  }

  function remove(): void {
    if (!originalQname) return;
    if (!confirm(`Delete action '${originalQname}'?`)) return;
    deleteAction(originalQname);
    selectedAction.set(null);
  }
</script>

<aside class="inspector">
  {#if !draft}
    <p class="muted placeholder">Select an action to edit it.</p>
  {:else}
    <header class="header">
      <strong>{originalQname}</strong>
      <button class="danger" onclick={remove}>Delete</button>
    </header>

    <div class="form">
      <label>
        <span>Group</span>
        <input type="text" bind:value={draft.group} />
      </label>

      <label>
        <span>Name</span>
        <input type="text" bind:value={draft.name} />
      </label>

      <label>
        <span>Description</span>
        <textarea rows="2" bind:value={draft.description}></textarea>
      </label>

      <label>
        <span>Input type</span>
        <select bind:value={draft.input_type} onchange={onInputTypeChange}>
          <option value={InputType.Button}>button</option>
          <option value={InputType.Analog}>analog</option>
          <option value={InputType.Output}>output (rumble)</option>
          <option value={InputType.BooleanTrigger}>boolean_trigger</option>
          <option value={InputType.VirtualAnalog}>virtual_analog</option>
        </select>
      </label>

      <label>
        <span>Trigger mode</span>
        <select bind:value={draft.trigger_mode}>
          {#each validTriggerModes as m (m)}
            <option value={m}>{m}</option>
          {/each}
        </select>
      </label>

      {#if usesShaping}
        <label>
          <span>Deadband</span>
          <input type="number" step="0.01" min="0" max="1" bind:value={draft.deadband} />
        </label>
        <label>
          <span>Slew rate (units/s, 0=off)</span>
          <input type="number" step="0.1" min="0" bind:value={draft.slew_rate} />
        </label>
        <label>
          <span>Scale</span>
          <input type="number" step="0.1" bind:value={draft.scale} />
        </label>
        <label class="row">
          <input type="checkbox" bind:checked={draft.inversion} />
          <span>Invert</span>
        </label>
      {/if}

      {#if draft.input_type === InputType.BooleanTrigger}
        <label>
          <span>Threshold</span>
          <input type="number" step="0.05" min="0" max="1" bind:value={draft.threshold} />
        </label>
      {/if}
    </div>

    <footer>
      <button class="primary" onclick={apply}>Apply</button>
    </footer>
  {/if}
</aside>

<style>
  .inspector {
    display: flex;
    flex-direction: column;
    background: var(--panel);
    border-left: 1px solid var(--border);
    min-width: 18rem;
    max-width: 24rem;
    height: 100%;
    overflow-y: auto;
  }
  .placeholder { padding: 1rem; }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border);
    background: var(--panel-2);
  }
  .form {
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
    padding: 0.75rem;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.85em;
  }
  label.row {
    flex-direction: row;
    align-items: center;
    gap: 0.4rem;
  }
  footer {
    padding: 0.5rem 0.75rem;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: flex-end;
  }
  .danger { background: var(--danger); border-color: var(--danger); color: #111; }
  .danger:hover { background: #f07a72; }
</style>
