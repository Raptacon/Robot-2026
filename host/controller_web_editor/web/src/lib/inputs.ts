// Xbox input vocabulary — mirrors utils/input/xbox_map.py.

import { InputType } from './types';

export type InputCategory = 'button' | 'axis' | 'pov' | 'output';

export const BUTTON_INPUTS = [
  'a_button',
  'b_button',
  'x_button',
  'y_button',
  'left_bumper',
  'right_bumper',
  'back_button',
  'start_button',
  'left_stick_button',
  'right_stick_button',
] as const;

export const AXIS_INPUTS = [
  'left_stick_x',
  'left_stick_y',
  'right_stick_x',
  'right_stick_y',
  'left_trigger',
  'right_trigger',
] as const;

export const POV_INPUTS = [
  'pov_up',
  'pov_up_right',
  'pov_right',
  'pov_down_right',
  'pov_down',
  'pov_down_left',
  'pov_left',
  'pov_up_left',
] as const;

export const OUTPUT_INPUTS = [
  'rumble_left',
  'rumble_right',
  'rumble_both',
] as const;

export const TRIGGER_INPUTS = new Set(['left_trigger', 'right_trigger']);

const _CATEGORY: Record<string, InputCategory> = {};
for (const n of BUTTON_INPUTS) _CATEGORY[n] = 'button';
for (const n of AXIS_INPUTS) _CATEGORY[n] = 'axis';
for (const n of POV_INPUTS) _CATEGORY[n] = 'pov';
for (const n of OUTPUT_INPUTS) _CATEGORY[n] = 'output';

export function categoryFor(input: string): InputCategory | undefined {
  return _CATEGORY[input];
}

// Whether an action with the given InputType is allowed on the input.
export function isCompatible(input: string, type: InputType): boolean {
  const cat = categoryFor(input);
  if (!cat) return false;
  switch (cat) {
    case 'button':
    case 'pov':
      return type === InputType.Button || type === InputType.VirtualAnalog;
    case 'axis':
      if (type === InputType.Analog) return true;
      // Triggers can additionally drive a BooleanTrigger action.
      return type === InputType.BooleanTrigger && TRIGGER_INPUTS.has(input);
    case 'output':
      return type === InputType.Output;
  }
}

export function humanLabel(input: string): string {
  return input
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export const ALL_INPUTS: readonly string[] = [
  ...BUTTON_INPUTS,
  ...AXIS_INPUTS,
  ...POV_INPUTS,
  ...OUTPUT_INPUTS,
];
