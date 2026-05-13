<script lang="ts">
  import { onMount } from 'svelte';
  import { config, selectedAction, setBinding, ensureController } from '../lib/store';
  import { isCompatible, humanLabel, categoryFor } from '../lib/inputs';
  import { InputType } from '../lib/types';
  import {
    hitboxes,
    fetchHitboxes,
    saveHitboxes,
    regionCenter,
    effectiveFonts,
    effectiveLabelOffset,
    DEFAULT_FONTS,
    DEFAULT_LABEL_OFFSET,
    type HitShape,
    type HitboxFile,
    type LabelOffset,
    type FontSettings,
  } from '../lib/hitboxes';
  import { draggedAction } from '../lib/dragdrop';
  import controllerSvgUrl from '../assets/xbox-controller.svg';

  // Persist hitbox edits across reloads so tuning work survives refresh.
  // Cleared by the Reset button or by pasting the merged JSON into the
  // source file and reloading.
  const OVERRIDES_KEY = 'controller-editor:hitbox-overrides:v2';

  interface EditOverrides {
    regions: Record<string, Partial<HitShape>>;
    labels: Record<string, LabelOffset>;
    fonts: Partial<FontSettings>;
  }

  function emptyOverrides(): EditOverrides {
    return { regions: {}, labels: {}, fonts: {} };
  }

  function loadOverrides(): EditOverrides {
    try {
      const raw = localStorage.getItem(OVERRIDES_KEY);
      if (!raw) return emptyOverrides();
      const parsed = JSON.parse(raw);
      return {
        regions: parsed?.regions ?? {},
        labels: parsed?.labels ?? {},
        fonts: parsed?.fonts ?? {},
      };
    } catch {
      return emptyOverrides();
    }
  }

  function overrideCount(o: EditOverrides): number {
    return (
      Object.keys(o.regions).length +
      Object.keys(o.labels).length +
      Object.keys(o.fonts).length
    );
  }

  let { port = $bindable(0) } = $props<{ port?: number }>();

  let showHitboxes = $state(true);
  let editMode = $state(false);
  let hoverInput = $state<string | null>(null);
  let hoverScreenX = $state(0);
  let hoverScreenY = $state(0);
  let dragOverInput = $state<string | null>(null);
  let menuFor = $state<string | null>(null);
  let menuX = $state(0);
  let menuY = $state(0);

  // --- Label-display helpers -------------------------------------------
  // Some inputs don't deserve a name label in normal use:
  //  * POV cells are too small to fit text alongside their dpad artwork.
  //  * Stick axes (left_stick_x, etc.) are visually informative with just
  //    "X"/"Y" since the surrounding stick region already names itself.
  function displayInputName(input: string): string {
    if (input.endsWith('_stick_x')) return 'X';
    if (input.endsWith('_stick_y')) return 'Y';
    return input;
  }

  function isStickAxis(input: string): 'x' | 'y' | null {
    if (input.endsWith('_stick_x')) return 'x';
    if (input.endsWith('_stick_y')) return 'y';
    return null;
  }

  function shouldShowNameLabel(input: string, hasBindings: boolean): boolean {
    if (hasBindings) return false;          // action label takes over
    if (categoryFor(input) === 'pov') return false;
    return true;
  }

  // Stack bound qualified names as { group, name } pairs so the SVG can
  // render two lines per action.
  function splitAction(qname: string): { group: string; name: string } {
    const idx = qname.indexOf('.');
    if (idx < 0) return { group: '', name: qname };
    return { group: qname.slice(0, idx), name: qname.slice(idx + 1) };
  }

  // Edit-mode state.  Overrides are merged on top of the base JSON so the
  // user can tweak regions/labels/fonts and then export the result.
  let overrides = $state<EditOverrides>(loadOverrides());
  let editingInput = $state<string | null>(null);
  let copyStatus = $state<string>('');
  let dragState: {
    kind: 'region' | 'label';
    input: string;
    startSvg: { x: number; y: number };
    originalShape?: HitShape;
    originalLabel?: LabelOffset;
  } | null = null;

  $effect(() => {
    try {
      if (overrideCount(overrides) === 0) {
        localStorage.removeItem(OVERRIDES_KEY);
      } else {
        localStorage.setItem(OVERRIDES_KEY, JSON.stringify(overrides));
      }
    } catch {
      /* localStorage may be unavailable; tolerate silently. */
    }
  });

  function effectiveShape(input: string): HitShape {
    const base = $hitboxes?.regions[input];
    if (!base) {
      return { shape: 'rect', x: 0, y: 0, width: 0, height: 0 };
    }
    const ov = overrides.regions[input];
    if (!ov) return base;
    return { ...base, ...ov } as HitShape;
  }

  function currentLabel(input: string): LabelOffset {
    const ov = overrides.labels[input];
    if (ov) return ov;
    return effectiveLabelOffset($hitboxes, input);
  }

  const currentFonts = $derived<FontSettings>({
    input_name:
      overrides.fonts.input_name ?? effectiveFonts($hitboxes).input_name,
    action_label:
      overrides.fonts.action_label ?? effectiveFonts($hitboxes).action_label,
  });

  function mergedHitboxes(): HitboxFile | null {
    if (!$hitboxes) return null;
    const out: HitboxFile = {
      viewBox: $hitboxes.viewBox,
      regions: {},
    };
    if ($hitboxes._note) out._note = $hitboxes._note;
    for (const input of Object.keys($hitboxes.regions)) {
      out.regions[input] = effectiveShape(input);
    }
    // Labels — merge base + overrides; drop entries that match defaults.
    const labels: Record<string, LabelOffset> = {};
    const baseLabels = $hitboxes.labels ?? {};
    const allLabelKeys = new Set([
      ...Object.keys(baseLabels),
      ...Object.keys(overrides.labels),
    ]);
    for (const key of allLabelKeys) {
      const value = overrides.labels[key] ?? baseLabels[key];
      if (!value) continue;
      if (value.dx === DEFAULT_LABEL_OFFSET.dx && value.dy === DEFAULT_LABEL_OFFSET.dy) {
        continue;
      }
      labels[key] = { dx: round1(value.dx), dy: round1(value.dy) };
    }
    if (Object.keys(labels).length > 0) out.labels = labels;

    // Fonts — only emit if any field differs from the default.
    const fonts = currentFonts;
    const baseFonts = effectiveFonts($hitboxes);
    if (
      fonts.input_name !== DEFAULT_FONTS.input_name ||
      fonts.action_label !== DEFAULT_FONTS.action_label ||
      fonts.input_name !== baseFonts.input_name ||
      fonts.action_label !== baseFonts.action_label
    ) {
      out.fonts = { ...fonts };
    }
    return out;
  }

  function screenToSvg(svg: SVGSVGElement, x: number, y: number): { x: number; y: number } {
    const pt = svg.createSVGPoint();
    pt.x = x;
    pt.y = y;
    const ctm = svg.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const t = pt.matrixTransform(ctm.inverse());
    return { x: t.x, y: t.y };
  }

  function getSvg(target: EventTarget | null): SVGSVGElement | null {
    return (target as Element | null)?.closest('svg') as SVGSVGElement | null;
  }

  function onRegionPointerDown(input: string, evt: PointerEvent): void {
    if (!editMode) return;
    evt.stopPropagation();
    evt.preventDefault();
    const svg = getSvg(evt.currentTarget);
    if (!svg) return;
    (evt.currentTarget as Element).setPointerCapture(evt.pointerId);
    editingInput = input;
    const p = screenToSvg(svg, evt.clientX, evt.clientY);
    dragState = {
      kind: 'region',
      input,
      startSvg: p,
      originalShape: structuredClone(effectiveShape(input)),
    };
  }

  function onRegionPointerMove(input: string, evt: PointerEvent): void {
    if (!editMode || !dragState || dragState.input !== input || dragState.kind !== 'region') return;
    const svg = getSvg(evt.currentTarget);
    if (!svg) return;
    const p = screenToSvg(svg, evt.clientX, evt.clientY);
    const dx = p.x - dragState.startSvg.x;
    const dy = p.y - dragState.startSvg.y;
    const orig = dragState.originalShape!;
    const next: Partial<HitShape> = {};
    if (orig.shape === 'circle' || orig.shape === 'ellipse') {
      (next as { cx: number; cy: number }).cx = round1(orig.cx + dx);
      (next as { cx: number; cy: number }).cy = round1(orig.cy + dy);
    } else if (orig.shape === 'rect') {
      (next as { x: number; y: number }).x = round1(orig.x + dx);
      (next as { x: number; y: number }).y = round1(orig.y + dy);
    }
    overrides = {
      ...overrides,
      regions: { ...overrides.regions, [input]: { ...overrides.regions[input], ...next } },
    };
  }

  function onRegionPointerUp(input: string, evt: PointerEvent): void {
    if (dragState?.input === input && dragState.kind === 'region') {
      try {
        (evt.currentTarget as Element).releasePointerCapture(evt.pointerId);
      } catch { /* pointer already released */ }
      dragState = null;
    }
  }

  function onLabelPointerDown(input: string, evt: PointerEvent): void {
    if (!editMode) return;
    evt.stopPropagation();
    evt.preventDefault();
    const svg = getSvg(evt.currentTarget);
    if (!svg) return;
    (evt.currentTarget as Element).setPointerCapture(evt.pointerId);
    editingInput = input;
    const p = screenToSvg(svg, evt.clientX, evt.clientY);
    dragState = {
      kind: 'label',
      input,
      startSvg: p,
      originalLabel: { ...currentLabel(input) },
    };
  }

  function onLabelPointerMove(input: string, evt: PointerEvent): void {
    if (!editMode || !dragState || dragState.input !== input || dragState.kind !== 'label') return;
    const svg = getSvg(evt.currentTarget);
    if (!svg) return;
    const p = screenToSvg(svg, evt.clientX, evt.clientY);
    const dx = p.x - dragState.startSvg.x;
    const dy = p.y - dragState.startSvg.y;
    const orig = dragState.originalLabel!;
    overrides = {
      ...overrides,
      labels: {
        ...overrides.labels,
        [input]: { dx: round1(orig.dx + dx), dy: round1(orig.dy + dy) },
      },
    };
  }

  function onLabelPointerUp(input: string, evt: PointerEvent): void {
    if (dragState?.input === input && dragState.kind === 'label') {
      try {
        (evt.currentTarget as Element).releasePointerCapture(evt.pointerId);
      } catch { /* pointer already released */ }
      dragState = null;
    }
  }

  function round1(v: number): number {
    return Math.round(v * 10) / 10;
  }

  function copyJsonToClipboard(): void {
    const merged = mergedHitboxes();
    if (!merged) return;
    const text = JSON.stringify(merged, null, 2);
    navigator.clipboard
      .writeText(text)
      .then(() => {
        copyStatus = 'Copied to clipboard';
        setTimeout(() => (copyStatus = ''), 4000);
      })
      .catch((e) => {
        copyStatus = `Copy failed: ${e.message}`;
        setTimeout(() => (copyStatus = ''), 4000);
      });
  }

  // POST the merged hitboxes to the server so they become the canonical
  // defaults for future sessions on any machine.
  async function saveAsDefaults(): Promise<void> {
    const merged = mergedHitboxes();
    if (!merged) return;
    copyStatus = 'Saving…';
    try {
      await saveHitboxes(merged);
      overrides = emptyOverrides();
      copyStatus = 'Saved as defaults';
      setTimeout(() => (copyStatus = ''), 4000);
    } catch (e) {
      copyStatus = `Save failed: ${(e as Error).message}`;
      setTimeout(() => (copyStatus = ''), 6000);
    }
  }

  onMount(() => {
    fetchHitboxes().catch((e) => {
      copyStatus = `Load failed: ${(e as Error).message}`;
    });
  });

  // Anchor-based grid alignment for the 8 POV hitboxes.  Uses pov_up,
  // pov_up_right, pov_right, pov_down_right as the source of truth for the
  // grid axes — the other 5 are derived so rows/columns line up exactly.
  function snapPovGrid(): void {
    const anchorUp = effectiveShape('pov_up');
    const anchorUpRight = effectiveShape('pov_up_right');
    const anchorRight = effectiveShape('pov_right');
    const anchorDownRight = effectiveShape('pov_down_right');
    const centerX = regionCenter(anchorUp).x;
    const rightX = regionCenter(anchorUpRight).x;
    const topY = regionCenter(anchorUp).y;
    const midY = regionCenter(anchorRight).y;
    const bottomY = regionCenter(anchorDownRight).y;
    const leftX = 2 * centerX - rightX;

    const targets: Record<string, { x: number; y: number }> = {
      pov_up_left:    { x: leftX,   y: topY },
      pov_up:         { x: centerX, y: topY },
      pov_up_right:   { x: rightX,  y: topY },
      pov_left:       { x: leftX,   y: midY },
      pov_right:      { x: rightX,  y: midY },
      pov_down_left:  { x: leftX,   y: bottomY },
      pov_down:       { x: centerX, y: bottomY },
      pov_down_right: { x: rightX,  y: bottomY },
    };

    const nextRegions = { ...overrides.regions };
    for (const [name, c] of Object.entries(targets)) {
      const shape = effectiveShape(name);
      if (shape.shape === 'rect') {
        nextRegions[name] = {
          ...nextRegions[name],
          x: round1(c.x - shape.width / 2),
          y: round1(c.y - shape.height / 2),
        };
      } else {
        nextRegions[name] = {
          ...nextRegions[name],
          cx: round1(c.x),
          cy: round1(c.y),
        };
      }
    }
    overrides = { ...overrides, regions: nextRegions };
  }

  function resetOverrides(): void {
    if (overrideCount(overrides) === 0) return;
    if (!confirm('Discard all unsaved hitbox edits? (also clears the autosaved copy)')) return;
    overrides = emptyOverrides();
    editingInput = null;
  }

  function setFont(field: keyof FontSettings, value: number): void {
    overrides = {
      ...overrides,
      fonts: { ...overrides.fonts, [field]: value },
    };
  }

  const portKey = $derived(String(port));
  const portsAvailable = $derived(
    Object.keys($config.controllers)
      .map(Number)
      .filter((n) => Number.isFinite(n))
      .sort((a, b) => a - b),
  );

  const bindingsForPort = $derived($config.controllers[portKey]?.bindings ?? {});

  function actionsForInput(input: string): string[] {
    return bindingsForPort[input] ?? [];
  }

  function compatibleActions(input: string): string[] {
    return Object.keys($config.actions)
      .filter((qn) => {
        const t = $config.actions[qn]?.input_type;
        return t ? isCompatible(input, t) : false;
      })
      .sort();
  }

  function inputIsCompatibleWith(input: string, qname: string | null): boolean {
    if (!qname) return false;
    const t = $config.actions[qname]?.input_type;
    return t ? isCompatible(input, t) : false;
  }

  function selectedHighlights(input: string): boolean {
    return $selectedAction !== null && actionsForInput(input).includes($selectedAction);
  }

  function bindAction(input: string, qname: string): void {
    ensureController(port);
    const current = actionsForInput(input);
    if (current.includes(qname)) return;
    setBinding(port, input, [...current, qname]);
  }

  function unbindAction(input: string, qname: string): void {
    const current = actionsForInput(input);
    setBinding(port, input, current.filter((a) => a !== qname));
  }

  function openMenu(input: string, evt: MouseEvent): void {
    evt.stopPropagation();
    menuFor = input;
    const target = evt.currentTarget as Element;
    const r = target.getBoundingClientRect();
    menuX = r.left + r.width / 2;
    menuY = r.bottom;
  }

  function closeMenu(): void {
    menuFor = null;
  }

  function onDragOver(input: string, evt: DragEvent): void {
    const qname = $draggedAction;
    if (!qname || !inputIsCompatibleWith(input, qname)) return;
    evt.preventDefault(); // signal "drop allowed"
    dragOverInput = input;
  }

  function onDragLeave(input: string): void {
    if (dragOverInput === input) dragOverInput = null;
  }

  function onDrop(input: string, evt: DragEvent): void {
    evt.preventDefault();
    const qname = $draggedAction;
    dragOverInput = null;
    draggedAction.set(null);
    if (!qname || !inputIsCompatibleWith(input, qname)) return;
    bindAction(input, qname);
  }

  function addController(): void {
    const next = (portsAvailable.at(-1) ?? -1) + 1;
    ensureController(next);
    port = next;
  }

  function shapeAttrs(s: HitShape): Record<string, number> {
    const { shape: _shape, ...rest } = s as HitShape & { shape: string };
    return rest as Record<string, number>;
  }

  function shapeEl(s: HitShape): 'circle' | 'ellipse' | 'rect' {
    return s.shape;
  }

  // Map dragged-action type to per-region styling so users see at a glance
  // which inputs accept the drop.
  function compatClass(input: string): string {
    const qname = $draggedAction;
    if (!qname) return '';
    return inputIsCompatibleWith(input, qname) ? 'compat' : 'incompat';
  }
</script>

<svelte:window onclick={closeMenu} />

<section class="controller-view">
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
    <span class="spacer"></span>
    <label class="row">
      <input type="checkbox" bind:checked={showHitboxes} />
      <span>Show hit regions</span>
    </label>
    <label class="row">
      <input
        type="checkbox"
        bind:checked={editMode}
        onchange={() => { if (!editMode) editingInput = null; }}
      />
      <span>Edit hit regions</span>
    </label>
    {#if editMode}
      <label class="row font-control" title="Font size for the per-region input name labels">
        <span>Name</span>
        <input
          type="number"
          min="4"
          max="20"
          step="0.5"
          value={currentFonts.input_name}
          onchange={(e) => setFont('input_name', Number((e.currentTarget as HTMLInputElement).value))}
        />
      </label>
      <label class="row font-control" title="Font size for bound-action labels">
        <span>Action</span>
        <input
          type="number"
          min="4"
          max="24"
          step="0.5"
          value={currentFonts.action_label}
          onchange={(e) => setFont('action_label', Number((e.currentTarget as HTMLInputElement).value))}
        />
      </label>
      <button
        onclick={snapPovGrid}
        title="Align all 8 POV hitboxes into a 3×3 grid using pov_up, pov_up_right, pov_right, pov_down_right as anchors"
      >
        Snap POV grid
      </button>
      <button
        class="primary"
        onclick={saveAsDefaults}
        disabled={!$hitboxes}
        title="Write the current positions to the server-side JSON so every future launch uses them"
      >
        Save as defaults
      </button>
      <button onclick={copyJsonToClipboard} title="Copy hitbox JSON to clipboard">
        Copy JSON
      </button>
      <button
        onclick={resetOverrides}
        disabled={overrideCount(overrides) === 0}
        title="Discard unsaved edits"
      >
        Reset
      </button>
    {/if}
    {#if copyStatus}
      <span class="copy-status">{copyStatus}</span>
    {/if}
    {#if editMode && overrideCount(overrides) > 0}
      <span class="muted" style="font-size: 0.8em;">
        {overrideCount(overrides)} unsaved (autosaved locally)
      </span>
    {/if}
  </header>

  <div class="canvas">
    {#if !$hitboxes}
      <p class="muted">Loading hit regions…</p>
    {:else}
    <svg viewBox={$hitboxes.viewBox} preserveAspectRatio="xMidYMid meet">
      <defs>
        <!-- Double-ended axis arrow.  `context-stroke` makes the marker
             fill follow the line's stroke colour so the arrowheads track
             the same hover/highlight states as everything else. -->
        <marker
          id="axis-arrow-head"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="5"
          markerHeight="5"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
        </marker>
      </defs>
      <!-- Controller artwork -->
      <image href={controllerSvgUrl} x="0" y="0" width="744" height="500" />

      <!-- Hit regions -->
      {#each Object.keys($hitboxes.regions) as input (input)}
        {@const shape = effectiveShape(input)}
        {@const center = regionCenter(shape)}
        {@const labels = actionsForInput(input)}
        {@const hovered = hoverInput === input}
        {@const draggingOver = dragOverInput === input}
        {@const highlighted = selectedHighlights(input)}
        {@const isEditing = editMode && editingInput === input}
        {@const isOverridden = overrides.regions[input] !== undefined || overrides.labels[input] !== undefined}
        {@const axis = isStickAxis(input)}
        <g
          class="hit {compatClass(input)}"
          class:visible={showHitboxes || hovered || draggingOver || highlighted || labels.length > 0}
          class:is-axis={axis !== null}
          class:hovered
          class:dragging-over={draggingOver}
          class:highlighted
          class:edit-mode={editMode}
          class:editing={isEditing}
          class:overridden={isOverridden}
          role="button"
          tabindex="0"
          aria-label={humanLabel(input)}
          onmouseenter={(e: MouseEvent) => {
            hoverInput = input;
            hoverScreenX = e.clientX;
            hoverScreenY = e.clientY;
          }}
          onmousemove={(e: MouseEvent) => {
            if (hoverInput === input) {
              hoverScreenX = e.clientX;
              hoverScreenY = e.clientY;
            }
          }}
          onmouseleave={() => {
            if (hoverInput === input) hoverInput = null;
          }}
          onclick={(e: MouseEvent) => {
            if (editMode) {
              e.stopPropagation();
              editingInput = input;
              return;
            }
            openMenu(input, e);
          }}
          onkeydown={(e: KeyboardEvent) => {
            if (editMode) return;
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              openMenu(input, e as unknown as MouseEvent);
            }
          }}
          onpointerdown={(e: PointerEvent) => onRegionPointerDown(input, e)}
          onpointermove={(e: PointerEvent) => onRegionPointerMove(input, e)}
          onpointerup={(e: PointerEvent) => onRegionPointerUp(input, e)}
          onpointercancel={(e: PointerEvent) => onRegionPointerUp(input, e)}
          ondragover={(e: DragEvent) => onDragOver(input, e)}
          ondragleave={() => onDragLeave(input)}
          ondrop={(e: DragEvent) => onDrop(input, e)}
        >
          <svelte:element this={shapeEl(shape)} {...shapeAttrs(shape)} />
          {#if axis && shape.shape === 'rect'}
            {@const inset = 4}
            {@const x1 = axis === 'x' ? shape.x + inset : shape.x + shape.width / 2}
            {@const y1 = axis === 'x' ? shape.y + shape.height / 2 : shape.y + inset}
            {@const x2 = axis === 'x' ? shape.x + shape.width - inset : shape.x + shape.width / 2}
            {@const y2 = axis === 'x' ? shape.y + shape.height / 2 : shape.y + shape.height - inset}
            <line
              class="axis-arrow"
              {x1}
              {y1}
              {x2}
              {y2}
              marker-start="url(#axis-arrow-head)"
              marker-end="url(#axis-arrow-head)"
            />
          {/if}
          {#if (showHitboxes || editMode) && shouldShowNameLabel(input, labels.length > 0)}
            <text
              x={center.x}
              y={center.y + currentFonts.input_name * 0.4}
              class="name-label"
              text-anchor="middle"
              style:font-size="{currentFonts.input_name}px"
            >
              {displayInputName(input)}
            </text>
          {/if}
          {#if isEditing}
            <circle cx={center.x} cy={center.y} r="3" class="edit-handle" />
            <text
              x={center.x}
              y={center.y + 18}
              class="coord-label"
              text-anchor="middle"
            >
              {Math.round(center.x)}, {Math.round(center.y)}
            </text>
          {/if}
        </g>
        {@const labelOffset = currentLabel(input)}
        {@const labelHasBindings = labels.length > 0}
        {@const splits = labels.map(splitAction)}
        {@const groupLine = splits.map((s) => s.group).filter(Boolean).join(' · ')}
        {@const nameLine = splits.map((s) => s.name).join(' · ')}
        {#if labelHasBindings || editMode}
          <g
            class="action-label-group"
            class:edit-mode={editMode}
            class:placeholder={!labelHasBindings}
            onpointerdown={(e: PointerEvent) => onLabelPointerDown(input, e)}
            onpointermove={(e: PointerEvent) => onLabelPointerMove(input, e)}
            onpointerup={(e: PointerEvent) => onLabelPointerUp(input, e)}
            onpointercancel={(e: PointerEvent) => onLabelPointerUp(input, e)}
            aria-hidden="true"
          >
            {#if editMode}
              <!-- Leader line so the user can tell which region a label
                   belongs to once it has been dragged away. -->
              <line
                x1={center.x}
                y1={center.y}
                x2={center.x + labelOffset.dx}
                y2={center.y + labelOffset.dy}
                class="leader"
              />
            {/if}
            <text
              x={center.x + labelOffset.dx}
              y={center.y + labelOffset.dy}
              class="label"
              class:label-placeholder={!labelHasBindings}
              text-anchor="middle"
              style:font-size="{currentFonts.action_label}px"
            >
              {#if !labelHasBindings}
                <tspan x={center.x + labelOffset.dx} dy="0.32em">{input}</tspan>
              {:else if groupLine}
                <!-- Balanced around anchor so the two-line block reads as
                     vertically centered at center + labelOffset. -->
                <tspan x={center.x + labelOffset.dx} dy="-0.15em" class="action-group">{groupLine}</tspan>
                <tspan x={center.x + labelOffset.dx} dy="1.0em" class="action-name">{nameLine}</tspan>
              {:else}
                <tspan x={center.x + labelOffset.dx} dy="0.32em" class="action-name">{nameLine}</tspan>
              {/if}
            </text>
          </g>
        {/if}
      {/each}
    </svg>
    {/if}
  </div>

  {#if hoverInput && !menuFor && !editMode}
    {@const hb = actionsForInput(hoverInput)}
    {@const cat = categoryFor(hoverInput)}
    <div
      class="tooltip"
      style:left="{hoverScreenX + 14}px"
      style:top="{hoverScreenY + 14}px"
    >
      <div class="tooltip-title">
        <strong>{humanLabel(hoverInput)}</strong>
        {#if cat}<span class="muted">·</span><span class="muted">{cat}</span>{/if}
      </div>
      <div class="tooltip-sub muted">{hoverInput}</div>
      {#if hb.length > 0}
        <ul class="tooltip-actions">
          {#each hb as qn (qn)}
            <li>{qn}</li>
          {/each}
        </ul>
      {:else}
        <div class="muted tooltip-empty">no actions bound</div>
      {/if}
    </div>
  {/if}

  {#if menuFor}
    {@const m = menuFor}
    {@const compat = compatibleActions(m)}
    {@const bound = actionsForInput(m)}
    <div
      class="menu"
      style:left="{menuX}px"
      style:top="{menuY}px"
      onclick={(e) => e.stopPropagation()}
      onkeydown={() => {}}
      role="menu"
      tabindex="-1"
    >
      <header>
        <strong>{humanLabel(m)}</strong>
        <span class="muted">{categoryFor(m)}</span>
      </header>
      {#if bound.length > 0}
        <section>
          <p class="muted small">Bound:</p>
          {#each bound as qn (qn)}
            <button class="menu-row" onclick={() => unbindAction(m, qn)}>
              <span>{qn}</span>
              <span class="muted small">remove ×</span>
            </button>
          {/each}
        </section>
      {/if}
      <section>
        <p class="muted small">Bind action:</p>
        {#if compat.length === 0}
          <p class="muted small">No compatible actions defined.</p>
        {/if}
        {#each compat as qn (qn)}
          {@const already = bound.includes(qn)}
          <button
            class="menu-row"
            disabled={already}
            onclick={() => {
              bindAction(m, qn);
              closeMenu();
            }}
          >
            <span>{qn}</span>
            <span class="muted small">
              {$config.actions[qn]?.input_type}
            </span>
          </button>
        {/each}
      </section>
    </div>
  {/if}
</section>

<style>
  .controller-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg);
  }
  header.row {
    padding: 0.5rem 0.75rem;
    gap: 0.75rem;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
  }
  .spacer { flex: 1; }
  .canvas {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem;
    overflow: auto;
  }
  svg {
    width: 100%;
    height: 100%;
    max-width: 900px;
    max-height: 100%;
  }

  /* Hit region defaults: faint outline so positions can be tuned at a glance. */
  .hit {
    cursor: pointer;
  }
  .hit > :global(circle),
  .hit > :global(ellipse),
  .hit > :global(rect) {
    fill: rgba(60, 120, 220, 0.06);
    stroke: rgba(45, 110, 210, 0.9);
    stroke-width: 1.75;
    stroke-dasharray: 3 2;
    transition: fill 0.1s, stroke 0.1s;
  }
  /* Stick axes use a double-ended arrow instead of a rect outline so the
     visual reads "axis of motion" rather than "rectangular zone". */
  .hit.is-axis > :global(rect) {
    fill: rgba(0, 0, 0, 0.001); /* near-transparent — keeps pointer events */
    stroke: none;
  }
  .axis-arrow {
    fill: none;
    stroke: rgba(45, 110, 210, 0.9);
    stroke-width: 1.75;
    stroke-dasharray: 3 2;
    pointer-events: none;
    transition: stroke 0.1s, stroke-width 0.1s;
  }
  .hit.visible .axis-arrow {
    stroke: rgba(79, 156, 249, 0.95);
    stroke-width: 1.75;
    stroke-dasharray: none;
  }
  .hit.hovered .axis-arrow {
    stroke: rgba(79, 156, 249, 1);
    stroke-width: 2.25;
    stroke-dasharray: none;
  }
  .hit.highlighted .axis-arrow {
    stroke: rgba(107, 191, 107, 1);
    stroke-width: 2.25;
    stroke-dasharray: none;
  }
  .hit.compat .axis-arrow {
    stroke: rgba(107, 191, 107, 0.85);
    stroke-dasharray: none;
  }
  .hit.incompat .axis-arrow {
    stroke: rgba(120, 120, 120, 0.4);
  }
  .hit.dragging-over .axis-arrow {
    stroke: rgba(107, 191, 107, 1);
    stroke-width: 2.5;
    stroke-dasharray: none;
  }
  .hit.editing .axis-arrow {
    stroke: rgba(255, 200, 80, 1);
    stroke-width: 2.25;
    stroke-dasharray: none;
  }
  .hit.visible > :global(circle),
  .hit.visible > :global(ellipse),
  .hit.visible > :global(rect) {
    fill: rgba(79, 156, 249, 0.14);
    stroke: rgba(79, 156, 249, 0.9);
    stroke-width: 1.5;
    stroke-dasharray: none;
  }
  .hit.hovered > :global(circle),
  .hit.hovered > :global(ellipse),
  .hit.hovered > :global(rect) {
    fill: rgba(79, 156, 249, 0.25);
    stroke: rgba(79, 156, 249, 0.9);
  }
  .hit.highlighted > :global(circle),
  .hit.highlighted > :global(ellipse),
  .hit.highlighted > :global(rect) {
    fill: rgba(107, 191, 107, 0.3);
    stroke: rgba(107, 191, 107, 0.9);
  }
  .hit.compat > :global(circle),
  .hit.compat > :global(ellipse),
  .hit.compat > :global(rect) {
    fill: rgba(107, 191, 107, 0.18);
    stroke: rgba(107, 191, 107, 0.7);
  }
  .hit.incompat > :global(circle),
  .hit.incompat > :global(ellipse),
  .hit.incompat > :global(rect) {
    fill: rgba(120, 120, 120, 0.08);
    stroke: rgba(120, 120, 120, 0.3);
  }
  .hit.dragging-over > :global(circle),
  .hit.dragging-over > :global(ellipse),
  .hit.dragging-over > :global(rect) {
    fill: rgba(107, 191, 107, 0.45);
    stroke: rgba(107, 191, 107, 1);
  }
  .hit.edit-mode { cursor: grab; }
  .hit.edit-mode.editing { cursor: grabbing; }
  .hit.editing > :global(circle),
  .hit.editing > :global(ellipse),
  .hit.editing > :global(rect) {
    fill: rgba(255, 200, 80, 0.25);
    stroke: rgba(255, 200, 80, 1);
    stroke-width: 2;
    stroke-dasharray: none;
  }
  .hit.overridden > :global(circle),
  .hit.overridden > :global(ellipse),
  .hit.overridden > :global(rect) {
    stroke: rgba(255, 200, 80, 0.9);
    stroke-dasharray: none;
  }
  .edit-handle {
    fill: rgba(255, 200, 80, 1);
    stroke: rgba(0, 0, 0, 0.7);
    stroke-width: 0.75;
    pointer-events: none;
  }
  .coord-label {
    font-size: 7px;
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    fill: rgba(255, 200, 80, 1);
    paint-order: stroke;
    stroke: rgba(0, 0, 0, 0.8);
    stroke-width: 2px;
    pointer-events: none;
  }
  .copy-status {
    font-size: 0.85em;
    color: var(--ok);
    margin-left: 0.5rem;
  }

  .label {
    font-size: 10px;
    fill: var(--text);
    paint-order: stroke;
    stroke: rgba(0, 0, 0, 0.8);
    stroke-width: 3.5px;
    stroke-linejoin: round;
    pointer-events: none;
  }
  .name-label {
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    fill: rgba(190, 190, 200, 0.7);
    paint-order: stroke;
    stroke: rgba(0, 0, 0, 0.6);
    stroke-width: 2px;
    stroke-linejoin: round;
    pointer-events: none;
  }

  .action-label-group {
    pointer-events: none;
  }
  .action-label-group.edit-mode {
    pointer-events: auto;
    cursor: grab;
  }
  /* Placeholder shown in edit mode where a region has no binding yet —
     significantly greyer than a real action label so the eye reads it
     as "drop something here" rather than as actual content. */
  .label-placeholder {
    opacity: 0.35;
    fill: rgba(160, 160, 170, 0.6);
    stroke: rgba(0, 0, 0, 0.5);
    stroke-width: 2px;
  }
  /* Bound action labels: warm amber to stand out against the grey
     controller artwork and the dim name-label text.  Group line is the
     same hue but dimmer so the action name dominates the read. */
  .action-group {
    fill: #ffb84d;
    font-weight: 500;
    font-size: 0.72em;
    opacity: 0.85;
  }
  .action-name {
    fill: #ffd680;
    font-weight: 700;
  }
  .leader {
    stroke: rgba(255, 200, 80, 0.65);
    stroke-width: 0.6;
    stroke-dasharray: 2 2;
    pointer-events: none;
  }

  .tooltip {
    position: fixed;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.4rem 0.55rem;
    box-shadow: 0 4px 14px #0009;
    pointer-events: none;
    z-index: 20;
    font-size: 0.85em;
    max-width: 18rem;
  }
  .tooltip-title { display: flex; gap: 0.35rem; align-items: baseline; }
  .tooltip-sub { font-size: 0.8em; font-family: ui-monospace, "SF Mono", Consolas, monospace; }
  .tooltip-actions {
    list-style: none;
    margin: 0.3rem 0 0;
    padding: 0;
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    font-size: 0.9em;
  }
  .tooltip-actions li { padding: 0.05rem 0; }
  .tooltip-empty { font-style: italic; margin-top: 0.2rem; }

  .font-control {
    gap: 0.3rem;
    font-size: 0.85em;
  }
  .font-control input {
    width: 4rem;
  }

  .menu {
    position: fixed;
    transform: translate(-50%, 0.25rem);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.5rem;
    min-width: 14rem;
    max-height: 60vh;
    overflow-y: auto;
    box-shadow: 0 8px 24px #000a;
    z-index: 10;
  }
  .menu header {
    display: flex;
    gap: 0.5rem;
    align-items: baseline;
    margin-bottom: 0.4rem;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid var(--border);
  }
  .menu section { margin-top: 0.3rem; }
  .menu .small { font-size: 0.8em; }
  .menu p { margin: 0.25rem 0; }
  .menu-row {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    width: 100%;
    background: transparent;
    border: 0;
    border-radius: 3px;
    padding: 0.3rem 0.4rem;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }
  .menu-row:hover:not(:disabled) { background: var(--panel); }
</style>
