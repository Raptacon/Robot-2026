<script lang="ts">
  // Visual editor for analog response curves (spline or piecewise-linear
  // segments).  Reads and writes ActionDefinition.extra.spline_points or
  // extra.segment_points via a `change` callback.
  //
  // Interactions:
  //   left-click empty space:  add a point
  //   drag point:              move it (intermediate: x + y; endpoints: y only)
  //   drag tangent handle:     adjust slope (spline only)
  //   right-click point:       remove it (intermediate only)
  //   Ctrl+Z (editor focused): undo last edit
  //
  // The "Monotonic" toggle clamps y so it never decreases with x (and for
  // splines also clamps tangents to >= 0).  This is a session-local UI
  // constraint -- the stored curve is the regular shape, so the toggle is
  // not persisted in YAML.
  //
  // Undo is local to this editor instance.  Each interaction snapshots
  // the working points before mutating; popping the stack restores the
  // prior state and pushes it through onChange so the LivePreview tracks.

  import {
    defaultSplinePoints,
    defaultSegmentPoints,
    evaluateSpline,
    numericalSlope,
  } from '../lib/curves.js';

  interface SplinePt { x: number; y: number; tangent: number }
  interface SegmentPt { x: number; y: number }
  type AnyPt = SplinePt | SegmentPt;
  type DragKind = { kind: 'point'; idx: number } | { kind: 'handle'; idx: number; side: 'in' | 'out' };

  interface Props {
    mode: 'spline' | 'segments';
    points: AnyPt[];
    onChange: (pts: AnyPt[]) => void;
  }
  let { mode, points, onChange }: Props = $props();

  const W = 360;
  const H = 260;
  const MARGIN = 24;
  const PLOT_W = W - 2 * MARGIN;
  const PLOT_H = H - 2 * MARGIN;
  const MIN_X_GAP = 0.04;
  const POINT_R = 6;
  const HANDLE_R = 4;
  const HANDLE_LEN = 36;

  function dataToCanvas(x: number, y: number): { cx: number; cy: number } {
    return {
      cx: MARGIN + ((x + 1) / 2) * PLOT_W,
      cy: MARGIN + ((1 - y) / 2) * PLOT_H,
    };
  }
  function canvasToData(cx: number, cy: number): { x: number; y: number } {
    return {
      x: ((cx - MARGIN) / PLOT_W) * 2 - 1,
      y: 1 - ((cy - MARGIN) / PLOT_H) * 2,
    };
  }
  function tangentOffset(tangent: number): { dx: number; dy: number } {
    const ppx = PLOT_W / 2;
    const ppy = PLOT_H / 2;
    const dx = ppx;
    const dy = -tangent * ppy;
    const len = Math.hypot(dx, dy);
    if (len < 1e-6) return { dx: HANDLE_LEN, dy: 0 };
    const s = HANDLE_LEN / len;
    return { dx: dx * s, dy: dy * s };
  }
  function offsetToTangent(dx: number, dy: number): number {
    const ppx = PLOT_W / 2;
    const ppy = PLOT_H / 2;
    const ddx = dx / ppx;
    const ddy = -dy / ppy;
    if (Math.abs(ddx) < 1e-6) return ddy > 0 ? 10 : -10;
    return Math.max(-10, Math.min(10, ddy / ddx));
  }

  const isSpline = $derived(mode === 'spline');

  let workingPoints = $state<AnyPt[]>([]);
  let lastSyncedKey = $state('');
  let monotonic = $state(false);
  let undoStack = $state<AnyPt[][]>([]);
  let dragSnapshotPushed = $state(false);
  const MAX_UNDO = 50;

  $effect(() => {
    const incoming = $state.snapshot(points) as AnyPt[];
    const key = JSON.stringify(incoming);
    if (key !== lastSyncedKey) {
      const fallback = isSpline ? defaultSplinePoints() : defaultSegmentPoints();
      const src: AnyPt[] = incoming && incoming.length >= 2 ? incoming : fallback;
      const cleaned: AnyPt[] = src
        .map((p) => isSpline
          ? { x: p.x, y: p.y, tangent: typeof (p as SplinePt).tangent === 'number' ? (p as SplinePt).tangent : 1 }
          : { x: p.x, y: p.y })
        .sort((a, b) => a.x - b.x);
      workingPoints = cleaned;
      lastSyncedKey = JSON.stringify(cleaned);
    }
  });

  // workingPoints is a $state proxy.  structuredClone / JSON.stringify on a
  // proxy can throw or behave inconsistently -- the Svelte 5 docs are
  // explicit about this.  Always run state through $state.snapshot first.
  function snap(): AnyPt[] {
    return $state.snapshot(workingPoints) as AnyPt[];
  }

  function commit(): void {
    const s = snap();
    onChange(s);
    lastSyncedKey = JSON.stringify(s);
  }

  function pushUndo(): void {
    undoStack = [...undoStack, snap()];
    if (undoStack.length > MAX_UNDO) {
      undoStack = undoStack.slice(undoStack.length - MAX_UNDO);
    }
  }

  function popUndo(): void {
    if (undoStack.length === 0) return;
    const prev = undoStack[undoStack.length - 1];
    undoStack = undoStack.slice(0, -1);
    workingPoints = $state.snapshot(prev) as AnyPt[];
    commit();
  }

  // Clamp y of a single point so the sequence stays monotonically
  // non-decreasing.  Called per drag step when `monotonic` is on.
  function clampMonotonicY(idx: number, y: number): number {
    const lo = idx > 0 ? workingPoints[idx - 1].y : -1;
    const hi = idx < workingPoints.length - 1 ? workingPoints[idx + 1].y : 1;
    return Math.max(lo, Math.min(hi, y));
  }

  function enforceMonotonic(): void {
    // Sweep left->right, raising each y to be >= previous.  Cheap fix when
    // toggling the constraint on or when bulk-loading non-monotonic data.
    let prev = -Infinity;
    for (const p of workingPoints) {
      if (p.y < prev) p.y = round3(prev);
      prev = p.y;
    }
    if (isSpline) {
      for (const p of workingPoints) {
        const sp = p as SplinePt;
        if (sp.tangent < 0) sp.tangent = 0;
      }
    }
    workingPoints = [...workingPoints];
  }

  function onMonotonicToggle(): void {
    if (monotonic) {
      pushUndo();
      enforceMonotonic();
      commit();
    }
  }

  const curvePath = $derived.by(() => {
    if (workingPoints.length < 2) return '';
    if (!isSpline) {
      return workingPoints.map((p, i) => {
        const { cx, cy } = dataToCanvas(p.x, Math.max(-1.5, Math.min(1.5, p.y)));
        return `${i === 0 ? 'M' : 'L'}${cx.toFixed(2)},${cy.toFixed(2)}`;
      }).join(' ');
    }
    const xMin = workingPoints[0].x;
    const xMax = workingPoints[workingPoints.length - 1].x;
    const samples = 160;
    const parts: string[] = [];
    for (let i = 0; i <= samples; i++) {
      const x = xMin + ((xMax - xMin) * i) / samples;
      const y = Math.max(-1.5, Math.min(1.5, evaluateSpline(workingPoints as SplinePt[], x)));
      const { cx, cy } = dataToCanvas(x, y);
      parts.push(`${i === 0 ? 'M' : 'L'}${cx.toFixed(2)},${cy.toFixed(2)}`);
    }
    return parts.join(' ');
  });

  let svgEl = $state<SVGSVGElement | null>(null);
  let drag = $state<DragKind | null>(null);

  function svgPoint(ev: PointerEvent | MouseEvent): { cx: number; cy: number } {
    if (!svgEl) return { cx: 0, cy: 0 };
    const ctm = svgEl.getScreenCTM();
    if (!ctm) return { cx: 0, cy: 0 };
    const pt = svgEl.createSVGPoint();
    pt.x = ev.clientX;
    pt.y = ev.clientY;
    const local = pt.matrixTransform(ctm.inverse());
    return { cx: local.x, cy: local.y };
  }

  function hitTest(cx: number, cy: number): DragKind | null {
    if (isSpline) {
      for (let i = 0; i < workingPoints.length; i++) {
        const p = workingPoints[i] as SplinePt;
        const center = dataToCanvas(p.x, p.y);
        const off = tangentOffset(p.tangent);
        if (i < workingPoints.length - 1) {
          if (Math.hypot(cx - (center.cx + off.dx), cy - (center.cy + off.dy)) <= HANDLE_R + 3) {
            return { kind: 'handle', idx: i, side: 'out' };
          }
        }
        if (i > 0) {
          if (Math.hypot(cx - (center.cx - off.dx), cy - (center.cy - off.dy)) <= HANDLE_R + 3) {
            return { kind: 'handle', idx: i, side: 'in' };
          }
        }
      }
    }
    for (let i = 0; i < workingPoints.length; i++) {
      const p = workingPoints[i];
      const { cx: pcx, cy: pcy } = dataToCanvas(p.x, p.y);
      if (Math.hypot(cx - pcx, cy - pcy) <= POINT_R + 3) {
        return { kind: 'point', idx: i };
      }
    }
    return null;
  }

  function isEndpoint(i: number): boolean {
    return i === 0 || i === workingPoints.length - 1;
  }

  function onPointerDown(ev: PointerEvent): void {
    if (ev.button === 2) return;
    const { cx, cy } = svgPoint(ev);
    const hit = hitTest(cx, cy);
    if (hit) {
      drag = hit;
      dragSnapshotPushed = false;
      svgEl?.setPointerCapture(ev.pointerId);
      ev.preventDefault();
      return;
    }
    const { x, y } = canvasToData(cx, cy);
    if (workingPoints.length === 0) return;
    const xLo = workingPoints[0].x + MIN_X_GAP;
    const xHi = workingPoints[workingPoints.length - 1].x - MIN_X_GAP;
    if (x <= xLo || x >= xHi) return;
    for (const p of workingPoints) {
      if (Math.abs(p.x - x) < MIN_X_GAP) return;
    }
    let newY = Math.max(-1, Math.min(1, y));
    if (monotonic) {
      // Find which gap this x falls into and clamp newY between neighbors.
      let leftY = -1, rightY = 1;
      for (let i = 0; i < workingPoints.length - 1; i++) {
        if (x > workingPoints[i].x && x < workingPoints[i + 1].x) {
          leftY = workingPoints[i].y;
          rightY = workingPoints[i + 1].y;
          break;
        }
      }
      newY = Math.max(leftY, Math.min(rightY, newY));
    }
    pushUndo();
    let tangent = isSpline ? round3(numericalSlope(workingPoints as SplinePt[], x)) : 0;
    if (monotonic && isSpline && tangent < 0) tangent = 0;
    const newPt: AnyPt = isSpline
      ? { x: round3(x), y: round3(newY), tangent }
      : { x: round3(x), y: round3(newY) };
    workingPoints = [...workingPoints, newPt].sort((a, b) => a.x - b.x);
    commit();
  }

  function onPointerMove(ev: PointerEvent): void {
    if (!drag) return;
    if (!dragSnapshotPushed) {
      pushUndo();
      dragSnapshotPushed = true;
    }
    const { cx, cy } = svgPoint(ev);
    if (drag.kind === 'point') {
      const { x, y } = canvasToData(cx, cy);
      const i = drag.idx;
      const p = workingPoints[i];
      let newY = Math.max(-1, Math.min(1, y));
      if (monotonic) newY = clampMonotonicY(i, newY);
      p.y = round3(newY);
      if (!isEndpoint(i)) {
        const xLo = workingPoints[i - 1].x + MIN_X_GAP;
        const xHi = workingPoints[i + 1].x - MIN_X_GAP;
        p.x = round3(Math.max(xLo, Math.min(xHi, x)));
      }
      workingPoints = [...workingPoints];
    } else if (drag.kind === 'handle' && isSpline) {
      const p = workingPoints[drag.idx] as SplinePt;
      const center = dataToCanvas(p.x, p.y);
      let dx = cx - center.cx;
      let dy = cy - center.cy;
      if (drag.side === 'in') {
        dx = -dx;
        dy = -dy;
      }
      if (Math.hypot(dx, dy) > 4) {
        let tangent = offsetToTangent(dx, dy);
        if (monotonic && tangent < 0) tangent = 0;
        p.tangent = round3(tangent);
        workingPoints = [...workingPoints];
      }
    }
  }

  function onPointerUp(ev: PointerEvent): void {
    if (drag) {
      const wasDrag = dragSnapshotPushed;
      drag = null;
      dragSnapshotPushed = false;
      svgEl?.releasePointerCapture(ev.pointerId);
      if (wasDrag) commit();
    }
  }

  function onContextMenu(ev: MouseEvent): void {
    ev.preventDefault();
    const { cx, cy } = svgPoint(ev);
    const hit = hitTest(cx, cy);
    if (!hit || hit.kind !== 'point') return;
    if (isEndpoint(hit.idx) || workingPoints.length <= 2) return;
    pushUndo();
    workingPoints = workingPoints.filter((_, i) => i !== hit.idx);
    commit();
  }

  function round3(n: number): number {
    return Math.round(n * 1000) / 1000;
  }

  function resetToLinear(): void {
    pushUndo();
    workingPoints = isSpline ? defaultSplinePoints() : defaultSegmentPoints();
    commit();
  }

  // Editor is "active" for keyboard shortcuts when the cursor is over it
  // or a drag is in progress.  We register a capture-phase Ctrl+Z handler
  // on the window so it runs before App.svelte's global undo handler --
  // otherwise Ctrl+Z would pop the store-level undo stack instead of the
  // curve editor's local one.
  let active = $state(false);

  function onGlobalKeyDown(ev: KeyboardEvent): void {
    if (!active && !drag) return;
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z' && !ev.shiftKey) {
      ev.preventDefault();
      ev.stopPropagation();
      popUndo();
    }
  }

  $effect(() => {
    window.addEventListener('keydown', onGlobalKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', onGlobalKeyDown, { capture: true });
  });

  const renderedPoints = $derived(workingPoints.map((p, i) => ({
    x: p.x,
    y: p.y,
    idx: i,
    canvas: dataToCanvas(p.x, p.y),
    endpoint: isEndpoint(i),
    handle: isSpline ? tangentOffset((p as SplinePt).tangent) : null,
  })));

  const gridXs = [-1, -0.5, 0, 0.5, 1];
  const gridYs = [-1, -0.5, 0, 0.5, 1];
</script>

<div
  class="curve-editor"
  role="group"
  onpointerenter={() => (active = true)}
  onpointerleave={() => (active = false)}
>
  <div class="header">
    <strong>{isSpline ? 'Spline curve' : 'Segmented curve'}</strong>
    <span class="muted">{workingPoints.length} pts</span>
    <label class="mono" title="Force y to be non-decreasing along x">
      <input type="checkbox" bind:checked={monotonic} onchange={onMonotonicToggle} />
      <span>Monotonic</span>
    </label>
    <button onclick={popUndo} disabled={undoStack.length === 0} title="Undo last edit (Ctrl+Z)">Undo</button>
    <button onclick={resetToLinear} title="Reset to y = x">Reset</button>
  </div>
  <svg
    bind:this={svgEl}
    viewBox="0 0 {W} {H}"
    role="application"
    aria-label="{isSpline ? 'Spline' : 'Segment'} curve editor"
    onpointerdown={onPointerDown}
    onpointermove={onPointerMove}
    onpointerup={onPointerUp}
    onpointercancel={onPointerUp}
    oncontextmenu={onContextMenu}
  >
    <rect x={MARGIN} y={MARGIN} width={PLOT_W} height={PLOT_H} class="bg" />

    {#each gridXs as gx (gx)}
      {@const top = dataToCanvas(gx, 1)}
      {@const bot = dataToCanvas(gx, -1)}
      <line x1={top.cx} y1={top.cy} x2={bot.cx} y2={bot.cy} class="grid" class:axis={gx === 0} />
      <text x={top.cx} y={H - 6} class="tick">{gx}</text>
    {/each}
    {#each gridYs as gy (gy)}
      {@const left = dataToCanvas(-1, gy)}
      {@const right = dataToCanvas(1, gy)}
      <line x1={left.cx} y1={left.cy} x2={right.cx} y2={right.cy} class="grid" class:axis={gy === 0} />
      <text x={6} y={left.cy + 3} class="tick">{gy}</text>
    {/each}

    <path d={curvePath} class="curve" />

    {#if isSpline}
      {#each renderedPoints as p (p.idx)}
        <line
          x1={p.canvas.cx - (p.handle?.dx ?? 0)}
          y1={p.canvas.cy - (p.handle?.dy ?? 0)}
          x2={p.canvas.cx + (p.handle?.dx ?? 0)}
          y2={p.canvas.cy + (p.handle?.dy ?? 0)}
          class="handle-line"
        />
        {#if p.idx > 0}
          <circle
            cx={p.canvas.cx - (p.handle?.dx ?? 0)}
            cy={p.canvas.cy - (p.handle?.dy ?? 0)}
            r={HANDLE_R}
            class="handle"
          />
        {/if}
        {#if p.idx < workingPoints.length - 1}
          <circle
            cx={p.canvas.cx + (p.handle?.dx ?? 0)}
            cy={p.canvas.cy + (p.handle?.dy ?? 0)}
            r={HANDLE_R}
            class="handle"
          />
        {/if}
      {/each}
    {/if}

    {#each renderedPoints as p (p.idx)}
      <circle
        cx={p.canvas.cx}
        cy={p.canvas.cy}
        r={POINT_R}
        class="point"
        class:endpoint={p.endpoint}
      />
    {/each}
  </svg>
  <p class="hint muted">
    Click empty area to add · drag points to move · right-click to remove · Ctrl+Z to undo
    {#if isSpline}· drag green handles to change slope{/if}
  </p>
</div>

<style>
  .curve-editor {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .header .mono {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.82em;
    color: var(--muted);
  }
  .header button {
    padding: 0.1rem 0.5rem;
    font-size: 0.82em;
  }
  .header button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  svg {
    width: 100%;
    height: auto;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    touch-action: none;
    user-select: none;
  }
  .bg {
    fill: rgba(255, 255, 255, 0.02);
  }
  .grid {
    stroke: rgba(255, 255, 255, 0.08);
    stroke-width: 1;
  }
  .grid.axis {
    stroke: rgba(255, 255, 255, 0.25);
  }
  .tick {
    fill: var(--muted);
    font-size: 9px;
    text-anchor: middle;
  }
  .curve {
    fill: none;
    stroke: #4f9cf9;
    stroke-width: 2;
  }
  .handle-line {
    stroke: #6a8;
    stroke-width: 1;
    stroke-dasharray: 4 4;
  }
  .handle {
    fill: #8bd0a0;
    stroke: #2a5;
    stroke-width: 1;
    cursor: grab;
  }
  .point {
    fill: #ff7755;
    stroke: #fff;
    stroke-width: 1.5;
    cursor: grab;
  }
  .point.endpoint {
    fill: #ffb84d;
  }
  .hint {
    font-size: 0.78em;
  }
</style>
