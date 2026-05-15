<script lang="ts">
  // Live preview of the analog shaping pipeline for the selected action.
  //
  // Input source is either a manual slider or a connected gamepad axis.
  // Shows raw vs shaped values numerically, plots the active curve, and
  // animates a vertical input cursor with a dot at the shaped output.

  import {
    shape,
    defaultSplinePoints,
    defaultSegmentPoints,
  } from '../lib/curves.js';

  interface SplinePt { x: number; y: number; tangent: number }
  interface SegmentPt { x: number; y: number }

  interface Props {
    inversion: boolean;
    deadband: number;
    scale: number;
    slewRate: number;
    triggerMode: string;
    splinePoints?: SplinePt[];
    segmentPoints?: SegmentPt[];
  }
  let {
    inversion,
    deadband,
    scale,
    slewRate,
    triggerMode,
    splinePoints,
    segmentPoints,
  }: Props = $props();

  const W = 320;
  const H = 160;
  const MARGIN = 18;
  const PLOT_W = W - 2 * MARGIN;
  const PLOT_H = H - 2 * MARGIN;

  const yExtent = $derived(Math.max(1, Math.abs(scale)));

  function dataToCanvas(x: number, y: number): { cx: number; cy: number } {
    return {
      cx: MARGIN + ((x + 1) / 2) * PLOT_W,
      cy: MARGIN + ((yExtent - y) / (2 * yExtent)) * PLOT_H,
    };
  }

  let source = $state<'slider' | 'gamepad'>('slider');
  let sliderRaw = $state(0);
  let gamepadIndex = $state(0);
  let axisIndex = $state(0);
  let gamepads = $state<Array<{ index: number; label: string; axes: number }>>([]);

  let rawValue = $state(0);
  let shapedValue = $state(0);
  let slewedValue = $state(0);

  const curvePath = $derived.by(() => {
    const samples = 120;
    const parts: string[] = [];
    for (let i = 0; i <= samples; i++) {
      const x = -1 + (2 * i) / samples;
      const y = Math.max(-yExtent, Math.min(yExtent, shape(x, {
        inversion,
        deadband,
        scale,
        triggerMode,
        splinePoints,
        segmentPoints,
      })));
      const { cx, cy } = dataToCanvas(x, y);
      parts.push(`${i === 0 ? 'M' : 'L'}${cx.toFixed(2)},${cy.toFixed(2)}`);
    }
    return parts.join(' ');
  });

  const pipelineDescription = $derived.by(() => {
    if (triggerMode === 'raw') return 'raw passthrough';
    const parts: string[] = [];
    if (inversion) parts.push('invert');
    if (deadband > 0) parts.push(`deadband(${deadband})`);
    switch (triggerMode) {
      case 'squared': parts.push('squared'); break;
      case 'segmented':
        parts.push(`segments(${(segmentPoints ?? defaultSegmentPoints()).length}pts)`);
        break;
      case 'spline':
        parts.push(`spline(${(splinePoints ?? defaultSplinePoints()).length}pts)`);
        break;
    }
    if (scale !== 1) parts.push(`scale(${scale})`);
    if (slewRate > 0) parts.push(`slew(${slewRate}/s)`);
    return parts.length ? parts.join(' -> ') : 'scaled';
  });

  let rafId: number | null = null;
  let lastTick = 0;

  function refreshGamepadList(): void {
    if (typeof navigator === 'undefined' || !navigator.getGamepads) return;
    const list: Array<{ index: number; label: string; axes: number }> = [];
    for (const gp of navigator.getGamepads()) {
      if (!gp) continue;
      list.push({ index: gp.index, label: gp.id, axes: gp.axes.length });
    }
    gamepads = list;
    if (source === 'gamepad' && !list.find((g) => g.index === gamepadIndex) && list.length > 0) {
      gamepadIndex = list[0].index;
    }
  }

  function tick(now: number): void {
    const dt = Math.max(0.001, (now - lastTick) / 1000);
    lastTick = now;

    let raw: number;
    if (source === 'gamepad') {
      const gp = navigator.getGamepads?.()[gamepadIndex];
      raw = gp && gp.axes[axisIndex] !== undefined ? gp.axes[axisIndex] : 0;
    } else {
      raw = sliderRaw;
    }
    rawValue = raw;
    shapedValue = shape(raw, {
      inversion,
      deadband,
      scale,
      triggerMode,
      splinePoints,
      segmentPoints,
    });
    if (slewRate > 0) {
      const maxStep = slewRate * dt;
      const delta = shapedValue - slewedValue;
      if (Math.abs(delta) <= maxStep) {
        slewedValue = shapedValue;
      } else {
        slewedValue += Math.sign(delta) * maxStep;
      }
    } else {
      slewedValue = shapedValue;
    }
    rafId = requestAnimationFrame(tick);
  }

  $effect(() => {
    refreshGamepadList();
    window.addEventListener('gamepadconnected', refreshGamepadList);
    window.addEventListener('gamepaddisconnected', refreshGamepadList);
    rafId = requestAnimationFrame((t) => {
      lastTick = t;
      tick(t);
    });
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      window.removeEventListener('gamepadconnected', refreshGamepadList);
      window.removeEventListener('gamepaddisconnected', refreshGamepadList);
    };
  });

  const cursorPos = $derived.by(() => {
    const x = Math.max(-1, Math.min(1, rawValue));
    const y = Math.max(-yExtent, Math.min(yExtent, slewedValue));
    return { x, y, ...dataToCanvas(x, y) };
  });

  // Pre-compute axis line endpoints so the template doesn't need free {@const}.
  const axes = $derived.by(() => {
    const xMid = dataToCanvas(0, 0);
    const xLeft = dataToCanvas(-1, 0);
    const xRight = dataToCanvas(1, 0);
    return { xMid, xLeft, xRight };
  });

  const cursorLine = $derived.by(() => {
    const top = dataToCanvas(cursorPos.x, yExtent);
    const bot = dataToCanvas(cursorPos.x, -yExtent);
    return { top, bot };
  });

  function fmt(n: number): string {
    return n.toFixed(3);
  }
</script>

<div class="preview">
  <div class="row">
    <label class="src">
      <span>Source</span>
      <select bind:value={source}>
        <option value="slider">Slider</option>
        <option value="gamepad">Gamepad</option>
      </select>
    </label>
    {#if source === 'gamepad'}
      <label class="gp">
        <span>Pad</span>
        <select bind:value={gamepadIndex}>
          {#if gamepads.length === 0}
            <option value={0}>(none connected)</option>
          {/if}
          {#each gamepads as gp (gp.index)}
            <option value={gp.index}>#{gp.index} {gp.label.slice(0, 24)}</option>
          {/each}
        </select>
      </label>
      <label class="axis">
        <span>Axis</span>
        <input type="number" min="0" max="15" step="1" bind:value={axisIndex} />
      </label>
    {/if}
  </div>

  {#if source === 'slider'}
    <input type="range" min="-1" max="1" step="0.01" bind:value={sliderRaw} />
  {/if}

  <svg viewBox="0 0 {W} {H}" role="img" aria-label="Live shaped-output preview">
    <rect x={MARGIN} y={MARGIN} width={PLOT_W} height={PLOT_H} class="bg" />

    <line x1={axes.xLeft.cx} y1={axes.xLeft.cy} x2={axes.xRight.cx} y2={axes.xRight.cy} class="axis" />
    <line x1={axes.xMid.cx} y1={MARGIN} x2={axes.xMid.cx} y2={H - MARGIN} class="axis" />

    <path d={curvePath} class="curve" />

    <line x1={cursorLine.top.cx} y1={cursorLine.top.cy}
          x2={cursorLine.bot.cx} y2={cursorLine.bot.cy} class="cursor" />
    <circle cx={cursorPos.cx} cy={cursorPos.cy} r={5} class="output-dot" />
  </svg>

  <table class="readout">
    <tbody>
      <tr><th>Raw</th><td>{fmt(rawValue)}</td></tr>
      <tr><th>Shaped</th><td>{fmt(shapedValue)}</td></tr>
      {#if slewRate > 0}
        <tr><th>Slewed</th><td>{fmt(slewedValue)}</td></tr>
      {/if}
    </tbody>
  </table>
  <p class="pipeline muted">{pipelineDescription}</p>
</div>

<style>
  .preview {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .row {
    display: flex;
    gap: 0.5rem;
    align-items: flex-end;
    flex-wrap: wrap;
  }
  .row label {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    font-size: 0.8em;
  }
  .row .axis input {
    width: 4rem;
  }
  input[type='range'] {
    width: 100%;
  }
  svg {
    width: 100%;
    height: auto;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
  }
  .bg {
    fill: rgba(255, 255, 255, 0.02);
  }
  .axis {
    stroke: rgba(255, 255, 255, 0.2);
    stroke-width: 1;
  }
  .curve {
    fill: none;
    stroke: #4f9cf9;
    stroke-width: 2;
  }
  .cursor {
    stroke: rgba(255, 184, 77, 0.55);
    stroke-width: 1;
    stroke-dasharray: 3 3;
  }
  .output-dot {
    fill: #ffb84d;
    stroke: #fff;
    stroke-width: 1.2;
  }
  .readout {
    border-collapse: collapse;
    font-size: 0.85em;
  }
  .readout th {
    text-align: left;
    padding-right: 0.6rem;
    font-weight: 500;
    color: var(--muted);
  }
  .readout td {
    font-variant-numeric: tabular-nums;
  }
  .pipeline {
    font-size: 0.78em;
    font-family: ui-monospace, monospace;
  }
</style>
