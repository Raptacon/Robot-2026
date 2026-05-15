"""Read tab — poll and display tag data."""

import tkinter as tk
from tkinter import ttk

from host.nfc_tool.battery_data import BatteryData


class ReadTab(ttk.Frame):
    """Tag reading with parsed battery data display."""

    def __init__(self, parent, request_poll=None):
        super().__init__(parent)
        self._request_poll = request_poll
        self._polling = False
        self._poll_id = None

        self._build_ui()

    def _build_ui(self):
        # Status indicator row
        status_frame = ttk.Frame(self)
        status_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        self._canvas = tk.Canvas(status_frame, width=20, height=20,
                                 highlightthickness=0)
        self._canvas.pack(side=tk.LEFT, padx=(0, 8))
        self._dot = self._canvas.create_oval(2, 2, 18, 18, fill='gray')

        self._status_var = tk.StringVar(value="Idle")
        ttk.Label(status_frame, textvariable=self._status_var).pack(
            side=tk.LEFT)

        # Controls
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        self._auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            ctrl_frame, text="Auto-poll",
            variable=self._auto_var,
            command=self._on_auto_toggle,
        ).pack(side=tk.LEFT)

        ttk.Button(
            ctrl_frame, text="Read Once",
            command=self._read_once,
        ).pack(side=tk.LEFT, padx=(10, 0))

        # Tag info section
        info_frame = ttk.LabelFrame(self, text="Tag Info")
        info_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        fields = [
            ("UID:", "_uid_var"),
            ("URI:", "_uri_var"),
        ]
        for i, (label, attr) in enumerate(fields):
            ttk.Label(info_frame, text=label).grid(
                row=i, column=0, sticky=tk.W, padx=(8, 4), pady=2)
            var = tk.StringVar(value="\u2014")
            setattr(self, attr, var)
            ttk.Label(info_frame, textvariable=var,
                      font=('Consolas', 10)).grid(
                row=i, column=1, sticky=tk.W, pady=2)

        # Battery data section
        bat_frame = ttk.LabelFrame(self, text="Battery Data")
        bat_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        bat_fields = [
            ("Serial Number:", "_sn_var"),
            ("Year:", "_year_var"),
            ("Note:", "_note_var"),
        ]
        for i, (label, attr) in enumerate(bat_fields):
            ttk.Label(bat_frame, text=label).grid(
                row=i, column=0, sticky=tk.W, padx=(8, 4), pady=2)
            var = tk.StringVar(value="\u2014")
            setattr(self, attr, var)
            ttk.Label(bat_frame, textvariable=var).grid(
                row=i, column=1, sticky=tk.W, pady=2)

        # Raw NDEF text
        raw_frame = ttk.LabelFrame(self, text="Raw NDEF Text")
        raw_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self._raw_text = tk.Text(raw_frame, height=6, wrap=tk.WORD,
                                 state='disabled', font=('Consolas', 9))
        self._raw_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def on_tab_selected(self):
        if self._auto_var.get():
            self._start_polling()

    def on_tab_deselected(self):
        self._stop_polling()

    def _on_auto_toggle(self):
        if self._auto_var.get():
            self._start_polling()
        else:
            self._stop_polling()

    def _read_once(self):
        if self._request_poll:
            self._request_poll('read')

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
            self._request_poll('read')
        self._poll_id = self.after(500, self._do_poll)

    def update_tag_data(self, tag_data):
        """Called by app when worker returns read result.

        Data fields are latched — they persist when the tag is removed.
        Only the dot color and status text update to reflect presence.
        """
        if tag_data is None:
            # Tag gone — update indicator only, keep latched data
            self._canvas.itemconfig(self._dot, fill='#cc3333')
            self._status_var.set("No tag (last read shown)")
            return

        if len(tag_data.user_data) == 0:
            self._canvas.itemconfig(self._dot, fill='orange')
            self._status_var.set("Tag detected but data read failed")
            self._uid_var.set(tag_data.uid_hex)
            return

        self._canvas.itemconfig(self._dot, fill='#33cc33')
        self._uid_var.set(tag_data.uid_hex)

        # URI
        uri = tag_data.get_uri()
        self._uri_var.set(uri if uri else "\u2014")

        # Parse battery data from text records
        text = tag_data.get_text()
        self._set_raw_text(text)

        if 'bat:' in text:
            bat = BatteryData.from_text(text)
            self._status_var.set("Battery tag recognized")
            self._sn_var.set(bat.sn if bat.sn else "\u2014")
            self._year_var.set(bat.year if bat.year else "\u2014")
            self._note_var.set(bat.note if bat.note else "\u2014")
        else:
            self._status_var.set("Tag read (unrecognized format)")
            self._sn_var.set("\u2014")
            self._year_var.set("\u2014")
            self._note_var.set("\u2014")

    def _set_raw_text(self, text):
        self._raw_text.configure(state='normal')
        self._raw_text.delete('1.0', tk.END)
        if text:
            self._raw_text.insert('1.0', text)
        self._raw_text.configure(state='disabled')
