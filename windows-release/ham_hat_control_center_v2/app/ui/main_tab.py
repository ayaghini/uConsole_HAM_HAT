#!/usr/bin/env python3
"""Main Tab — Radio control, connection, and audio routing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from ..engine.models import AppProfile
from ..engine.sa818_client import CTCSS
from .widgets import BoundedLog, add_row, scrollable_frame

if TYPE_CHECKING:
    from ..app import HamHatApp


class MainTab(ttk.Frame):
    """Control tab: connection, radio params, audio routing, log."""

    def __init__(self, parent: ttk.Notebook, state: "HamHatApp") -> None:
        super().__init__(parent)
        self._state = state
        self._out_device_map: dict[str, int] = {}
        self._in_device_map:  dict[str, int] = {}
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(6, 6, 6, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(2, weight=1)
        top.columnconfigure(3, weight=1)
        self._build_params(top)

        # Log panel at bottom
        lf = ttk.LabelFrame(self, text="Radio Log", padding=4)
        lf.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self._log = BoundedLog(lf, height=8, wrap="word",
                                font=("Consolas", 8), state="disabled",
                                background="#0f2531", foreground="#9cc4dd")
        self._log.grid(row=0, column=0, sticky="nsew")

    def _build_params(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)
        parent.columnconfigure(3, weight=1)

        # --- Connection ---
        conn = ttk.LabelFrame(parent, text="Connection", padding=8)
        conn.grid(row=0, column=0, columnspan=4, sticky="ew")
        conn.columnconfigure(1, weight=1)
        ttk.Label(conn, text="Serial Port").grid(row=0, column=0, sticky="w", pady=3)
        self.port_combo = ttk.Combobox(conn, textvariable=self._state.port_var, width=22, state="readonly")
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=6, pady=3)
        ttk.Label(conn, textvariable=self._state.status_var).grid(row=0, column=2, sticky="e")

        btn_row = ttk.Frame(conn)
        btn_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        for i in range(5):
            btn_row.columnconfigure(i, weight=1)
        ttk.Button(btn_row, text="Refresh", command=self._state.refresh_ports).grid(row=0, column=0, sticky="ew")
        ttk.Button(btn_row, text="Auto Identify", command=self._state.auto_identify).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(btn_row, text="Connect", command=self._state.connect).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ttk.Button(btn_row, text="Disconnect", command=self._state.disconnect).grid(row=0, column=3, sticky="ew", padx=(6, 0))
        ttk.Button(btn_row, text="Read Version", command=self._state.read_version).grid(row=0, column=4, sticky="ew", padx=(6, 0))

        profile_row = ttk.Frame(conn)
        profile_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        for i in range(2):
            profile_row.columnconfigure(i, weight=1)
        ttk.Button(profile_row, text="Import Profile", command=self._state.import_profile).grid(row=0, column=0, sticky="ew")
        ttk.Button(profile_row, text="Export Profile", command=self._state.export_profile).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # --- Radio params ---
        radio = ttk.LabelFrame(parent, text="Radio Parameters", padding=8)
        radio.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        radio.columnconfigure(1, weight=1)
        add_row(radio, "Frequency (MHz)", ttk.Entry(radio, textvariable=self._state.frequency_var, width=14), 0)
        add_row(radio, "Offset (MHz)", ttk.Entry(radio, textvariable=self._state.offset_var, width=14), 1)
        add_row(radio, "Squelch (0-8)", ttk.Entry(radio, textvariable=self._state.squelch_var, width=14), 2)
        bw = ttk.Combobox(radio, textvariable=self._state.bandwidth_var, values=["Wide", "Narrow"], width=12, state="readonly")
        add_row(radio, "Bandwidth", bw, 3)
        ttk.Button(radio, text="Apply Radio", command=self._state.apply_radio).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # --- Audio routing ---
        audio = ttk.LabelFrame(parent, text="Audio Routing + Auto Detection", padding=8)
        audio.grid(row=1, column=2, columnspan=2, sticky="nsew", padx=(8, 0), pady=(8, 0))
        audio.columnconfigure(1, weight=1)
        self.out_combo = ttk.Combobox(audio, textvariable=self._state.audio_out_var, width=34, state="readonly")
        add_row(audio, "Audio Output", self.out_combo, 0)
        self.out_combo.bind("<<ComboboxSelected>>", self._on_out_selected)
        self.in_combo = ttk.Combobox(audio, textvariable=self._state.audio_in_var, width=34, state="readonly")
        add_row(audio, "Audio Input", self.in_combo, 1)
        self.in_combo.bind("<<ComboboxSelected>>", self._on_in_selected)
        ttk.Button(audio, text="Refresh Audio Devices", command=self._state.refresh_audio_devices).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(audio, text="Auto Find TX/RX Pair", command=self._state.auto_find_audio_pair).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(audio, text="TX Channel Announce Sweep", command=self._state.tx_channel_sweep).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(audio, text="Auto Detect RX by Voice", command=self._state.auto_detect_rx).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Checkbutton(audio, text="Auto-select SA818 audio on connect",
                        variable=self._state.auto_audio_var).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # --- PTT ---
        ptt = ttk.LabelFrame(parent, text="PTT", padding=8)
        ptt.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ptt.columnconfigure(1, weight=1)
        ttk.Checkbutton(ptt, text="Key PTT during TX audio", variable=self._state.ptt_enabled_var).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        ptt_line = ttk.Combobox(ptt, textvariable=self._state.ptt_line_var, values=["RTS", "DTR"], width=10, state="readonly")
        add_row(ptt, "PTT Line", ptt_line, 1)
        ttk.Checkbutton(ptt, text="PTT Active High", variable=self._state.ptt_active_high_var).grid(
            row=2, column=0, columnspan=2, sticky="w")
        add_row(ptt, "PTT Pre (ms)", ttk.Entry(ptt, textvariable=self._state.ptt_pre_ms_var, width=10), 3)
        add_row(ptt, "PTT Post (ms)", ttk.Entry(ptt, textvariable=self._state.ptt_post_ms_var, width=10), 4)

    # ------------------------------------------------------------------
    # Update from profile
    # ------------------------------------------------------------------

    def apply_profile(self, p: AppProfile) -> None:
        self._state.frequency_var.set(str(p.frequency))
        self._state.offset_var.set(str(p.offset))
        self._state.squelch_var.set(str(p.squelch))
        self._state.bandwidth_var.set(p.bandwidth)
        self._state.ptt_enabled_var.set(p.ptt_enabled)
        self._state.ptt_line_var.set(p.ptt_line)
        self._state.ptt_active_high_var.set(p.ptt_active_high)
        self._state.ptt_pre_ms_var.set(str(p.ptt_pre_ms))
        self._state.ptt_post_ms_var.set(str(p.ptt_post_ms))
        self._state.auto_audio_var.set(p.auto_audio_select)

    def collect_profile(self, p: AppProfile) -> None:
        try:
            p.frequency = float(self._state.frequency_var.get())
        except ValueError:
            pass
        try:
            p.offset = float(self._state.offset_var.get())
        except ValueError:
            pass
        try:
            p.squelch = int(self._state.squelch_var.get())
        except ValueError:
            pass
        p.bandwidth = self._state.bandwidth_var.get()
        p.ptt_enabled = self._state.ptt_enabled_var.get()
        p.ptt_line = self._state.ptt_line_var.get()
        p.ptt_active_high = self._state.ptt_active_high_var.get()
        try:
            p.ptt_pre_ms = int(self._state.ptt_pre_ms_var.get())
        except ValueError:
            pass
        try:
            p.ptt_post_ms = int(self._state.ptt_post_ms_var.get())
        except ValueError:
            pass
        p.auto_audio_select = self._state.auto_audio_var.get()
        # Audio device names for profile restore
        p.output_device_name = self._state.audio_out_var.get()
        p.input_device_name  = self._state.audio_in_var.get()

    # ------------------------------------------------------------------
    # Event handlers from combobox selection
    # ------------------------------------------------------------------

    def _on_out_selected(self, _e=None) -> None:
        name = self._state.audio_out_var.get()
        idx = self._out_device_map.get(name)
        self._state.set_output_device(idx, name)

    def _on_in_selected(self, _e=None) -> None:
        name = self._state.audio_in_var.get()
        idx = self._in_device_map.get(name)
        self._state.set_input_device(idx, name)

    # ------------------------------------------------------------------
    # Public API called from app.py dispatcher
    # ------------------------------------------------------------------

    def refresh_audio_devices(self) -> None:
        """Ask app for updated device lists and repopulate comboboxes."""
        from ..engine.audio_tools import list_output_devices, list_input_devices
        outs = list_output_devices()
        ins  = list_input_devices()
        self.populate_audio_devices(outs, ins)

    def populate_audio_devices(
        self,
        outs: list[tuple[int, str]],
        ins:  list[tuple[int, str]],
    ) -> None:
        self._out_device_map = {name: idx for idx, name in outs}
        self._in_device_map  = {name: idx for idx, name in ins}
        out_names = [name for _, name in outs]
        in_names  = [name for _, name in ins]
        self.out_combo["values"] = out_names
        self.in_combo["values"]  = in_names
        # Restore selection if device name still present
        if self._state.audio_out_var.get() not in out_names and out_names:
            self._state.audio_out_var.set(out_names[0])
            self._on_out_selected()
        if self._state.audio_in_var.get() not in in_names and in_names:
            self._state.audio_in_var.set(in_names[0])
            self._on_in_selected()

    def on_audio_pair(self, out_idx: int, out_name: str, in_idx: int, in_name: str) -> None:
        """Called by app dispatcher when auto-pair succeeds."""
        self._state.audio_out_var.set(out_name)
        self._state.audio_in_var.set(in_name)
        self._state.set_output_device(out_idx, out_name)
        self._state.set_input_device(in_idx, in_name)

    def on_connect(self, port: str) -> None:
        pass  # Status bar in app.py already updated

    def on_disconnect(self) -> None:
        pass  # Status bar in app.py already updated

    def append_log(self, msg: str) -> None:
        """Append a line to the radio log panel."""
        self._log.append(msg.rstrip())
