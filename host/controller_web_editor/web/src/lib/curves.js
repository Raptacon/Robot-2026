// Pure-function port of utils/math/curves.py.
//
// Mathematically identical to the Python implementations.  The parity test
// at host/controller_web_editor/tests/test_curves_parity.py imports this
// file under Node and compares its output point-by-point with the Python
// implementation.  If you change anything here, the matching Python module
// must change too (or vice versa).
//
// Spline math is cubic hermite interpolation, identical to
// wpimath.spline.CubicHermiteSpline.
//
// Written as plain ESM JavaScript with JSDoc types so Node can import it
// without a transform step.  tsconfig.json has allowJs + checkJs enabled,
// so the editor still gets full type-checking from these annotations.

/**
 * @typedef {Object} SplinePoint
 * @property {number} x
 * @property {number} y
 * @property {number} tangent
 */

/**
 * @typedef {Object} SegmentPoint
 * @property {number} x
 * @property {number} y
 */

/**
 * Evaluate one cubic hermite segment at parameter t in [0, 1].
 * @param {number} y0
 * @param {number} m0
 * @param {number} y1
 * @param {number} m1
 * @param {number} dx segment width (x1 - x0)
 * @param {number} t parameter in [0, 1]
 * @returns {number}
 */
export function hermiteEval(y0, m0, y1, m1, dx, t) {
  const t2 = t * t;
  const t3 = t2 * t;
  const h00 = 2 * t3 - 3 * t2 + 1;
  const h10 = t3 - 2 * t2 + t;
  const h01 = -2 * t3 + 3 * t2;
  const h11 = t3 - t2;
  return h00 * y0 + h10 * dx * m0 + h01 * y1 + h11 * dx * m1;
}

/** @returns {SplinePoint[]} */
export function defaultSplinePoints() {
  return [
    { x: -1.0, y: -1.0, tangent: 1.0 },
    { x: 0.0, y: 0.0, tangent: 1.0 },
    { x: 1.0, y: 1.0, tangent: 1.0 },
  ];
}

/**
 * @param {SplinePoint[]} points
 * @param {number} x
 * @returns {number}
 */
export function evaluateSpline(points, x) {
  if (!points || points.length < 2) return x;
  const xMin = points[0].x;
  const xMax = points[points.length - 1].x;
  if (x < xMin) x = xMin;
  if (x > xMax) x = xMax;
  for (let i = 0; i < points.length - 1; i++) {
    const x0 = points[i].x;
    const x1 = points[i + 1].x;
    if (x <= x1 || i === points.length - 2) {
      const dx = x1 - x0;
      if (dx === 0) return points[i].y;
      const t = (x - x0) / dx;
      return hermiteEval(
        points[i].y, points[i].tangent,
        points[i + 1].y, points[i + 1].tangent,
        dx, t,
      );
    }
  }
  return x;
}

/**
 * Estimate dy/dx at x by central difference.
 * @param {SplinePoint[]} points
 * @param {number} x
 * @returns {number}
 */
export function numericalSlope(points, x) {
  const eps = 0.001;
  return (evaluateSpline(points, x + eps) - evaluateSpline(points, x - eps)) / (2 * eps);
}

/** @returns {SegmentPoint[]} */
export function defaultSegmentPoints() {
  return [
    { x: -1.0, y: -1.0 },
    { x: 0.0, y: 0.0 },
    { x: 1.0, y: 1.0 },
  ];
}

/**
 * @param {SegmentPoint[]} points
 * @param {number} x
 * @returns {number}
 */
export function evaluateSegments(points, x) {
  if (!points || points.length < 2) return x;
  const xMin = points[0].x;
  const xMax = points[points.length - 1].x;
  if (x < xMin) x = xMin;
  if (x > xMax) x = xMax;
  for (let i = 0; i < points.length - 1; i++) {
    const x0 = points[i].x;
    const x1 = points[i + 1].x;
    if (x <= x1 || i === points.length - 2) {
      const dx = x1 - x0;
      if (dx === 0) return points[i].y;
      const t = (x - x0) / dx;
      return points[i].y + t * (points[i + 1].y - points[i].y);
    }
  }
  return x;
}

/**
 * Apply deadband with linear rescaling of the remaining range.
 * Mirrors utils/input/shaping.py:apply_deadband (the pure-python fallback,
 * not the wpimath path -- both are mathematically equivalent for these
 * inputs).
 * @param {number} value
 * @param {number} deadband
 * @returns {number}
 */
export function applyDeadband(value, deadband) {
  if (deadband <= 0) return value;
  if (Math.abs(value) < deadband) return 0;
  if (value > 0) return (value - deadband) / (1 - deadband);
  return (value + deadband) / (1 - deadband);
}

/**
 * @typedef {Object} ShapingParams
 * @property {boolean} inversion
 * @property {number} deadband
 * @property {number} scale
 * @property {string} triggerMode
 * @property {SplinePoint[]} [splinePoints]
 * @property {SegmentPoint[]} [segmentPoints]
 */

/**
 * Apply the full shaping pipeline used by the robot's InputFactory for
 * analog actions: invert -> deadband -> curve -> scale.  Slew rate is
 * time-dependent and applied separately in LivePreview, not here.
 *
 * Matches utils/input/shaping.py:build_shaping_pipeline behavior.
 * @param {number} value raw axis value in [-1, 1]
 * @param {ShapingParams} p
 * @returns {number}
 */
export function shape(value, p) {
  // RAW = true passthrough (matches the robot pipeline)
  if (p.triggerMode === 'raw') return value;
  let v = p.inversion ? -value : value;
  v = applyDeadband(v, p.deadband);
  switch (p.triggerMode) {
    case 'scaled':
      break;
    case 'squared':
      v = Math.sign(v) * v * v;
      break;
    case 'segmented':
      v = evaluateSegments(p.segmentPoints ?? defaultSegmentPoints(), v);
      break;
    case 'spline':
      v = evaluateSpline(p.splinePoints ?? defaultSplinePoints(), v);
      break;
    default:
      break;
  }
  return v * p.scale;
}
