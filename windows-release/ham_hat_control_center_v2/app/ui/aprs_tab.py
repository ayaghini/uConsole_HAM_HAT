#!/usr/bin/env python3
"""APRS Tab — TX, RX monitor, position, and map."""

from __future__ import annotations

from typing import TYPE_CHECKING

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from ..engine.models import AppProfile
from .widgets import add_row, scrollable_frame, AprsMapCanvas, BoundedLog

if TYPE_CHECKING:
    from ..app import HamHatApp


class AprsTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, app: "HamHatApp") -> None:
        super().__init__(parent)
        self._app = app
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left_outer = ttk.Frame(self)
        left_outer.grid(row=0, column=0, sticky="nsew")
        _, _, left = scrollable_frame(left_outer)
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self._build_identity(left)
        self._build_message(left)
        self._build_position(left)
        self._build_rx(left)
        self._build_map(right)
        self._build_monitor(right)

    # ------------------------------------------------------------------
    # Left-panel sections
    # ------------------------------------------------------------------

    def _build_identity(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="APRS Identity + TX Tuning", padding=8)
        f.pack(fill="x")
        f.columnconfigure(1, weight=1)
        add_row(f, "Source", ttk.Entry(f, textvariable=self._app.aprs_source_var, width=16), 0)
        # Preset buttons
        preset = ttk.Frame(f)
        preset.grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Button(preset, text="VA7AYG-00",
                   command=lambda: self._app.apply_callsign_preset("VA7AYG-00", "VA7AYG-01")).pack(side="left")
        ttk.Button(preset, text="VA7AYG-01",
                   command=lambda: self._app.apply_callsign_preset("VA7AYG-01", "VA7AYG-00")).pack(side="left", padx=(6, 0))
        add_row(f, "Destination", ttk.Entry(f, textvariable=self._app.aprs_dest_var, width=16), 1)
        add_row(f, "Path", ttk.Entry(f, textvariable=self._app.aprs_path_var, width=20), 2)
        add_row(f, "TX Gain (0.05-0.40)", ttk.Entry(f, textvariable=self._app.aprs_tx_gain_var, width=10), 3)
        add_row(f, "Preamble Flags (16-400)", ttk.Entry(f, textvariable=self._app.aprs_preamble_var, width=10), 4)
        add_row(f, "TX Repeats (1-5)", ttk.Entry(f, textvariable=self._app.aprs_repeats_var, width=10), 5)
        ttk.Checkbutton(f, text="Re-init SA818 before APRS TX",
                        variable=self._app.aprs_reinit_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def _build_message(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="Message TX", padding=8)
        f.pack(fill="x", pady=(8, 0))
        f.columnconfigure(1, weight=1)
        add_row(f, "To", ttk.Entry(f, textvariable=self._app.aprs_msg_to_var, width=16), 0)
        add_row(f, "Message", ttk.Entry(f, textvariable=self._app.aprs_msg_text_var, width=36), 1)
        add_row(f, "Message ID (opt)", ttk.Entry(f, textvariable=self._app.aprs_msg_id_var, width=10), 2)
        ttk.Checkbutton(f, text="Reliable mode (ACK/retry)",
                        variable=self._app.aprs_reliable_var).grid(row=3, column=0, columnspan=2, sticky="w")
        add_row(f, "ACK Timeout (s)", ttk.Entry(f, textvariable=self._app.aprs_ack_timeout_var, width=8), 4)
        add_row(f, "ACK Retries (1-10)", ttk.Entry(f, textvariable=self._app.aprs_ack_retries_var, width=8), 5)
        ttk.Button(f, text="Send Message", command=self._app.send_aprs_message).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _build_position(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="Position TX", padding=8)
        f.pack(fill="x", pady=(8, 0))
        f.columnconfigure(1, weight=1)
        add_row(f, "Latitude (deg)", ttk.Entry(f, textvariable=self._app.aprs_lat_var, width=16), 0)
        add_row(f, "Longitude (deg)", ttk.Entry(f, textvariable=self._app.aprs_lon_var, width=16), 1)
        add_row(f, "Comment", ttk.Entry(f, textvariable=self._app.aprs_comment_var, width=32), 2)
        add_row(f, "Symbol Table", ttk.Entry(f, textvariable=self._app.aprs_symbol_table_var, width=4), 3)
        add_row(f, "Symbol", ttk.Entry(f, textvariable=self._app.aprs_symbol_var, width=4), 4)
        ttk.Button(f, text="Send Position", command=self._app.send_aprs_position).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _build_rx(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="RX Monitor", padding=8)
        f.pack(fill="x", pady=(8, 0))
        f.columnconfigure(1, weight=1)
        add_row(f, "Capture Sec", ttk.Entry(f, textvariable=self._app.aprs_rx_dur_var, width=8), 0)
        add_row(f, "Chunk Sec", ttk.Entry(f, textvariable=self._app.aprs_rx_chunk_var, width=8), 1)

        trim_row = ttk.Frame(f)
        trim_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        trim_row.columnconfigure(1, weight=1)
        ttk.Label(trim_row, text="RX Trim (dB)").grid(row=0, column=0, sticky="w")
        ttk.Scale(trim_row, variable=self._app.aprs_rx_trim_var, from_=-30.0, to=0.0, orient="horizontal").grid(
            row=0, column=1, sticky="ew", padx=8)
        ttk.Label(trim_row, textvariable=self._app.aprs_rx_trim_var, width=6).grid(row=0, column=2, sticky="e")
        ttk.Label(trim_row, text="Input Level").grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Label(trim_row, textvariable=self._app.aprs_rx_level_var).grid(row=1, column=1, sticky="w", pady=(2, 0))
        ttk.Label(trim_row, text="Input Clip").grid(row=2, column=0, sticky="w", pady=(2, 0))
        ttk.Label(trim_row, textvariable=self._app.rx_clip_var).grid(row=2, column=1, sticky="w", pady=(2, 0))

        os_row = ttk.Frame(f)
        os_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        os_row.columnconfigure(1, weight=1)
        ttk.Label(os_row, text="OS Mic Level").grid(row=0, column=0, sticky="w")
        ttk.Scale(os_row, variable=self._app.aprs_rx_os_level_var, from_=1, to=100, orient="horizontal").grid(
            row=0, column=1, sticky="ew", padx=8)
        ttk.Label(os_row, textvariable=self._app.aprs_rx_os_level_var, width=4).grid(row=0, column=2, sticky="e")
        ttk.Button(os_row, text="Apply OS Level", command=self._app.apply_os_rx_level).grid(
            row=0, column=3, sticky="e", padx=(8, 0))

        ttk.Checkbutton(f, text="Always-on RX Monitor",
                        variable=self._app.aprs_rx_auto_var,
                        command=self._app.on_rx_auto_toggle).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Checkbutton(f, text="Auto-ACK direct messages",
                        variable=self._app.aprs_auto_ack_var).grid(row=5, column=0, columnspan=2, sticky="w")

        btn_row = ttk.Frame(f)
        btn_row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        ttk.Button(btn_row, text="One-Shot Decode", command=self._app.rx_one_shot).grid(row=0, column=0, sticky="ew")
        ttk.Button(btn_row, text="Start Monitor", command=self._app.start_rx_monitor).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(f, text="Stop Monitor", command=self._app.stop_rx_monitor).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._rx_status_lbl = ttk.Label(f, text="", foreground="#5db85d")
        self._rx_status_lbl.grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))

    # ------------------------------------------------------------------
    # Right-panel
    # ------------------------------------------------------------------

    def _build_map(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="Stations Map (Offline)", padding=8)
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        self.aprs_map = AprsMapCanvas(f, height=260)
        self.aprs_map.grid(row=0, column=0, sticky="nsew")
        self.aprs_map.set_on_pick(lambda lat, lon, label: self.aprs_log(f"Map pick: {label} @ {lat:.5f}, {lon:.5f}"))
        btns = ttk.Frame(f)
        btns.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="Clear Map", command=self._clear_map).pack(side="left")
        ttk.Button(btns, text="Open Last In Browser", command=self._open_in_browser).pack(side="left", padx=(8, 0))
        ttk.Label(f, text="Drag=pan  Scroll=zoom  Click=info").grid(row=2, column=0, sticky="w", pady=(4, 0))

    def _build_monitor(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="APRS Monitor", padding=8)
        f.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        f.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1)
        self.aprs_monitor = BoundedLog(f, height=18)
        self.aprs_monitor.grid(row=0, column=0, sticky="nsew")

    def aprs_log(self, msg: str) -> None:
        self.aprs_monitor.append(msg)

    def add_map_point(self, lat: float, lon: float, label: str) -> None:
        self.aprs_map.add_point(lat, lon, label)

    def _clear_map(self) -> None:
        self.aprs_map.clear()
        self.aprs_log("Map cleared")

    def _open_in_browser(self) -> None:
        import webbrowser
        pos = self.aprs_map.last_position
        if not pos:
            messagebox.showinfo("Map", "No APRS position plotted yet.")
            return
        lat, lon, _ = pos
        url = f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=13/{lat:.6f}/{lon:.6f}"
        webbrowser.open(url, new=2)

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def apply_profile(self, p: AppProfile) -> None:
        self._app.aprs_source_var.set(p.aprs_source)
        self._app.aprs_dest_var.set(p.aprs_dest)
        self._app.aprs_path_var.set(p.aprs_path)
        self._app.aprs_tx_gain_var.set(str(p.aprs_tx_gain))
        self._app.aprs_preamble_var.set(str(p.aprs_preamble_flags))
        self._app.aprs_repeats_var.set(str(p.aprs_tx_repeats))
        self._app.aprs_reinit_var.set(p.aprs_tx_reinit)
        self._app.aprs_symbol_table_var.set(p.aprs_symbol_table)
        self._app.aprs_symbol_var.set(p.aprs_symbol)
        self._app.aprs_msg_to_var.set(p.aprs_msg_to)
        self._app.aprs_msg_text_var.set(p.aprs_msg_text)
        self._app.aprs_reliable_var.set(p.aprs_reliable)
        self._app.aprs_ack_timeout_var.set(str(p.aprs_ack_timeout))
        self._app.aprs_ack_retries_var.set(str(p.aprs_ack_retries))
        self._app.aprs_auto_ack_var.set(p.aprs_auto_ack)
        self._app.aprs_lat_var.set(str(p.aprs_lat))
        self._app.aprs_lon_var.set(str(p.aprs_lon))
        self._app.aprs_comment_var.set(p.aprs_comment)
        self._app.aprs_rx_dur_var.set(str(p.aprs_rx_duration))
        self._app.aprs_rx_chunk_var.set(str(p.aprs_rx_chunk))
        self._app.aprs_rx_trim_var.set(p.aprs_rx_trim_db)
        self._app.aprs_rx_os_level_var.set(p.aprs_rx_os_level)
        self._app.aprs_rx_auto_var.set(p.aprs_rx_auto)

    def collect_profile(self, p: AppProfile) -> None:
        p.aprs_source = self._app.aprs_source_var.get().strip().upper()
        p.aprs_dest = self._app.aprs_dest_var.get().strip().upper()
        p.aprs_path = self._app.aprs_path_var.get().strip().upper()
        try:
            p.aprs_tx_gain = float(self._app.aprs_tx_gain_var.get())
        except ValueError:
            pass
        try:
            p.aprs_preamble_flags = int(self._app.aprs_preamble_var.get())
        except ValueError:
            pass
        try:
            p.aprs_tx_repeats = int(self._app.aprs_repeats_var.get())
        except ValueError:
            pass
        p.aprs_tx_reinit = self._app.aprs_reinit_var.get()
        p.aprs_symbol_table = self._app.aprs_symbol_table_var.get()
        p.aprs_symbol = self._app.aprs_symbol_var.get()
        p.aprs_msg_to = self._app.aprs_msg_to_var.get().strip().upper()
        p.aprs_msg_text = self._app.aprs_msg_text_var.get()
        p.aprs_reliable = self._app.aprs_reliable_var.get()
        try:
            p.aprs_ack_timeout = float(self._app.aprs_ack_timeout_var.get())
        except ValueError:
            pass
        try:
            p.aprs_ack_retries = int(self._app.aprs_ack_retries_var.get())
        except ValueError:
            pass
        p.aprs_auto_ack = self._app.aprs_auto_ack_var.get()
        try:
            p.aprs_lat = float(self._app.aprs_lat_var.get())
        except ValueError:
            pass
        try:
            p.aprs_lon = float(self._app.aprs_lon_var.get())
        except ValueError:
            pass
        p.aprs_comment = self._app.aprs_comment_var.get()
        try:
            p.aprs_rx_duration = float(self._app.aprs_rx_dur_var.get())
        except ValueError:
            pass
        try:
            p.aprs_rx_chunk = float(self._app.aprs_rx_chunk_var.get())
        except ValueError:
            pass
        p.aprs_rx_trim_db = float(self._app.aprs_rx_trim_var.get())
        p.aprs_rx_os_level = int(self._app.aprs_rx_os_level_var.get())
        p.aprs_rx_auto = self._app.aprs_rx_auto_var.get()

    # ------------------------------------------------------------------
    # Public API called from app.py dispatcher
    # ------------------------------------------------------------------

    def append_log(self, msg: str) -> None:
        """Append a line to the APRS monitor log (alias for aprs_log)."""
        self.aprs_log(msg)

    def set_monitor_active(self, active: bool) -> None:
        """Update the RX monitor status indicator label."""
        self._rx_status_lbl.configure(text="● MONITORING" if active else "")

    def set_input_level(self, level: float) -> None:
        """Update input level indicator (separate from clip)."""
        pct = int(min(100, max(0, level * 100.0)))
        self._app.aprs_rx_level_var.set(f"{pct:3d}%")

    def set_output_level(self, level: float) -> None:
        """Update TX level (currently just logged, could drive a meter)."""
        pass  # future: drive a TX level indicator widget

    def push_waterfall(self, mono, rate: int) -> None:
        """Feed audio samples to the waterfall widget if present."""
        # Waterfall widget is optional in this tab (not currently built)
        pass

    def set_rx_clip(self, pct: float) -> None:
        """Show RX clip percentage in the clip label."""
        if pct > 5.0:
            self._app.rx_clip_var.set(f"⚠ {pct:.1f}%")
        else:
            self._app.rx_clip_var.set(f"{pct:.1f}%")
