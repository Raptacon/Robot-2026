"""Scan tab — live tag presence indicator for range testing."""

import tkinter as tk
from tkinter import ttk


class ScanTab(ttk.Frame):
    """Large red/green indicator showing tag presence in real time."""

    def __init__(self, parent, request_poll=None):
        super().__init__(parent)
        self._request_poll = request_poll
        self._polling = False
        self._poll_id = None

        self._build_ui()

    def _build_ui(self):
        # Large colored circle
        self._canvas = tk.Canvas(self, width=200, height=200,
                                 highlightthickness=0)
        self._canvas.pack(pady=20)
        self._indicator = self._canvas.create_oval(
            25, 25, 175, 175, fill='#cc3333', outline='#882222', width=3,
        )

        self._status_var = tk.StringVar(value="No tag detected")
        ttk.Label(
            self, textvariable=self._status_var,
            font=('TkDefaultFont', 14),
        ).pack(pady=(0, 10))

        # UID display
        info_frame = ttk.Frame(self)
        info_frame.pack(fill=tk.X, padx=40)

        ttk.Label(info_frame, text="UID:").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8))
        self._uid_var = tk.StringVar(value="—")
        ttk.Label(info_frame, textvariable=self._uid_var,
                  font=('Consolas', 11)).grid(
            row=0, column=1, sticky=tk.W)

        ttk.Label(info_frame, text="Data size:").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 8), pady=(4, 0))
        self._size_var = tk.StringVar(value="—")
        ttk.Label(info_frame, textvariable=self._size_var).grid(
            row=1, column=1, sticky=tk.W, pady=(4, 0))

        # Auto-poll control
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.pack(pady=20)
        self._auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            ctrl_frame, text="Auto-poll (200ms)",
            variable=self._auto_var,
            command=self._on_auto_toggle,
        ).pack()

    def on_tab_selected(self):
        """Called when this tab becomes visible."""
        if self._auto_var.get():
            self._start_polling()

    def on_tab_deselected(self):
        """Called when switching away from this tab."""
        self._stop_polling()

    def _on_auto_toggle(self):
        if self._auto_var.get():
            self._start_polling()
        else:
            self._stop_polling()

    def _start_polling(self):
        if self._polling:
            return
        self._polling = True
        self._do_poll()

    def _stop_polling(self):
        self._polling = False
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _do_poll(self):
        if not self._polling:
            return
        if self._request_poll:
            self._request_poll('scan')
        self._poll_id = self.after(200, self._do_poll)

    def update_tag_data(self, tag_data):
        """Called by app when worker returns scan result."""
        if tag_data is not None:
            # Tag present
            self._canvas.itemconfig(self._indicator, fill='#33cc33',
                                    outline='#228822')
            self._status_var.set("Tag detected!")
            self._uid_var.set(tag_data.uid_hex)
            data_len = len(tag_data.user_data)
            if data_len > 0:
                self._size_var.set(f"{data_len} bytes")
            else:
                self._size_var.set("UID only (data read failed)")
        else:
            # No tag
            self._canvas.itemconfig(self._indicator, fill='#cc3333',
                                    outline='#882222')
            self._status_var.set("No tag detected")
            self._uid_var.set("\u2014")
            self._size_var.set("\u2014")
