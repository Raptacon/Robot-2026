"""Generate match analysis charts as PNG images."""

import io
import logging
from typing import List, Tuple, Dict

logger = logging.getLogger("match_monitor")

try:
    import matplotlib
    matplotlib.use('Agg')  # non-interactive backend
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    _HAS_MATPLOTLIB = True
except ImportError:
    _HAS_MATPLOTLIB = False

# Mode display config: (color, label) — None color means no band drawn
_MODE_COLORS = {
    'disabled':   (None, 'Disabled'),
    'autonomous': ('#3498db', 'Auto'),
    'teleop':     ('#2ecc71', 'Teleop'),
    'test':       ('#f39c12', 'Test'),
}


def _build_mode_spans(mode_transitions: List[dict],
                      duration: float) -> List[Tuple[float, float, str]]:
    """Convert mode transitions into (start, end, mode_name) spans.

    Mode transitions contain entries like:
        {'time_sec': 5.0, 'mode': 'enabled', 'value': True}
        {'time_sec': 5.0, 'mode': 'autonomous', 'value': True}
        {'time_sec': 20.0, 'mode': 'autonomous', 'value': False}
        {'time_sec': 20.0, 'mode': 'enabled', 'value': False}

    Returns spans like: [(0, 5, 'disabled'), (5, 20, 'autonomous'), (20, 150, 'disabled')]
    """
    if not mode_transitions:
        return [(0, duration, 'disabled')]

    # Collect state changes at each timestamp, preserving order within a timestamp
    events: List[Tuple[float, str, bool]] = []
    for t in mode_transitions:
        ts = t['time_sec']
        mode = t['mode']
        # Support both old format (no 'value' key, implied True) and new format
        val = t.get('value', True)
        if mode in ('enabled', 'autonomous', 'test'):
            events.append((ts, mode, val))

    # Sort by timestamp (stable sort preserves order within same timestamp)
    events.sort(key=lambda e: e[0])

    # Build spans by replaying events in order
    spans = []
    prev_time = 0.0
    prev_mode = 'disabled'
    state: Dict[str, bool] = {'enabled': False, 'autonomous': False, 'test': False}

    for ts, mode, val in events:
        state[mode] = val

        # Determine current mode from state
        if not state['enabled']:
            cur_mode = 'disabled'
        elif state['autonomous']:
            cur_mode = 'autonomous'
        elif state['test']:
            cur_mode = 'test'
        else:
            cur_mode = 'teleop'

        # Only emit a span when mode actually changes
        if cur_mode != prev_mode:
            if ts > prev_time:
                spans.append((prev_time, ts, prev_mode))
            prev_mode = cur_mode
            prev_time = ts

    # Final span to end of match
    if prev_time < duration:
        spans.append((prev_time, duration, prev_mode))

    return spans


def _find_last_match_block(spans: List[Tuple[float, float, str]],
                           gap_tolerance: float = 5.0,
                           ) -> Tuple[float, float]:
    """Find the last contiguous block of non-disabled modes.

    Walks backwards from the end of the spans list to find the last active
    block. Disabled gaps shorter than gap_tolerance are bridged (e.g.
    the brief disabled blip between auto and teleop in an FRC match).

    Returns:
        (t_zero, match_end) where t_zero is the start of the first
        auto/teleop/test span in the block, and match_end is the end
        of the last active span.  Falls back to (0, last_span_end) if
        no active spans exist.
    """
    if not spans:
        return (0.0, 0.0)

    # Walk backwards: find last non-disabled span
    i = len(spans) - 1
    while i >= 0 and spans[i][2] == 'disabled':
        i -= 1

    if i < 0:
        # All disabled
        return (0.0, spans[-1][1])

    last_block_end = spans[i][1]
    last_block_start = spans[i][0]

    # Walk backwards: bridge small disabled gaps
    i -= 1
    while i >= 0:
        start, end, mode = spans[i]
        if mode == 'disabled':
            # Check the disabled span's own duration
            gap_duration = end - start
            if gap_duration > gap_tolerance:
                break  # large gap — previous enable cycle
        else:
            # Active span — extend block start
            last_block_start = start
        i -= 1

    # T=0 at first auto/teleop/test in this block, else block start
    t_zero = last_block_start
    for start, _end, mode in spans:
        if start >= last_block_start and mode in ('autonomous', 'teleop', 'test'):
            t_zero = start
            break

    return (t_zero, last_block_end)


def voltage_chart(timeseries: List[Tuple[float, float]],
                  brownout_times: List[float] = None,
                  mode_transitions: List[dict] = None,
                  match_duration: float = None) -> bytes:
    """Generate a battery voltage chart with mode bands and return PNG bytes.

    Args:
        timeseries: List of (time_sec, voltage) tuples.
        brownout_times: Optional list of brownout timestamps (seconds from start).
        mode_transitions: Optional list of {'time_sec': float, 'mode': str} dicts.
        match_duration: Total match duration in seconds.

    Returns:
        PNG image bytes, or empty bytes if matplotlib is unavailable or data is empty.
    """
    if not _HAS_MATPLOTLIB:
        logger.debug("matplotlib not installed — skipping voltage chart")
        return b''
    if not timeseries:
        return b''

    duration = match_duration or (max(t for t, _ in timeseries))

    _PRE_MATCH_BUFFER = 10.0   # seconds before match start to show
    _POST_MATCH_BUFFER = 10.0  # seconds after match end to show

    # Debug: dump mode transitions to help diagnose clipping issues
    if mode_transitions:
        has_false = any(not t.get('value', True) for t in mode_transitions)
        logger.info(f"Chart: {len(mode_transitions)} mode transitions, "
                    f"has_false_values={has_false}, duration={duration:.1f}")
        for t in mode_transitions[:30]:
            logger.info(f"  transition: {t}")

    # Find the last contiguous "match" block
    t_zero = 0.0
    match_end = duration
    if mode_transitions:
        spans = _build_mode_spans(mode_transitions, duration)
        t_zero, match_end = _find_last_match_block(spans)

        logger.info(f"Chart: spans={len(spans)}, t_zero={t_zero:.1f}, "
                    f"match_end={match_end:.1f}")
        for s in spans:
            logger.debug(f"  span: {s[0]:.1f}-{s[1]:.1f} {s[2]}")

    clip_start = max(0.0, t_zero - _PRE_MATCH_BUFFER)
    clip_end = min(duration, match_end + _POST_MATCH_BUFFER)

    # Shift timeseries relative to t_zero, clip to window
    shifted_ts = [(t - t_zero, v) for t, v in timeseries
                  if clip_start <= t <= clip_end]
    if not shifted_ts:
        return b''
    times = [t for t, _ in shifted_ts]
    volts = [v for _, v in shifted_ts]
    x_min = clip_start - t_zero
    x_max = clip_end - t_zero

    fig, ax = plt.subplots(figsize=(8, 3), dpi=120)

    # Mode background bands
    seen_modes = set()
    if mode_transitions:
        spans = _build_mode_spans(mode_transitions, duration)
        for start, end, mode in spans:
            # Shift and clip spans to visible window
            s = max(start - t_zero, x_min)
            e = min(end - t_zero, x_max)
            if e <= s:
                continue
            color, _ = _MODE_COLORS.get(mode, ('#cccccc', mode))
            if color is not None:
                ax.axvspan(s, e, alpha=0.15, color=color, linewidth=0)
                seen_modes.add(mode)

    # Voltage trace
    ax.plot(times, volts, color='#3498db', linewidth=1.0, label='Battery')

    # Reference lines
    ax.axhline(y=12.0, color='#2ecc71', linewidth=1.0, linestyle='--',
               alpha=0.7, label='12V nominal')
    ax.axhline(y=7.0, color='#e74c3c', linewidth=1.0, linestyle='--',
               alpha=0.7, label='7V brownout')

    # Brownout markers
    if brownout_times:
        for bt in brownout_times:
            bt_shifted = bt - t_zero
            if bt_shifted >= clip_start - t_zero:
                ax.axvline(x=bt_shifted, color='#e74c3c', linewidth=0.8,
                           linestyle=':', alpha=0.5)

    ax.set_xlabel('Match Time (s)', fontsize=9)
    ax.set_ylabel('Voltage (V)', fontsize=9)
    ax.set_title('Battery Voltage', fontsize=10, fontweight='bold')
    ax.set_xlim(left=x_min, right=x_max)
    ax.set_ylim(bottom=0, top=14)
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=8)

    # Build legend: voltage items on the left, mode patches on the right
    voltage_legend = ax.legend(loc='lower left', fontsize=7, framealpha=0.8)
    ax.add_artist(voltage_legend)

    if seen_modes:
        mode_patches = [
            Patch(facecolor=_MODE_COLORS[m][0], alpha=0.3, label=_MODE_COLORS[m][1])
            for m in ('disabled', 'autonomous', 'teleop', 'test')
            if m in seen_modes
        ]
        ax.legend(handles=mode_patches, loc='lower right', fontsize=7,
                  framealpha=0.8, title='Mode', title_fontsize=7)

    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.read()
