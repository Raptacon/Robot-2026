// Single drag-and-drop channel.  HTML5 dataTransfer is unreliable across
// shadow DOM and same-document drags in some browsers; a Svelte store
// gives us a deterministic source of truth.

import { writable } from 'svelte/store';

export const draggedAction = writable<string | null>(null);

export const DRAG_MIME = 'application/x-controller-action';
