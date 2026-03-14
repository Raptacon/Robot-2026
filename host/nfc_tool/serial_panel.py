"""Serial port connection panel — shared across all tabs."""

import tkinter as tk
from tkinter import ttk

import serial.tools.list_ports


class SerialPanel(ttk.Frame):
    """COM port selector with connect/disconnect toggle."""

    def __init__(self, parent, on_connect=None, on_disconnect=None):
        super().__init__(parent)
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._connected = False

        self._build_ui()
        self._refresh_ports()

    def _build_ui(self):
        ttk.Label(self, text="Port:").pack(side=tk.LEFT, padx=(0, 4))

        self._port_var = tk.StringVar()
        self._port_combo = ttk.Combobox(
            self, textvariable=self._port_var,
            state='readonly', width=30,
        )
        self._port_combo.pack(side=tk.LEFT, padx=(0, 4))

        self._refresh_btn = ttk.Button(
            self, text="Refresh", command=self._refresh_ports, width=8,
        )
        self._refresh_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._connect_btn = ttk.Button(
            self, text="Connect", command=self._toggle_connect, width=12,
        )
        self._connect_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._status_var = tk.StringVar(value="Disconnected")
        self._status_label = ttk.Label(
            self, textvariable=self._status_var,
            foreground='gray',
        )
        self._status_label.pack(side=tk.LEFT)

    def _refresh_ports(self):
        """Rescan available serial ports."""
        ports = serial.tools.list_ports.comports()
        descriptions = []
        self._port_map = {}
        for p in sorted(ports, key=lambda x: x.device):
            desc = f"{p.device} - {p.description}"
            descriptions.append(desc)
            self._port_map[desc] = p.device

        self._port_combo['values'] = descriptions
        if descriptions and not self._port_var.get():
            self._port_combo.current(0)

    def _toggle_connect(self):
        if self._connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        desc = self._port_var.get()
        port = self._port_map.get(desc, desc)
        if not port:
            self.set_status("No port selected", 'red')
            return

        self.set_status("Connecting...", 'orange')
        self._set_controls_enabled(False)

        if self._on_connect:
            self._on_connect(port)

    def _disconnect(self):
        if self._on_disconnect:
            self._on_disconnect()

    def set_connected(self, success, error_msg=''):
        """Called by app after worker reports connect result."""
        if success:
            self._connected = True
            self._connect_btn.configure(text="Disconnect")
            self.set_status("Connected", 'green')
            self._port_combo.configure(state='disabled')
            self._refresh_btn.configure(state='disabled')
        else:
            self._connected = False
            self._set_controls_enabled(True)
            msg = f"Error: {error_msg}" if error_msg else "Connection failed"
            self.set_status(msg, 'red')

    def set_disconnected(self):
        """Called by app after disconnect."""
        self._connected = False
        self._connect_btn.configure(text="Connect")
        self._set_controls_enabled(True)
        self.set_status("Disconnected", 'gray')

    def set_status(self, text, color='gray'):
        self._status_var.set(text)
        self._status_label.configure(foreground=color)

    def _set_controls_enabled(self, enabled):
        state = 'readonly' if enabled else 'disabled'
        self._port_combo.configure(state=state)
        self._refresh_btn.configure(
            state='normal' if enabled else 'disabled')
        self._connect_btn.configure(text="Connect")

    @property
    def is_connected(self):
        return self._connected
