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

// Exported so App.svelte can spin up a fresh in-memory config for the
// "New" flow without round-tripping through the server.
export function emptyConfig(): FullConfig {
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

// A pending new action created by left-clicking an unbound region.  Lives
// outside $config.actions until the user clicks Apply, at which point the
// action is created and bound to `binding`.  Cleared without any commit if
// the user selects a different action, navigates away, or hits Reset.
export const pendingNewAction = writable<{
  action: ActionDefinition;
  binding: { port: number; input: string };
} | null>(null);

// Whenever the user selects a real action that doesn't match the pending
// one, drop the pending stub so it doesn't lurk.  Done as a top-level
// subscription so any caller of `selectedAction.set(...)` benefits.
selectedAction.subscribe((sel) => {
  const pending = get(pendingNewAction);
  if (pending && sel !== qualifiedName(pending.action)) {
    pendingNewAction.set(null);
  }
});

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

// Move an action to a different group.  Same qname remapping logic as
// renameAction -- bindings follow the new qname automatically.  Keeps
// the selection on the moved action.
export function moveActionToGroup(qname: string, newGroup: string): void {
  const a = get(config).actions[qname];
  if (!a || a.group === newGroup || !newGroup) return;
  const newQname = `${newGroup}.${a.name}`;
  renameAction(qname, { ...structuredClone(a), group: newGroup });
  if (get(selectedAction) === qname) {
    selectedAction.set(newQname);
  }
}

// Rename a whole group: every action whose group matches gets remapped
// in a single mutate so undo treats it as one step, and bindings across
// all controllers are updated in the same pass.  Empty groups (entries
// in c.empty_groups) are renamed too.
export function renameGroup(oldGroup: string, newGroup: string): void {
  const trimmed = newGroup.trim();
  if (!trimmed || trimmed === oldGroup) return;
  const selBefore = get(selectedAction);
  let selAfter: string | null = selBefore;
  mutate(`rename group ${oldGroup} -> ${trimmed}`, (c) => {
    const remap: Record<string, string> = {};
    for (const [qname, a] of Object.entries(c.actions)) {
      if (a.group === oldGroup) {
        a.group = trimmed;
        remap[qname] = `${trimmed}.${a.name}`;
      }
    }
    if (Object.keys(remap).length > 0) {
      const next: Record<string, ActionDefinition> = {};
      for (const [qname, a] of Object.entries(c.actions)) {
        const target = remap[qname] ?? qname;
        next[target] = a;
      }
      c.actions = next;
      for (const port of Object.keys(c.controllers)) {
        const bindings = c.controllers[port].bindings;
        for (const input of Object.keys(bindings)) {
          bindings[input] = bindings[input].map((a) => remap[a] ?? a);
        }
      }
      if (selBefore && remap[selBefore]) selAfter = remap[selBefore];
    }
    if (c.empty_groups.includes(oldGroup)) {
      c.empty_groups = [
        ...c.empty_groups.filter((g) => g !== oldGroup && g !== trimmed),
        trimmed,
      ];
    }
  });
  if (selAfter !== selBefore) selectedAction.set(selAfter);
}

export function deleteGroup(group: string): void {
  mutate(`delete group ${group}`, (c) => {
    for (const [qname, a] of Object.entries(c.actions)) {
      if (a.group === group) delete c.actions[qname];
    }
    for (const port of Object.keys(c.controllers)) {
      const bindings = c.controllers[port].bindings;
      for (const input of Object.keys(bindings)) {
        bindings[input] = bindings[input].filter((a) => {
          const dot = a.indexOf('.');
          const g = dot < 0 ? '' : a.slice(0, dot);
          return g !== group;
        });
        if (bindings[input].length === 0) delete bindings[input];
      }
    }
    c.empty_groups = c.empty_groups.filter((g) => g !== group);
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
