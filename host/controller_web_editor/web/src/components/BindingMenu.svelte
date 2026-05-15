<script lang="ts">
  import { config, setBinding, ensureController } from '../lib/store';
  import { ALL_INPUTS, categoryFor, humanLabel, isCompatible } from '../lib/inputs';

  let { port = $bindable(0) } = $props<{ port?: number }>();

  const portKey = $derived(String(port));
  const portsAvailable = $derived(
    Object.keys($config.controllers)
      .map(Number)
      .filter((n) => Number.isFinite(n))
      .sort((a, b) => a - b),
  );

  const bindingsForPort = $derived(
    $config.controllers[portKey]?.bindings ?? {},
  );

  const actionsList = $derived(Object.keys($config.actions).sort());

  function actionType(qname: string): string {
    return $config.actions[qname]?.input_type ?? 'button';
  }

  function compatibleActions(input: string): string[] {
    return actionsList.filter((qn) => {
      const t = $config.actions[qn]?.input_type;
      return t ? isCompatible(input, t) : false;
    });
  }

  function addBinding(input: string, action: string): void {
    if (!action) return;
    ensureController(port);
    const current = bindingsForPort[input] ?? [];
    if (current.includes(action)) return;
    setBinding(port, input, [...current, action]);
  }

  function removeBinding(input: string, action: string): void {
    const current = bindingsForPort[input] ?? [];
    setBinding(
      port,
      input,
      current.filter((a) => a !== action),
    );
  }

  function addController(): void {
    const next = (portsAvailable.at(-1) ?? -1) + 1;
    ensureController(next);
    port = next;
  }
</script>

<section class="binding-menu">
  <header class="row">
    <label class="row">
      <span>Port</span>
      <select bind:value={port}>
        {#each portsAvailable as p (p)}
          <option value={p}>{p}</option>
        {/each}
        {#if portsAvailable.length === 0}
          <option value={0}>0</option>
        {/if}
      </select>
    </label>
    <button onclick={addController}>＋ controller</button>
  </header>

  <div class="rows">
    {#each ALL_INPUTS as input (input)}
      {@const bound = bindingsForPort[input] ?? []}
      {@const compat = compatibleActions(input)}
      <div class="binding-row">
        <div class="input-cell">
          <span class="input-label">{humanLabel(input)}</span>
          <span class="input-cat">{categoryFor(input)}</span>
        </div>
        <div class="bindings-cell">
          {#each bound as qn (qn)}
            <span class="chip">
              {qn}
              <span class="chip-type">({actionType(qn)})</span>
              <button class="chip-x" title="Unbind" onclick={() => removeBinding(input, qn)}>×</button>
            </span>
          {/each}
          <select
            value=""
            disabled={compat.length === 0}
            onchange={(e) => {
              const v = (e.currentTarget as HTMLSelectElement).value;
              if (v) addBinding(input, v);
              (e.currentTarget as HTMLSelectElement).value = '';
            }}
          >
            <option value="">{compat.length ? '+ bind action…' : '(no compatible actions)'}</option>
            {#each compat as qn (qn)}
              <option value={qn} disabled={bound.includes(qn)}>{qn}</option>
            {/each}
          </select>
        </div>
      </div>
    {/each}
  </div>
</section>

<style>
  .binding-menu {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    background: var(--bg);
  }
  header.row {
    padding: 0.5rem 0.75rem;
    gap: 0.75rem;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
  }
  .rows {
    flex: 1;
    overflow-y: auto;
    padding: 0.25rem 0;
  }
  .binding-row {
    display: grid;
    grid-template-columns: 12rem 1fr;
    gap: 0.5rem;
    align-items: center;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--border);
  }
  .input-cell { display: flex; flex-direction: column; }
  .input-label { font-weight: 500; }
  .input-cat { font-size: 0.7em; color: var(--text-dim); text-transform: uppercase; }
  .bindings-cell {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    align-items: center;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.1rem 0.5rem;
    font-size: 0.85em;
  }
  .chip-type { color: var(--text-dim); font-size: 0.85em; }
  .chip-x {
    background: transparent;
    border: 0;
    color: var(--text-dim);
    cursor: pointer;
    padding: 0 0.1rem;
    font-size: 1.1em;
    line-height: 1;
  }
  .chip-x:hover { color: var(--danger); }
</style>
