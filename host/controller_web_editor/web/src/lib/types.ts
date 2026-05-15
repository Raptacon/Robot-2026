// Mirrors utils/controller/model.py.  Kept narrow on purpose: the server is
// authoritative for defaults and migration; this file only describes the
// shape of the JSON the API hands us.

export const InputType = {
  Button: 'button',
  Analog: 'analog',
  Output: 'output',
  BooleanTrigger: 'boolean_trigger',
  VirtualAnalog: 'virtual_analog',
} as const;
export type InputType = (typeof InputType)[keyof typeof InputType];

export const BUTTON_TRIGGER_MODES = [
  'on_true',
  'on_false',
  'while_true',
  'while_false',
  'toggle_on_true',
] as const;

export const ANALOG_TRIGGER_MODES = [
  'raw',
  'scaled',
  'squared',
  'segmented',
  'spline',
] as const;

export type ButtonTriggerMode = (typeof BUTTON_TRIGGER_MODES)[number];
export type AnalogTriggerMode = (typeof ANALOG_TRIGGER_MODES)[number];
export type TriggerMode = ButtonTriggerMode | AnalogTriggerMode;

export interface ActionDefinition {
  name: string;
  description: string;
  group: string;
  input_type: InputType;
  trigger_mode: TriggerMode;
  deadband: number;
  threshold: number;
  inversion: boolean;
  slew_rate: number;
  scale: number;
  extra: Record<string, unknown>;
}

export interface ControllerConfig {
  port: number;
  name: string;
  controller_type: string;
  bindings: Record<string, string[]>;
}

export interface FullConfig {
  version: string;
  actions: Record<string, ActionDefinition>;
  controllers: Record<string, ControllerConfig>;
  empty_groups: string[];
}

export function qualifiedName(action: Pick<ActionDefinition, 'group' | 'name'>): string {
  return `${action.group}.${action.name}`;
}

export function isAnalogLike(type: InputType): boolean {
  return type === InputType.Analog || type === InputType.VirtualAnalog;
}

export function defaultTriggerModeFor(type: InputType): TriggerMode {
  return isAnalogLike(type) ? 'scaled' : 'on_true';
}

export function newAction(group: string, name: string): ActionDefinition {
  return {
    name,
    description: '',
    group,
    input_type: InputType.Button,
    trigger_mode: 'on_true',
    deadband: 0,
    threshold: 0.5,
    inversion: false,
    slew_rate: 0,
    scale: 1,
    extra: {},
  };
}
