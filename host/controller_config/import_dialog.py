"""Modal dialog for resolving action name conflicts during import.

Shows each conflicting action side-by-side (existing vs imported)
and lets the user choose: keep existing, replace with imported, or skip.
"""

import tkinter as tk
from tkinter import ttk

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from utils.controller.model import ActionDefinition


class ImportConflictDialog(tk.Toplevel):
    """Dialog for resolving action conflicts during import."""

    def __init__(self, parent, conflicts: set[str],
                 current: dict[str, ActionDefinition],
                 imported: dict[str, ActionDefinition]):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Resolve Import Conflicts")

        self._result: dict[str, ActionDefinition] | None = None
        self._conflicts = sorted(conflicts)
        self._current = current
        self._imported = imported

        self._build_ui()

        # Center on parent
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _build_ui(self):
        self.minsize(500, 400)

        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main,
            text=f"{len(self._conflicts)} action(s) already exist:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor=tk.W, pady=(0, 5))

        # Scrollable frame
        canvas = tk.Canvas(main, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main, orient=tk.VERTICAL,
                                  command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._radio_vars: dict[str, tk.StringVar] = {}
        for qname in self._conflicts:
            frame = ttk.LabelFrame(scroll_frame, text=qname, padding=5)
            frame.pack(fill=tk.X, padx=5, pady=3)

            cur = self._current.get(qname)
            imp = self._imported.get(qname)

            cur_desc = cur.description if cur else "(none)"
            imp_desc = imp.description if imp else "(none)"
            ttk.Label(frame, text=f"Existing: {cur_desc}").pack(anchor=tk.W)
            ttk.Label(frame, text=f"Imported: {imp_desc}").pack(anchor=tk.W)

            var = tk.StringVar(value="keep")
            self._radio_vars[qname] = var

            radio_frame = ttk.Frame(frame)
            radio_frame.pack(fill=tk.X, pady=(3, 0))
            ttk.Radiobutton(radio_frame, text="Keep Existing",
                            variable=var, value="keep").pack(
                                side=tk.LEFT, padx=5)
            ttk.Radiobutton(radio_frame, text="Replace",
                            variable=var, value="replace").pack(
                                side=tk.LEFT, padx=5)
            ttk.Radiobutton(radio_frame, text="Skip (remove both)",
                            variable=var, value="skip").pack(
                                side=tk.LEFT, padx=5)

        # Bulk actions
        bulk_frame = ttk.Frame(main)
        bulk_frame.pack(fill=tk.X, pady=(10, 5))
        ttk.Button(bulk_frame, text="Keep All Existing",
                   command=lambda: self._set_all("keep")).pack(
                       side=tk.LEFT, padx=3)
        ttk.Button(bulk_frame, text="Replace All",
                   command=lambda: self._set_all("replace")).pack(
                       side=tk.LEFT, padx=3)

        # OK / Cancel
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok,
                   width=10).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel,
                   width=10).pack(side=tk.RIGHT)

    def _set_all(self, value: str):
        for var in self._radio_vars.values():
            var.set(value)

    def _on_ok(self):
        result = {}
        for qname, var in self._radio_vars.items():
            choice = var.get()
            if choice == "keep":
                result[qname] = self._current[qname]
            elif choice == "replace":
                result[qname] = self._imported[qname]
            # "skip" -> not included (removed from merged)
        self._result = result
        self.destroy()

    def _on_cancel(self):
        self._result = None
        self.destroy()

    def get_result(self) -> dict[str, ActionDefinition] | None:
        """Block until dialog closes. Returns resolved actions or None."""
        self.wait_window()
        return self._result
