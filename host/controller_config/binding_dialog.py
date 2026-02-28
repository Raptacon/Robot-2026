"""Modal dialog for assigning/removing actions to a controller input.

Opened when clicking a binding box on the controller canvas.
Shows the input name, currently assigned actions, and allows
adding/removing actions.
"""

import tkinter as tk
from tkinter import ttk

from .layout_coords import XBOX_INPUT_MAP


class BindingDialog(tk.Toplevel):
    """Dialog for editing the action bindings of a single controller input."""

    def __init__(self, parent, input_name: str, current_actions: list[str],
                 available_actions: list[str]):
        """
        Args:
            parent: parent window
            input_name: canonical input name (e.g., "left_stick_x")
            current_actions: list of currently bound action names
            available_actions: all action names available to assign
        """
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()

        inp = XBOX_INPUT_MAP.get(input_name)
        display = inp.display_name if inp else input_name
        self.title(f"Bindings: {display}")

        self._input_name = input_name
        self._result: list[str] | None = None
        self._assigned = list(current_actions)
        self._available = [a for a in available_actions if a not in current_actions]

        self._build_ui()

        # Center dialog on parent
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _build_ui(self):
        self.minsize(350, 300)

        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Currently assigned actions ---
        ttk.Label(main, text="Assigned Actions:", font=("Arial", 9, "bold")).pack(anchor=tk.W)

        assigned_frame = tk.Frame(main)
        assigned_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 10))

        self._assigned_listbox = tk.Listbox(assigned_frame, height=5, exportselection=False)
        self._assigned_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        assigned_scroll = ttk.Scrollbar(assigned_frame, orient=tk.VERTICAL,
                                        command=self._assigned_listbox.yview)
        assigned_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._assigned_listbox.config(yscrollcommand=assigned_scroll.set)

        for action in self._assigned:
            self._assigned_listbox.insert(tk.END, action)

        # Remove button
        ttk.Button(main, text="Remove Selected", command=self._remove_action).pack(anchor=tk.W, pady=(0, 10))

        # --- Available actions to add ---
        ttk.Label(main, text="Available Actions:", font=("Arial", 9, "bold")).pack(anchor=tk.W)

        avail_frame = tk.Frame(main)
        avail_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 5))

        self._avail_listbox = tk.Listbox(avail_frame, height=6, exportselection=False)
        self._avail_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        avail_scroll = ttk.Scrollbar(avail_frame, orient=tk.VERTICAL,
                                     command=self._avail_listbox.yview)
        avail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._avail_listbox.config(yscrollcommand=avail_scroll.set)

        for action in sorted(self._available):
            self._avail_listbox.insert(tk.END, action)

        # Add button
        ttk.Button(main, text="Add Selected", command=self._add_action).pack(anchor=tk.W, pady=(0, 10))

        # --- OK / Cancel ---
        btn_frame = tk.Frame(main)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel, width=10).pack(side=tk.RIGHT)

    def _remove_action(self):
        """Move selected action from assigned back to available."""
        sel = self._assigned_listbox.curselection()
        if not sel:
            return
        action = self._assigned_listbox.get(sel[0])
        self._assigned_listbox.delete(sel[0])
        self._assigned.remove(action)

        # Add back to available list in sorted position
        self._available.append(action)
        self._available.sort()
        self._avail_listbox.delete(0, tk.END)
        for a in self._available:
            self._avail_listbox.insert(tk.END, a)

    def _add_action(self):
        """Move selected action from available to assigned."""
        sel = self._avail_listbox.curselection()
        if not sel:
            return
        action = self._avail_listbox.get(sel[0])
        self._avail_listbox.delete(sel[0])
        self._available.remove(action)

        self._assigned.append(action)
        self._assigned_listbox.insert(tk.END, action)

    def _on_ok(self):
        self._result = list(self._assigned)
        self.destroy()

    def _on_cancel(self):
        self._result = None
        self.destroy()

    def get_result(self) -> list[str] | None:
        """Return the updated action list, or None if canceled."""
        self.wait_window()
        return self._result
