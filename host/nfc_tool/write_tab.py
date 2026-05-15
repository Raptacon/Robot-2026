"""Write tab — battery data write workflow with UID verification."""

import datetime
import time
import tkinter as tk
from tkinter import ttk, messagebox

from host.nfc_tool.battery_data import BatteryData


# Write workflow states
IDLE = 'idle'
SEARCHING = 'searching'
TAG_FOUND = 'tag_found'
VERIFYING = 'verifying'
WRITING = 'writing'
DONE = 'done'
ERROR = 'error'

# Verify retry settings
VERIFY_RETRY_INTERVAL_MS = 1000  # 1 second between retries
VERIFY_TIMEOUT_S = 10  # give up after 10 seconds


class WriteTab(ttk.Frame):
    """Multi-step write workflow with tag verification safety."""

    def __init__(self, parent, request_poll=None, request_write=None):
        super().__init__(parent)
        self._request_poll = request_poll
        self._request_write = request_write
        self._state = IDLE
        self._found_uid = None  # UID captured when tag first detected
        self._found_tag_data = None  # Full tag data from detection
        self._poll_id = None
        self._verify_start_time = 0

        self._build_ui()

    def _build_ui(self):
        # Form section
        form_frame = ttk.LabelFrame(self, text="Battery Information")
        form_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(form_frame, text="Serial Number:").grid(
            row=0, column=0, sticky=tk.W, padx=(8, 4), pady=4)
        self._sn_var = tk.StringVar()
        self._sn_entry = ttk.Entry(form_frame, textvariable=self._sn_var,
                                   width=30)
        self._sn_entry.grid(row=0, column=1, sticky=tk.W, pady=4)

        ttk.Label(form_frame, text="Year:").grid(
            row=1, column=0, sticky=tk.W, padx=(8, 4), pady=4)
        current_year = datetime.datetime.now().year
        years = [str(y) for y in
                 range(current_year + 1, current_year - 6, -1)]
        self._year_var = tk.StringVar(value=str(current_year))
        self._year_combo = ttk.Combobox(
            form_frame, textvariable=self._year_var,
            values=years, width=8,
        )
        self._year_combo.grid(row=1, column=1, sticky=tk.W, pady=4)

        ttk.Label(form_frame, text="Note:").grid(
            row=2, column=0, sticky=tk.W, padx=(8, 4), pady=4)
        self._note_var = tk.StringVar()
        self._note_entry = ttk.Entry(
            form_frame, textvariable=self._note_var, width=40)
        self._note_entry.grid(row=2, column=1, sticky=tk.W, pady=4)

        ttk.Label(form_frame, text="URI:").grid(
            row=3, column=0, sticky=tk.W, padx=(8, 4), pady=4)
        self._uri_var = tk.StringVar(value="http://www.raptacon.org")
        self._uri_entry = ttk.Entry(
            form_frame, textvariable=self._uri_var, width=40)
        self._uri_entry.grid(row=3, column=1, sticky=tk.W, pady=4)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        self._start_btn = ttk.Button(
            btn_frame, text="Start Write",
            command=self._on_start_write,
        )
        self._start_btn.pack(side=tk.LEFT)

        self._cancel_btn = ttk.Button(
            btn_frame, text="Cancel",
            command=self._on_cancel,
            state='disabled',
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Status / log area
        log_frame = ttk.LabelFrame(self, text="Write Progress")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        self._log_text = tk.Text(log_frame, height=10, wrap=tk.WORD,
                                 state='disabled', font=('Consolas', 9))
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL,
                                  command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                            padx=(4, 0), pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)

    def _log(self, msg):
        self._log_text.configure(state='normal')
        self._log_text.insert(tk.END, msg + '\n')
        self._log_text.see(tk.END)
        self._log_text.configure(state='disabled')

    def _clear_log(self):
        self._log_text.configure(state='normal')
        self._log_text.delete('1.0', tk.END)
        self._log_text.configure(state='disabled')

    def _set_state(self, state):
        self._state = state
        form_enabled = state in (IDLE, DONE, ERROR)
        entry_state = 'normal' if form_enabled else 'disabled'
        self._sn_entry.configure(state=entry_state)
        self._year_combo.configure(
            state='normal' if form_enabled else 'disabled')
        self._note_entry.configure(state=entry_state)
        self._uri_entry.configure(state=entry_state)

        self._start_btn.configure(
            state='normal' if form_enabled else 'disabled')
        self._cancel_btn.configure(
            state='normal' if state == SEARCHING else 'disabled')

    # --- User actions ---

    def _on_start_write(self):
        sn = self._sn_var.get().strip()
        if not sn:
            messagebox.showwarning(
                "Missing Data", "Serial number is required.",
                parent=self)
            return

        self._clear_log()
        self._found_uid = None
        self._found_tag_data = None
        self._set_state(SEARCHING)
        self._log("Searching for tag... Place tag on reader.")
        self._start_search_poll()

    def _on_cancel(self):
        self._stop_poll()
        self._set_state(IDLE)
        self._log("Cancelled.")

    # --- Polling helpers ---

    def _start_search_poll(self):
        self._stop_poll()
        self._do_search_poll()

    def _stop_poll(self):
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _do_search_poll(self):
        if self._state != SEARCHING:
            return
        if self._request_poll:
            self._request_poll('write_search')
        self._poll_id = self.after(300, self._do_search_poll)

    def _do_verify_poll(self):
        """Poll for tag during verify phase, with timeout."""
        if self._state != VERIFYING:
            return
        elapsed = time.monotonic() - self._verify_start_time
        if elapsed >= VERIFY_TIMEOUT_S:
            # Timed out
            self._set_state(ERROR)
            messagebox.showerror(
                "Write Failed",
                "Tag not detected after 10 seconds.\n\n"
                "Make sure the tag is placed on the reader "
                "and try again.",
                parent=self)
            self._log("Write failed: tag not detected (timed out).")
            return
        if self._request_poll:
            self._request_poll('write_verify')
        self._poll_id = self.after(VERIFY_RETRY_INTERVAL_MS,
                                   self._do_verify_poll)

    # --- Tab lifecycle ---

    def on_tab_selected(self):
        pass

    def on_tab_deselected(self):
        if self._state in (SEARCHING, VERIFYING):
            self._on_cancel()

    # --- Results from worker ---

    def on_search_result(self, tag_data):
        """Called when searching for a tag during write workflow."""
        if self._state != SEARCHING:
            return

        if tag_data is None:
            return  # Keep searching

        self._stop_poll()
        self._found_uid = tag_data.uid_hex
        self._found_tag_data = tag_data
        self._set_state(TAG_FOUND)

        # Build the confirmation message
        self._log(f"Tag found! UID: {tag_data.uid_hex}")

        existing_info = ""
        if len(tag_data.user_data) > 0:
            text = tag_data.get_text()
            uri = tag_data.get_uri()
            if text:
                self._log(f"Existing text: {text}")
                existing_info += f"Existing text: {text}\n"
            if uri:
                self._log(f"Existing URI: {uri}")
                existing_info += f"Existing URI: {uri}\n"
            if not text and not uri:
                self._log("Tag is blank (no NDEF data).")
                existing_info = "Tag is currently blank.\n"
        else:
            self._log("Could not read tag data (UID only).")
            existing_info = "Could not read existing data.\n"

        # Build new data preview
        bat = BatteryData(
            sn=self._sn_var.get().strip(),
            year=self._year_var.get().strip(),
            note=self._note_var.get().strip(),
        )
        new_uri = self._uri_var.get().strip()

        # Show confirmation dialog
        msg = (
            f"Tag detected: UID {tag_data.uid_hex}\n\n"
            f"{existing_info}\n"
            f"--- Write the following? ---\n"
            f"URI: {new_uri}\n"
            f"{bat.to_text()}\n\n"
            f"Proceed with write?"
        )

        proceed = messagebox.askyesno(
            "Confirm Write", msg, parent=self)

        if proceed:
            self._log("")
            self._log("Write confirmed. Verifying tag...")
            self._set_state(VERIFYING)
            self._verify_start_time = time.monotonic()
            self._do_verify_poll()
        else:
            self._set_state(IDLE)
            self._log("Write cancelled by user.")

    def on_verify_result(self, tag_data):
        """Called during write verification — check UID matches."""
        if self._state != VERIFYING:
            return

        if tag_data is None:
            # Tag not found yet — retry will happen via _do_verify_poll
            elapsed = time.monotonic() - self._verify_start_time
            remaining = max(0, VERIFY_TIMEOUT_S - elapsed)
            self._log(f"Tag not detected, retrying... "
                      f"({remaining:.0f}s remaining)")
            return

        self._stop_poll()

        current_uid = tag_data.uid_hex
        if current_uid != self._found_uid:
            self._set_state(ERROR)
            messagebox.showerror(
                "Write Failed",
                f"Tag changed during write!\n\n"
                f"Expected UID: {self._found_uid}\n"
                f"Detected UID: {current_uid}\n\n"
                f"Place the original tag back and try again.",
                parent=self)
            self._log(
                f"Write failed: tag changed "
                f"(expected {self._found_uid}, "
                f"got {current_uid})")
            return

        # UID matches — proceed with write
        self._set_state(WRITING)
        self._log("Tag verified. Writing...")
        if self._request_write:
            self._request_write(
                sn=self._sn_var.get().strip(),
                year=self._year_var.get().strip(),
                note=self._note_var.get().strip(),
                uri=self._uri_var.get().strip(),
            )

    def on_write_result(self, success, error_msg=''):
        """Called when write operation completes."""
        if success:
            self._set_state(DONE)
            self._log("Write successful!")
            self._log("Tag has been programmed. You may remove it.")
            messagebox.showinfo(
                "Write Complete",
                "Tag has been successfully programmed!",
                parent=self)
        else:
            self._set_state(ERROR)
            self._log(f"Write failed: {error_msg}")
            messagebox.showerror(
                "Write Failed",
                f"Tag write failed:\n\n{error_msg}\n\n"
                f"Click 'Start Write' to try again.",
                parent=self)
