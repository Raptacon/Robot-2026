<script lang="ts">
  import {
    config,
    selectedAction,
    upsertAction,
    renameAction,
    deleteAction,
    setBinding,
    ensureController,
    inspectorExpanded,
    pendingNewAction,
    mutate,
  } from '../lib/store';
  import {
    InputType,
    BUTTON_TRIGGER_MODES,
    ANALOG_TRIGGER_MODES,
    defaultTriggerModeFor,
    isAnalogLike,
  } from '../lib/types';
  import type { ActionDefinition, TriggerMode } from '../lib/types';
  import { defaultSplinePoints, defaultSegmentPoints } from '../lib/curves.js';
  import { ALL_INPUTS, categoryFor, humanLabel, isCompatible } from '../lib/inputs';
  import { get } from 'svelte/store';
  import CurveEditor from './CurveEditor.svelte';
  import LivePreview from './LivePreview.svelte';

  // When a pending new action is active, treat it as the original for
  // draft purposes -- the inspector renders a normal editor view, but
  // nothing is persisted until Apply.
  const isPending = $derived($pendingNewAction !== null);

  const original = $derived(
    $pendingNewAction !== null
      ? $pendingNewAction.action
      : ($selectedAction ? $config.actions[$selectedAction] ?? null : null),
  );

  // Sorted list of every group currently in use plus any empty groups.
  // Surfaced as a <datalist> on the Group field so the user can pick
  // existing groups but still type a new one freely.
  const knownGroups = $derived.by((): string[] => {
    const set = new Set<string>();
    for (const a of Object.values($config.actions)) set.add(a.group);
    for (const g of $config.empty_groups) set.add(g);
    return [...set].sort();
  });

  // Editable copy.  Resets when the selection changes.
  let draft = $state<ActionDefinition | null>(null);
  let originalQname = $state<string | null>(null);

  // Binding snapshot captured when the draft is first loaded for a given
  // action (and refreshed after Apply).  Reset uses this to undo any
  // unbind / add-binding edits the user made through the inspector.
  // Bindings themselves are still committed to the store immediately --
  // we just remember the starting state so we can roll back.
  interface BindingRef { port: number; input: string }
  let originalBindings = $state<BindingRef[]>([]);

  function collectBindingsForQname(qname: string): BindingRef[] {
    const out: BindingRef[] = [];
    const cfg = get(config);
    for (const [portKey, ctrl] of Object.entries(cfg.controllers)) {
      const port = Number(portKey);
      if (!Number.isFinite(port)) continue;
      for (const [input, qnames] of Object.entries(ctrl.bindings ?? {})) {
        if (qnames.includes(qname)) out.push({ port, input });
      }
    }
    return out.sort((a, b) =>
      a.port !== b.port ? a.port - b.port : a.input.localeCompare(b.input));
  }

  $effect(() => {
    if (original && originalQname !== `${original.group}.${original.name}`) {
      const qname = `${original.group}.${original.name}`;
      draft = structuredClone(original);
      originalQname = qname;
      originalBindings = collectBindingsForQname(qname);
    } else if (!original) {
      draft = null;
      originalQname = null;
      originalBindings = [];
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

  const usesSpline = $derived(usesShaping && draft?.trigger_mode === 'spline');
  const usesSegments = $derived(usesShaping && draft?.trigger_mode === 'segmented');

  // Curve-editor change handlers.  Apply immediately to the draft so the
  // live preview reflects the edit without needing Apply.
  function onSplinePointsChange(points: unknown[]): void {
    if (!draft) return;
    draft.extra = { ...draft.extra, spline_points: points };
  }
  function onSegmentPointsChange(points: unknown[]): void {
    if (!draft) return;
    draft.extra = { ...draft.extra, segment_points: points };
  }

  // Ensure curve-data exists when switching into a curve mode so the editor
  // has something to render and the preview has a curve to evaluate.
  function ensureCurveData(): void {
    if (!draft) return;
    if (draft.trigger_mode === 'spline' && !Array.isArray(draft.extra?.spline_points)) {
      draft.extra = { ...draft.extra, spline_points: defaultSplinePoints() };
    } else if (draft.trigger_mode === 'segmented' && !Array.isArray(draft.extra?.segment_points)) {
      draft.extra = { ...draft.extra, segment_points: defaultSegmentPoints() };
    }
  }

  function onTriggerModeChange(): void {
    ensureCurveData();
  }

  function onInputTypeChange(): void {
    if (!draft) return;
    const modes = isAnalogLike(draft.input_type)
      ? ANALOG_TRIGGER_MODES
      : BUTTON_TRIGGER_MODES;
    if (!(modes as readonly string[]).includes(draft.trigger_mode)) {
      draft.trigger_mode = defaultTriggerModeFor(draft.input_type);
    }
    ensureCurveData();
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
    // Pending-new flow: action doesn't exist in $config yet.  Create it
    // and bind it to the region recorded on the pending stub, all in one
    // mutate so it lands as a single undo step.
    const pending = $pendingNewAction;
    if (pending) {
      const port = pending.binding.port;
      const input = pending.binding.input;
      mutate(`add ${newQname}`, (c) => {
        c.actions[newQname] = next;
        c.empty_groups = c.empty_groups.filter((g) => g !== trimmedGroup);
        if (!c.controllers[String(port)]) {
          c.controllers[String(port)] = {
            port, name: '', controller_type: 'xbox', bindings: {},
          };
        }
        const cur = c.controllers[String(port)].bindings[input] ?? [];
        if (!cur.includes(newQname)) {
          c.controllers[String(port)].bindings[input] = [...cur, newQname];
        }
      });
      pendingNewAction.set(null);
      selectedAction.set(newQname);
      originalBindings = collectBindingsForQname(newQname);
      return;
    }
    if (newQname === originalQname) {
      upsertAction(next);
    } else {
      renameAction(originalQname, next);
      selectedAction.set(newQname);
    }
    // The committed state is now the new baseline -- refresh the binding
    // snapshot so a subsequent Reset doesn't revert past this point.
    // Use the post-Apply qname; renameAction has already remapped the
    // bindings across all controllers.
    originalBindings = collectBindingsForQname(newQname);
  }

  function remove(): void {
    if (!originalQname) return;
    if (!confirm(`Delete action '${originalQname}'?`)) return;
    deleteAction(originalQname);
    selectedAction.set(null);
  }

  // Duplicate the current action: clone everything except the name and
  // bindings.  Auto-suffix the name with `_copy` (and `_copy_2`,
  // `_copy_3`, ... if needed to avoid collisions in the same group).
  function copy(): void {
    if (!original) return;
    const base = `${original.name}_copy`;
    let candidate = base;
    let n = 2;
    while ($config.actions[`${original.group}.${candidate}`]) {
      candidate = `${base}_${n}`;
      n += 1;
    }
    const dup: ActionDefinition = {
      ...structuredClone(original),
      name: candidate,
    };
    upsertAction(dup);
    selectedAction.set(`${dup.group}.${dup.name}`);
  }

  // Apply commits the draft to the in-memory config -- not to disk.  The
  // toolbar Save button writes to YAML.  Reset throws away pending edits
  // (both action fields and binding changes) and re-clones the current
  // config state into the draft + binding snapshot.
  function reset(): void {
    // Pending-new flow: Reset discards the unsaved action entirely.
    if ($pendingNewAction) {
      pendingNewAction.set(null);
      selectedAction.set(null);
      return;
    }
    if (!original || !originalQname) return;
    // Revert binding changes first so the store update for action fields
    // doesn't race with our binding diff.  Walk both sets; remove what
    // shouldn't be there, restore what should.
    const want = new Set(originalBindings.map(bindingKey));
    const have = new Set(currentBindings.map(bindingKey));
    for (const ref of currentBindings) {
      if (!want.has(bindingKey(ref))) {
        const list = (get(config).controllers[String(ref.port)]?.bindings[ref.input]) ?? [];
        setBinding(ref.port, ref.input, list.filter((a) => a !== originalQname));
      }
    }
    for (const ref of originalBindings) {
      if (!have.has(bindingKey(ref))) {
        ensureController(ref.port);
        const list = (get(config).controllers[String(ref.port)]?.bindings[ref.input]) ?? [];
        if (!list.includes(originalQname)) {
          setBinding(ref.port, ref.input, [...list, originalQname]);
        }
      }
    }
    draft = structuredClone(original);
    originalQname = `${original.group}.${original.name}`;
  }

  const isDirty = $derived.by(() => {
    if (!draft || !original) return false;
    // A pending new action is "dirty" by definition -- it doesn't exist
    // in the store yet, so Apply must be enabled even if the user hasn't
    // touched a field.
    if (isPending) return true;
    if (JSON.stringify(draft) !== JSON.stringify(original)) return true;
    return bindingsDirty;
  });

  // True when the draft's qualified name differs from the persisted one.
  // Apply will call renameAction(), which both moves the entry in
  // $config.actions and remaps every binding across all controllers --
  // we surface that explicitly so the user understands existing
  // bindings aren't going to break.
  const willRename = $derived.by(() => {
    if (!draft || !originalQname) return false;
    const trimmedGroup = draft.group.trim();
    const trimmedName = draft.name.trim();
    if (!trimmedGroup || !trimmedName) return false;
    return `${trimmedGroup}.${trimmedName}` !== originalQname;
  });

  const pendingQname = $derived(
    draft ? `${draft.group.trim()}.${draft.name.trim()}` : '',
  );

  // --- Bindings panel ---
  //
  // Binding edits go directly through setBinding so the controller view
  // updates immediately, but we also track the starting state in
  // `originalBindings` so Reset can roll the bindings back along with
  // the draft fields.  We re-key the panel by `originalQname` (the
  // persisted name) because that's what's stored in $config; the draft's
  // group/name may differ if the user is renaming and hasn't applied yet.

  const currentBindings = $derived.by((): BindingRef[] => {
    if (!originalQname) return [];
    // Read $config so the derived re-runs when bindings change in the
    // store -- collectBindingsForQname uses get() internally which
    // doesn't track reactivity on its own.
    void $config.controllers;
    return collectBindingsForQname(originalQname);
  });

  function bindingKey(b: BindingRef): string {
    return `${b.port}:${b.input}`;
  }

  const bindingsDirty = $derived.by((): boolean => {
    if (currentBindings.length !== originalBindings.length) return true;
    const a = new Set(currentBindings.map(bindingKey));
    for (const b of originalBindings) {
      if (!a.has(bindingKey(b))) return true;
    }
    return false;
  });

  const availablePorts = $derived.by((): number[] => {
    const ports = Object.keys($config.controllers)
      .map(Number)
      .filter((n) => Number.isFinite(n))
      .sort((a, b) => a - b);
    return ports.length > 0 ? ports : [0];
  });

  // For the "add binding" row.  Resets when the port or action changes.
  let addPort = $state<number>(0);

  $effect(() => {
    if (availablePorts.length > 0 && !availablePorts.includes(addPort)) {
      addPort = availablePorts[0];
    }
  });

  const freeInputs = $derived.by((): string[] => {
    if (!original) return [];
    const bound = $config.controllers[String(addPort)]?.bindings ?? {};
    return ALL_INPUTS.filter((input) => {
      if (!isCompatible(input, original.input_type)) return false;
      const existing = bound[input] ?? [];
      return !existing.includes(originalQname ?? '');
    });
  });

  function unbind(ref: BindingRef): void {
    if (!originalQname) return;
    const current = $config.controllers[String(ref.port)]?.bindings[ref.input] ?? [];
    setBinding(ref.port, ref.input, current.filter((a) => a !== originalQname));
  }

  function addBinding(input: string): void {
    if (!input || !originalQname) return;
    ensureController(addPort);
    const current = $config.controllers[String(addPort)]?.bindings[input] ?? [];
    if (current.includes(originalQname)) return;
    setBinding(addPort, input, [...current, originalQname]);
  }
</script>

<!-- Curve editor and live preview rendered via a snippet so the same
     markup can sit inline in the form (collapsed mode) or in a side
     column (expanded mode) without duplication. -->
{#snippet curveBlock()}
  {#if draft && usesSpline}
    <CurveEditor
      mode="spline"
      points={(draft.extra?.spline_points as any[]) ?? defaultSplinePoints()}
      onChange={onSplinePointsChange}
    />
  {/if}
  {#if draft && usesSegments}
    <CurveEditor
      mode="segments"
      points={(draft.extra?.segment_points as any[]) ?? defaultSegmentPoints()}
      onChange={onSegmentPointsChange}
    />
  {/if}
  {#if draft && isAnalogLike(draft.input_type)}
    <section class="preview-section">
      <h4>Live preview</h4>
      <LivePreview
        inversion={draft.inversion}
        deadband={draft.deadband}
        scale={draft.scale}
        slewRate={draft.slew_rate}
        triggerMode={draft.trigger_mode}
        splinePoints={(draft.extra?.spline_points as any[]) ?? undefined}
        segmentPoints={(draft.extra?.segment_points as any[]) ?? undefined}
      />
    </section>
  {/if}
{/snippet}

<aside class="inspector" class:expanded={$inspectorExpanded}>
  {#if !draft}
    <p class="muted placeholder">Select an action to edit it.</p>
  {:else}
    <header class="header">
      <strong>{originalQname}{isPending ? ' (new)' : ''}</strong>
      <div class="header-actions">
        <button
          class="icon-btn"
          onclick={() => inspectorExpanded.update((v) => !v)}
          title={$inspectorExpanded ? 'Collapse editor' : 'Expand editor (side-by-side curves)'}
        >
          {$inspectorExpanded ? '⤡' : '⤢'}
        </button>
        {#if !isPending}
          <button
            class="icon-btn"
            onclick={copy}
            title="Duplicate this action (no bindings carried over)"
          >Copy</button>
          <button class="danger" onclick={remove}>Delete</button>
        {/if}
      </div>
    </header>

    <div class="body" class:expanded={$inspectorExpanded}>
      {#if $inspectorExpanded}
        <aside class="side-col">
          {@render curveBlock()}
        </aside>
      {/if}

    <div class="form">
      <section class="bindings-section top">
        {#if isPending && $pendingNewAction}
          <h4>Binding (pending)</h4>
          <ul class="binding-rows">
            <li class="binding-row pending-row">
              <span class="binding-port">P{$pendingNewAction.binding.port}</span>
              <span class="binding-input" title={$pendingNewAction.binding.input}>
                {humanLabel($pendingNewAction.binding.input)}
                <span class="binding-cat muted">{categoryFor($pendingNewAction.binding.input) ?? ''}</span>
              </span>
              <span class="pending-flag" title="Bound on Apply">new</span>
            </li>
          </ul>
          <p class="muted small">Click Apply to create this action and bind it.  Click Reset to discard.</p>
        {:else}
          <h4>Bindings ({currentBindings.length})</h4>
          {#if currentBindings.length === 0}
            <p class="muted small">No bindings.  Add one below.</p>
          {:else}
            <ul class="binding-rows">
              {#each currentBindings as ref (ref.port + ':' + ref.input)}
                {@const incompat = !isCompatible(ref.input, draft.input_type)}
                <li class="binding-row" class:incompat>
                  <span class="binding-port">P{ref.port}</span>
                  <span class="binding-input" title={ref.input}>
                    {humanLabel(ref.input)}
                    <span class="binding-cat muted">{categoryFor(ref.input) ?? ''}</span>
                  </span>
                  {#if incompat}
                    <span class="incompat-flag" title="Input type changed -- this binding is no longer compatible">!</span>
                  {/if}
                  <button class="unbind" title="Unbind" onclick={() => unbind(ref)}>×</button>
                </li>
              {/each}
            </ul>
          {/if}

          <div class="add-binding">
            <label>
              <span>Port</span>
              <select bind:value={addPort}>
                {#each availablePorts as p (p)}
                  <option value={p}>{p}</option>
                {/each}
              </select>
            </label>
            <label>
              <span>Add input</span>
              <select
                value=""
                disabled={freeInputs.length === 0}
                onchange={(e) => {
                  const v = (e.currentTarget as HTMLSelectElement).value;
                  if (v) addBinding(v);
                  (e.currentTarget as HTMLSelectElement).value = '';
                }}
              >
                <option value="">{freeInputs.length ? '(pick an input)' : '(none compatible)'}</option>
                {#each freeInputs as input (input)}
                  <option value={input}>{humanLabel(input)} · {categoryFor(input)}</option>
                {/each}
              </select>
            </label>
          </div>
        {/if}
      </section>

      <label>
        <span>Group</span>
        <!-- Plain text input -- no `list`/datalist.  The browser's
             datalist dropdown filters options by the current input value,
             which misled users into thinking only the current group
             existed.  The chips below show every known group instead. -->
        <input type="text" bind:value={draft.group} />
        {#if knownGroups.length > 0}
          <div class="group-chips">
            {#each knownGroups as g (g)}
              <button
                type="button"
                class="group-chip"
                class:active={draft.group === g}
                onclick={() => { if (draft) draft.group = g; }}
              >{g}</button>
            {/each}
          </div>
        {/if}
      </label>

      <label>
        <span>Name</span>
        <input type="text" bind:value={draft.name} />
      </label>

      {#if willRename}
        <div class="rename-notice">
          Will rename to <code>{pendingQname}</code> on Apply.
          {#if currentBindings.length > 0}
            {currentBindings.length} binding{currentBindings.length === 1 ? '' : 's'} will update automatically.
          {/if}
        </div>
      {/if}

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
        <select bind:value={draft.trigger_mode} onchange={onTriggerModeChange}>
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

      {#if !$inspectorExpanded}
        {@render curveBlock()}
      {/if}
    </div>
    </div>

    <footer>
      <span class="dirty-hint muted" class:dirty={isDirty}>
        {#if isPending}
          New action · click Apply to create, or Reset to discard
        {:else if isDirty}
          Pending edits · click Apply to commit, or Reset to discard
        {:else}
          No pending edits
        {/if}
      </span>
      <div class="footer-buttons">
        <button onclick={reset} disabled={!isDirty}>{isPending ? 'Cancel' : 'Reset'}</button>
        <button class="primary" onclick={apply} disabled={!isDirty}>{isPending ? 'Create' : 'Apply'}</button>
      </div>
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
  /* Expanded mode lifts the cap so the App grid can give us a side
     column for the curve editor + live preview. */
  .inspector.expanded {
    max-width: none;
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
  .header-actions {
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }
  .icon-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 0.15rem 0.45rem;
    font-size: 1em;
    line-height: 1;
    border-radius: 3px;
    cursor: pointer;
  }
  .icon-btn:hover {
    background: var(--panel);
  }
  /* Two-column layout when expanded: curve+preview on the left, form
     on the right.  Collapsed leaves .body as a passive wrapper so the
     form scrolls as a single column like before. */
  .body {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
  .body.expanded {
    display: grid;
    grid-template-columns: minmax(20rem, 1fr) minmax(20rem, 1fr);
    gap: 0;
  }
  .side-col {
    padding: 0.75rem;
    border-right: 1px solid var(--border);
    background: var(--panel);
    overflow-y: auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .body.expanded .form {
    overflow-y: auto;
    min-height: 0;
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
    flex-direction: column;
    gap: 0.35rem;
    background: var(--panel-2);
    position: sticky;
    bottom: 0;
  }
  .dirty-hint {
    font-size: 0.78em;
    font-style: italic;
  }
  .dirty-hint.dirty {
    color: #ffb84d;
    font-style: normal;
  }
  .footer-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 0.4rem;
  }
  .footer-buttons button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .danger { background: var(--danger); border-color: var(--danger); color: #111; }
  .danger:hover { background: #f07a72; }
  .preview-section {
    border-top: 1px solid var(--border);
    padding-top: 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .preview-section h4 {
    margin: 0;
    font-size: 0.9em;
    color: var(--muted);
    font-weight: 500;
  }
  .bindings-section {
    border-top: 1px solid var(--border);
    padding-top: 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  /* At the top of the inspector the bindings section is the first thing
     in the form -- skip the divider rule so it doesn't double up with
     the header's bottom border. */
  .bindings-section.top {
    border-top: 0;
    padding-top: 0;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 0.25rem;
  }
  .bindings-section h4 {
    margin: 0;
    font-size: 0.9em;
    color: var(--muted);
    font-weight: 500;
  }
  .binding-rows {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .binding-row {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.15rem 0.4rem;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: var(--panel-2);
    font-size: 0.85em;
  }
  .binding-port {
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    font-weight: 600;
    color: #6cb6ff;
    min-width: 1.5rem;
  }
  .binding-input {
    flex: 1;
    display: flex;
    gap: 0.3rem;
    align-items: baseline;
  }
  .binding-cat {
    font-size: 0.78em;
    text-transform: uppercase;
  }
  .binding-row.incompat {
    border-color: rgba(255, 138, 122, 0.6);
  }
  .binding-row.pending-row {
    border-color: rgba(255, 184, 77, 0.6);
    background: rgba(255, 184, 77, 0.08);
  }
  .incompat-flag {
    color: var(--danger, #ff8a7a);
    font-weight: 700;
    font-family: ui-monospace, monospace;
  }
  .pending-flag {
    color: #ffb84d;
    font-size: 0.7em;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.05rem 0.35rem;
    border: 1px solid rgba(255, 184, 77, 0.5);
    border-radius: 3px;
  }
  .group-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-top: 0.25rem;
  }
  .group-chip {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.05rem 0.5rem;
    font-size: 0.78em;
    cursor: pointer;
    color: var(--muted);
  }
  .group-chip:hover {
    background: var(--panel);
    color: var(--text);
  }
  .group-chip.active {
    color: #111;
    background: #6cb6ff;
    border-color: #6cb6ff;
  }
  .unbind {
    background: transparent;
    border: 0;
    color: var(--muted);
    font-size: 1em;
    line-height: 1;
    padding: 0 0.35rem;
    cursor: pointer;
    border-radius: 3px;
  }
  .unbind:hover {
    color: var(--danger, #ff8a7a);
    background: var(--panel);
  }
  .add-binding {
    display: flex;
    gap: 0.5rem;
    align-items: flex-end;
  }
  .add-binding label {
    flex: 1;
    font-size: 0.78em;
  }
  .add-binding label:first-child {
    flex: 0 0 4rem;
  }
  .small {
    font-size: 0.85em;
  }
  .rename-notice {
    background: rgba(255, 184, 77, 0.12);
    border: 1px solid rgba(255, 184, 77, 0.4);
    border-radius: 3px;
    padding: 0.35rem 0.5rem;
    font-size: 0.8em;
    line-height: 1.35;
    color: #ffd680;
  }
  .rename-notice code {
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    background: rgba(0, 0, 0, 0.25);
    padding: 0 0.3rem;
    border-radius: 2px;
    color: #ffe6b3;
  }
</style>
