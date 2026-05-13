// Editor state with undo/redo.
//
// Each user action calls `mutate(label, fn)`.  Before the mutation runs, the
// current config snapshot is pushed onto the undo stack.  Snapshots are deep
// clones via structuredClone so we never alias the working state.

import { writable, derived, get } from 'svelte/store';
import type { FullConfig, ActionDefinition } from './types';
import { qualifiedName } from './types';

const MAX_HISTORY = 100;

function clone(c: FullConfig): FullConfig {
  return structuredClone(c);
}

function emptyConfig(): FullConfig {
  return {
    version: '1.0.0',
    actions: {},
    controllers: {},
    empty_groups: [],
  };
}

export const config = writable<FullConfig>(emptyConfig());
export const currentPath = writable<string | null>(null);
export const selectedAction = writable<string | null>(null);
export const dirty = writable<boolean>(false);
// Inspector expanded mode -- when on, the right pane grows wider and the
// curve editor + live preview move into a side column so the user can see
// most options without scrolling.  Stored at the app level so App.svelte
// can resize the grid in lockstep with the inspector's internal layout.
export const inspectorExpanded = writable<boolean>(false);

const undoStack: FullConfig[] = [];
const redoStack: FullConfig[] = [];
export const canUndo = writable(false);
export const canRedo = writable(false);

function refreshHistoryFlags(): void {
  canUndo.set(undoStack.length > 0);
  canRedo.set(redoStack.length > 0);
}

export function loadInto(c: FullConfig, path: string | null): void {
  undoStack.length = 0;
  redoStack.length = 0;
  config.set(clone(c));
  currentPath.set(path);
  dirty.set(false);
  refreshHistoryFlags();
}

export function markSaved(): void {
  dirty.set(false);
}

export function mutate(_label: string, fn: (c: FullConfig) => void): void {
  const before = clone(get(config));
  undoStack.push(before);
  if (undoStack.length > MAX_HISTORY) undoStack.shift();
  redoStack.length = 0;
  // Deep-clone before mutating.  Svelte 5's $derived short-circuits on
  // Object.is of its result, so mutating nested properties in place
  // would leave downstream derived chains (e.g. `$config.controllers[p].bindings`)
  // returning the same object reference and Svelte would skip the update.
  // Cloning forces a fresh identity along every path, guaranteeing that
  // dependent UI re-renders.  Also has the side benefit that undoStack
  // entries never alias the live working config.
  config.update((c) => {
    const next = clone(c);
    fn(next);
    return next;
  });
  dirty.set(true);
  refreshHistoryFlags();
}

export function undo(): void {
  const prev = undoStack.pop();
  if (!prev) return;
  redoStack.push(clone(get(config)));
  config.set(prev);
  dirty.set(true);
  refreshHistoryFlags();
}

export function redo(): void {
  const next = redoStack.pop();
  if (!next) return;
  undoStack.push(clone(get(config)));
  config.set(next);
  dirty.set(true);
  refreshHistoryFlags();
}

// --- Convenience mutators ---

export function upsertAction(action: ActionDefinition): void {
  const qname = qualifiedName(action);
  mutate(`edit ${qname}`, (c) => {
    c.actions[qname] = action;
    c.empty_groups = c.empty_groups.filter((g) => g !== action.group);
  });
}

export function deleteAction(qname: string): void {
  mutate(`delete ${qname}`, (c) => {
    delete c.actions[qname];
    for (const port of Object.keys(c.controllers)) {
      const bindings = c.controllers[port].bindings;
      for (const input of Object.keys(bindings)) {
        bindings[input] = bindings[input].filter((a) => a !== qname);
        if (bindings[input].length === 0) delete bindings[input];
      }
    }
  });
}

export function renameAction(oldQname: string, newAction: ActionDefinition): void {
  const newQname = qualifiedName(newAction);
  if (oldQname === newQname) {
    upsertAction(newAction);
    return;
  }
  mutate(`rename ${oldQname} -> ${newQname}`, (c) => {
    delete c.actions[oldQname];
    c.actions[newQname] = newAction;
    for (const port of Object.keys(c.controllers)) {
      const bindings = c.controllers[port].bindings;
      for (const input of Object.keys(bindings)) {
        bindings[input] = bindings[input].map((a) => (a === oldQname ? newQname : a));
      }
    }
  });
}

export function setBinding(port: number, input: string, actions: string[]): void {
  mutate(`bind ${input}@${port}`, (c) => {
    const key = String(port);
    if (!c.controllers[key]) {
      c.controllers[key] = {
        port,
        name: '',
        controller_type: 'xbox',
        bindings: {},
      };
    }
    if (actions.length === 0) {
      delete c.controllers[key].bindings[input];
    } else {
      c.controllers[key].bindings[input] = actions;
    }
  });
}

export function ensureController(port: number): void {
  const c = get(config);
  if (c.controllers[String(port)]) return;
  mutate(`add controller ${port}`, (cfg) => {
    cfg.controllers[String(port)] = {
      port,
      name: '',
      controller_type: 'xbox',
      bindings: {},
    };
  });
}

// --- Derived views ---

export const groupedActions = derived(config, ($c) => {
  const groups = new Map<string, ActionDefinition[]>();
  for (const a of Object.values($c.actions)) {
    const list = groups.get(a.group) ?? [];
    list.push(a);
    groups.set(a.group, list);
  }
  for (const g of $c.empty_groups) {
    if (!groups.has(g)) groups.set(g, []);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([group, actions]) => ({
      group,
      actions: actions.sort((a, b) => a.name.localeCompare(b.name)),
    }));
});
