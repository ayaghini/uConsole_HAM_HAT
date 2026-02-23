#!/usr/bin/env python3
"""Cross-platform UI for uConsole HAM HAT bring-up and SA818 control."""

from __future__ import annotations

import json
import platform
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from time import sleep
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import numpy as np
from serial.tools import list_ports

from aprs_modem import (
    build_aprs_ack_payload,
    build_aprs_message_payload,
    build_aprs_position_payload,
    decode_ax25_from_samples,
    decode_ax25_from_wav,
    parse_aprs_message_info,
)
from audio_tools import (
    capture_samples,
    list_input_devices,
    list_output_devices,
    play_wav_blocking,
    record_wav,
    stop_playback,
    wav_duration_seconds,
    write_aprs_wav,
    write_test_tone_wav,
)
from sa818_client import RadioConfig, SA818Client, SA818Error


APP_DIR = Path(__file__).resolve().parents[1]
PROFILE_PATH = APP_DIR / "profiles" / "last_profile.json"
AUDIO_DIR = APP_DIR / "audio_out"


class HamHatControlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("uConsole HAM HAT Control Center")
        self.geometry("980x720")

        self.client = SA818Client()

        self._vars()
        self._build_ui()
        self.refresh_ports()
        self.refresh_audio_devices()
        self.refresh_input_devices()
        self.load_profile(silent=True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_ui_queue)
        if self.aprs_rx_auto_var.get():
            self.start_rx_monitor()

    def _vars(self) -> None:
        self.port_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Disconnected")

        self.frequency_var = tk.StringVar(value="145.070")
        self.offset_var = tk.StringVar(value="0.6")
        self.squelch_var = tk.StringVar(value="4")
        self.bandwidth_var = tk.StringVar(value="Wide")

        self.ctcss_tx_var = tk.StringVar(value="")
        self.ctcss_rx_var = tk.StringVar(value="")
        self.dcs_tx_var = tk.StringVar(value="")
        self.dcs_rx_var = tk.StringVar(value="")

        self.disable_emphasis_var = tk.BooleanVar(value=True)
        self.disable_highpass_var = tk.BooleanVar(value=True)
        self.disable_lowpass_var = tk.BooleanVar(value=True)

        self.volume_var = tk.IntVar(value=5)
        self.offline_bootstrap_var = tk.BooleanVar(value=False)
        self.test_tone_freq_var = tk.StringVar(value="1200")
        self.test_tone_duration_var = tk.StringVar(value="2.0")
        self.aprs_source_var = tk.StringVar(value="N0CALL-9")
        self.aprs_dest_var = tk.StringVar(value="APRS")
        self.aprs_path_var = tk.StringVar(value="WIDE1-1")
        self.aprs_message_var = tk.StringVar(value="uConsole HAM HAT test")
        self.audio_device_var = tk.StringVar(value="Default")
        self.aprs_msg_to_var = tk.StringVar(value="N0CALL")
        self.aprs_msg_text_var = tk.StringVar(value="hello from uConsole")
        self.aprs_msg_id_var = tk.StringVar(value="")
        self.aprs_reliable_var = tk.BooleanVar(value=False)
        self.aprs_ack_timeout_var = tk.StringVar(value="8")
        self.aprs_ack_retries_var = tk.StringVar(value="4")
        self.aprs_auto_ack_var = tk.BooleanVar(value=True)
        self.aprs_lat_var = tk.StringVar(value="49.2827")
        self.aprs_lon_var = tk.StringVar(value="-123.1207")
        self.aprs_comment_var = tk.StringVar(value="uConsole HAM HAT")
        self.aprs_rx_input_var = tk.StringVar(value="Default")
        self.aprs_rx_duration_var = tk.StringVar(value="10")
        self.aprs_rx_chunk_var = tk.StringVar(value="2.0")
        self.aprs_rx_auto_var = tk.BooleanVar(value=False)
        # Baseline defaults that matched earlier handheld-decodable tests.
        self.aprs_tx_gain_var = tk.StringVar(value="0.12")
        self.aprs_preamble_flags_var = tk.StringVar(value="160")
        self.aprs_tx_repeats_var = tk.StringVar(value="1")
        self.ptt_enabled_var = tk.BooleanVar(value=True)
        self.ptt_line_var = tk.StringVar(value="RTS")
        self.ptt_active_high_var = tk.BooleanVar(value=True)
        self.auto_audio_select_var = tk.BooleanVar(value=True)
        self.aprs_tx_reinit_var = tk.BooleanVar(value=True)
        self.ptt_pre_ms_var = tk.StringVar(value="400")
        self.ptt_post_ms_var = tk.StringVar(value="120")
        self.sa818_audio_output_hint = ""
        self.sa818_audio_input_hint = ""
        self._audio_worker: threading.Thread | None = None
        self._rx_monitor_thread: threading.Thread | None = None
        self._rx_monitor_running = False
        self._audio_lock = threading.Lock()
        self._rx_overlap_samples = None
        self._last_rx_text = ""
        self._last_rx_time = 0.0
        self._ui_queue: queue.Queue[tuple[str, str, str | None]] = queue.Queue()
        self._ack_condition = threading.Condition()
        self._acked_message_ids: set[str] = set()
        self._seen_direct_message_ids: set[str] = set()

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Serial Port:").pack(side="left")
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, width=28, state="readonly")
        self.port_combo.pack(side="left", padx=(6, 6))

        ttk.Button(top, text="Refresh", command=self.refresh_ports).pack(side="left")
        ttk.Button(top, text="Auto Identify SA818", command=self.auto_identify_and_connect).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Connect", command=self.connect).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Disconnect", command=self.disconnect).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Read Version", command=self.read_version).pack(side="left", padx=(8, 0))

        ttk.Label(top, textvariable=self.status_var).pack(side="right")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        control_tab = ttk.Frame(notebook, padding=10)
        aprs_tab = ttk.Frame(notebook, padding=10)
        setup_tab = ttk.Frame(notebook, padding=10)
        notebook.add(control_tab, text="Radio Control")
        notebook.add(aprs_tab, text="APRS")
        notebook.add(setup_tab, text="Setup")

        self._build_control_tab(control_tab)
        self._build_aprs_tab(aprs_tab)
        self._build_setup_tab(setup_tab)

        log_frame = ttk.LabelFrame(self, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = ScrolledText(log_frame, height=14)
        self.log_text.pack(fill="both", expand=True)

    def _build_control_tab(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        left.pack(side="left", fill="both", expand=True)

        radio = ttk.LabelFrame(left, text="Radio", padding=10)
        radio.pack(fill="x")

        self._row(radio, "Frequency (MHz)", ttk.Entry(radio, textvariable=self.frequency_var, width=16), 0)
        self._row(radio, "Offset (MHz)", ttk.Entry(radio, textvariable=self.offset_var, width=16), 1)
        self._row(radio, "Squelch (0-8)", ttk.Entry(radio, textvariable=self.squelch_var, width=16), 2)

        bw_combo = ttk.Combobox(radio, textvariable=self.bandwidth_var, values=["Wide", "Narrow"], width=14, state="readonly")
        self._row(radio, "Bandwidth", bw_combo, 3)

        self._row(radio, "CTCSS TX", ttk.Entry(radio, textvariable=self.ctcss_tx_var, width=16), 4)
        self._row(radio, "CTCSS RX", ttk.Entry(radio, textvariable=self.ctcss_rx_var, width=16), 5)
        self._row(radio, "DCS TX", ttk.Entry(radio, textvariable=self.dcs_tx_var, width=16), 6)
        self._row(radio, "DCS RX", ttk.Entry(radio, textvariable=self.dcs_rx_var, width=16), 7)

        ttk.Button(radio, text="Apply Radio", command=self.apply_radio).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        filters = ttk.LabelFrame(left, text="Filters", padding=10)
        filters.pack(fill="x", pady=(10, 0))

        ttk.Checkbutton(filters, text="Disable pre/de-emphasis", variable=self.disable_emphasis_var).pack(anchor="w")
        ttk.Checkbutton(filters, text="Disable high-pass", variable=self.disable_highpass_var).pack(anchor="w")
        ttk.Checkbutton(filters, text="Disable low-pass", variable=self.disable_lowpass_var).pack(anchor="w")
        ttk.Button(filters, text="Apply Filters", command=self.apply_filters).pack(fill="x", pady=(8, 0))

        volume = ttk.LabelFrame(left, text="Volume", padding=10)
        volume.pack(fill="x", pady=(10, 0))
        ttk.Scale(volume, from_=1, to=8, variable=self.volume_var, orient="horizontal").pack(fill="x")
        ttk.Button(volume, text="Apply Volume", command=self.apply_volume).pack(fill="x", pady=(8, 0))

        audio = ttk.LabelFrame(left, text="Audio Test / APRS", padding=10)
        audio.pack(fill="x", pady=(10, 0))
        self._row(audio, "Tone Freq (Hz)", ttk.Entry(audio, textvariable=self.test_tone_freq_var, width=16), 0)
        self._row(audio, "Tone Sec", ttk.Entry(audio, textvariable=self.test_tone_duration_var, width=16), 1)
        self._row(audio, "APRS Source", ttk.Entry(audio, textvariable=self.aprs_source_var, width=16), 2)
        self._row(audio, "APRS Dest", ttk.Entry(audio, textvariable=self.aprs_dest_var, width=16), 3)
        self._row(audio, "APRS Path", ttk.Entry(audio, textvariable=self.aprs_path_var, width=16), 4)
        self._row(audio, "APRS Text", ttk.Entry(audio, textvariable=self.aprs_message_var, width=24), 5)
        self.audio_device_combo = ttk.Combobox(audio, textvariable=self.audio_device_var, width=36, state="readonly")
        self._row(audio, "Audio Output", self.audio_device_combo, 6)
        ttk.Checkbutton(audio, text="Key PTT during playback", variable=self.ptt_enabled_var).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        ptt_line_combo = ttk.Combobox(audio, textvariable=self.ptt_line_var, values=["RTS", "DTR"], width=16, state="readonly")
        self._row(audio, "PTT Line", ptt_line_combo, 8)
        ttk.Checkbutton(audio, text="PTT Active High", variable=self.ptt_active_high_var).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(0, 0)
        )
        self._row(audio, "PTT Pre (ms)", ttk.Entry(audio, textvariable=self.ptt_pre_ms_var, width=12), 10)
        self._row(audio, "PTT Post (ms)", ttk.Entry(audio, textvariable=self.ptt_post_ms_var, width=12), 11)
        ttk.Button(audio, text="Refresh Devices", command=self.refresh_audio_devices).grid(row=12, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(audio, text="Play Test Tone", command=self.play_test_tone).grid(row=13, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(audio, text="Play APRS Packet", command=self.play_aprs_packet).grid(row=13, column=1, sticky="ew", pady=(8, 0), padx=(8, 0))
        ttk.Button(audio, text="Stop Audio", command=self.stop_audio).grid(row=14, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        profiles = ttk.LabelFrame(parent, text="Profiles", padding=10)
        profiles.pack(side="left", fill="y", padx=(10, 0))
        ttk.Button(profiles, text="Save Profile", command=self.save_profile).pack(fill="x")
        ttk.Button(profiles, text="Load Profile", command=self.load_profile).pack(fill="x", pady=(8, 0))

        hints = (
            "Hints\n"
            "- Use either CTCSS or DCS, not both\n"
            "- DCS format: 047N or 047I\n"
            "- For no tone, leave tone fields empty"
        )
        ttk.Label(profiles, text=hints, justify="left").pack(anchor="w", pady=(14, 0))

    def _build_aprs_tab(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        left.pack(side="left", fill="both", expand=True)

        tx_msg = ttk.LabelFrame(left, text="APRS Message TX", padding=10)
        tx_msg.pack(fill="x")
        self._row(tx_msg, "Source", ttk.Entry(tx_msg, textvariable=self.aprs_source_var, width=16), 0)
        self._row(tx_msg, "Destination", ttk.Entry(tx_msg, textvariable=self.aprs_dest_var, width=16), 1)
        self._row(tx_msg, "Path", ttk.Entry(tx_msg, textvariable=self.aprs_path_var, width=20), 2)
        self._row(tx_msg, "To (Message)", ttk.Entry(tx_msg, textvariable=self.aprs_msg_to_var, width=16), 3)
        self._row(tx_msg, "Text", ttk.Entry(tx_msg, textvariable=self.aprs_msg_text_var, width=32), 4)
        self._row(tx_msg, "Msg ID (opt)", ttk.Entry(tx_msg, textvariable=self.aprs_msg_id_var, width=10), 5)
        ttk.Checkbutton(tx_msg, text="Reliable Message (ACK/Retry)", variable=self.aprs_reliable_var).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(2, 2)
        )
        self._row(tx_msg, "ACK Timeout (sec)", ttk.Entry(tx_msg, textvariable=self.aprs_ack_timeout_var, width=10), 7)
        self._row(tx_msg, "ACK Retries", ttk.Entry(tx_msg, textvariable=self.aprs_ack_retries_var, width=10), 8)
        self._row(tx_msg, "TX Gain (0.05-0.40)", ttk.Entry(tx_msg, textvariable=self.aprs_tx_gain_var, width=10), 9)
        self._row(tx_msg, "Preamble Flags", ttk.Entry(tx_msg, textvariable=self.aprs_preamble_flags_var, width=10), 10)
        self._row(tx_msg, "TX Repeats", ttk.Entry(tx_msg, textvariable=self.aprs_tx_repeats_var, width=10), 11)
        ttk.Button(tx_msg, text="Send APRS Message", command=self.send_aprs_message).grid(
            row=12, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        tx_pos = ttk.LabelFrame(left, text="APRS Position TX", padding=10)
        tx_pos.pack(fill="x", pady=(10, 0))
        self._row(tx_pos, "Latitude (deg)", ttk.Entry(tx_pos, textvariable=self.aprs_lat_var, width=16), 0)
        self._row(tx_pos, "Longitude (deg)", ttk.Entry(tx_pos, textvariable=self.aprs_lon_var, width=16), 1)
        self._row(tx_pos, "Comment", ttk.Entry(tx_pos, textvariable=self.aprs_comment_var, width=32), 2)
        ttk.Button(tx_pos, text="Send APRS Position", command=self.send_aprs_position).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        rx = ttk.LabelFrame(left, text="APRS RX (Audio Capture Decode)", padding=10)
        rx.pack(fill="x", pady=(10, 0))
        self.aprs_rx_input_combo = ttk.Combobox(rx, textvariable=self.aprs_rx_input_var, width=36, state="readonly")
        self._row(rx, "Input Device", self.aprs_rx_input_combo, 0)
        self._row(rx, "Capture Sec", ttk.Entry(rx, textvariable=self.aprs_rx_duration_var, width=8), 1)
        self._row(rx, "Chunk Sec", ttk.Entry(rx, textvariable=self.aprs_rx_chunk_var, width=8), 2)
        ttk.Checkbutton(
            rx,
            text="Always-on RX Monitor",
            variable=self.aprs_rx_auto_var,
            command=self._on_auto_rx_toggle,
        ).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        ttk.Checkbutton(
            rx,
            text="Auto-ACK direct APRS messages",
            variable=self.aprs_auto_ack_var,
        ).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 0)
        )
        ttk.Button(rx, text="Refresh Inputs", command=self.refresh_input_devices).grid(
            row=5, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(rx, text="Receive APRS", command=self.receive_aprs_capture).grid(
            row=5, column=1, sticky="ew", pady=(8, 0), padx=(8, 0)
        )
        ttk.Button(rx, text="Start RX Monitor", command=self.start_rx_monitor).grid(
            row=6, column=0, sticky="ew", pady=(6, 0)
        )
        ttk.Button(rx, text="Stop RX Monitor", command=self.stop_rx_monitor).grid(
            row=6, column=1, sticky="ew", pady=(6, 0), padx=(8, 0)
        )
        ttk.Button(rx, text="Auto Find Audio Pair", command=self.auto_find_audio_pair).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        ttk.Checkbutton(
            rx,
            text="Auto-select SA818 audio on connect",
            variable=self.auto_audio_select_var,
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            rx,
            text="Re-init SA818 before APRS TX",
            variable=self.aprs_tx_reinit_var,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(0, 0))

        right = ttk.LabelFrame(parent, text="APRS Monitor", padding=8)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.aprs_monitor = ScrolledText(right, height=28)
        self.aprs_monitor.pack(fill="both", expand=True)

    def _build_setup_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Automated setup for third-party SA818 tools").pack(anchor="w")
        ttk.Checkbutton(parent, text="Offline mode (use local fallback snapshots)", variable=self.offline_bootstrap_var).pack(anchor="w", pady=(6, 10))
        ttk.Button(parent, text="Run Third-Party Bootstrap", command=self.run_bootstrap).pack(anchor="w")

        help_text = (
            "Bootstrap does:\n"
            "1. Install/upgrade pip\n"
            "2. Install pyserial\n"
            "3. Clone/pull SA818 and SRFRS repos\n"
            "4. Install SA818 python package\n"
        )
        ttk.Label(parent, text=help_text, justify="left").pack(anchor="w", pady=(12, 0))

    @staticmethod
    def _row(frame: ttk.Frame, label: str, widget: ttk.Widget, row: int) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        widget.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        frame.columnconfigure(1, weight=1)

    def log(self, msg: str) -> None:
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def refresh_ports(self) -> None:
        ports = [p.device for p in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])
        self.log(f"Ports: {ports if ports else 'none'}")

    def refresh_audio_devices(self) -> None:
        entries = ["Default"]
        for idx, name in list_output_devices():
            entries.append(f"{idx}: {name}")
        self.audio_device_combo["values"] = entries
        if self.audio_device_var.get() not in entries:
            self.audio_device_var.set("Default")
        self.log(f"Audio outputs: {entries}")

    def refresh_input_devices(self) -> None:
        entries = ["Default"]
        for idx, name in list_input_devices():
            entries.append(f"{idx}: {name}")
        if hasattr(self, "aprs_rx_input_combo"):
            self.aprs_rx_input_combo["values"] = entries
            if self.aprs_rx_input_var.get() not in entries:
                self.aprs_rx_input_var.set("Default")
        self.log(f"Audio inputs: {entries}")

    def connect(self) -> None:
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Error", "Select a serial port")
            return
        try:
            self.client.connect(port)
        except Exception as exc:  # noqa: BLE001
            self.status_var.set("Disconnected")
            self.log(f"Connect failed: {exc}")
            messagebox.showerror("Connect failed", str(exc))
            return
        self.status_var.set(f"Connected: {port}")
        self.log(f"Connected to {port}")
        if self.auto_audio_select_var.get():
            if self._auto_select_audio_devices():
                self.log("Auto-selected SA818 audio devices")
            else:
                self.log("Auto-select could not determine SA818 audio uniquely; use 'Auto Find Audio Pair'")

    @staticmethod
    def _entry_name(entry: str) -> str:
        token = entry.strip()
        if ":" in token:
            _, name = token.split(":", 1)
            return name.strip()
        return token

    @staticmethod
    def _usb_audio_token(name: str) -> str:
        m = re.search(r"\(([^)]*usb audio device[^)]*)\)", name, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().lower()
        if "usb audio device" in name.lower():
            return name.strip().lower()
        return ""

    def _find_output_entry_by_name(self, name_hint: str) -> str | None:
        hint = name_hint.strip().lower()
        if not hint:
            return None
        for entry in self.audio_device_combo["values"]:
            if self._entry_name(str(entry)).lower() == hint:
                return str(entry)
        return None

    def _find_input_entry_by_name(self, name_hint: str) -> str | None:
        hint = name_hint.strip().lower()
        if not hint or not hasattr(self, "aprs_rx_input_combo"):
            return None
        for entry in self.aprs_rx_input_combo["values"]:
            if self._entry_name(str(entry)).lower() == hint:
                return str(entry)
        return None

    def _update_audio_hints_from_selection(self) -> None:
        out_entry = self.audio_device_var.get().strip()
        in_entry = self.aprs_rx_input_var.get().strip()
        self.sa818_audio_output_hint = self._entry_name(out_entry) if out_entry and out_entry != "Default" else ""
        self.sa818_audio_input_hint = self._entry_name(in_entry) if in_entry and in_entry != "Default" else ""

    def _auto_select_audio_devices(self) -> bool:
        self.refresh_audio_devices()
        self.refresh_input_devices()

        # 1) Reuse previously verified names if still present.
        out_saved = self._find_output_entry_by_name(self.sa818_audio_output_hint)
        in_saved = self._find_input_entry_by_name(self.sa818_audio_input_hint)
        if out_saved and in_saved:
            self.audio_device_var.set(out_saved)
            self.aprs_rx_input_var.set(in_saved)
            return True

        # 2) If exactly one USB output and one USB input exist, use them.
        outs = list_output_devices()
        ins = list_input_devices()
        usb_outs = [(idx, name) for idx, name in outs if "usb audio device" in name.lower()]
        usb_ins = [(idx, name) for idx, name in ins if "usb audio device" in name.lower()]
        if len(usb_outs) == 1 and len(usb_ins) == 1:
            self._set_audio_device_by_index(usb_outs[0][0])
            self._set_input_device_by_index(usb_ins[0][0])
            self._update_audio_hints_from_selection()
            return True

        # 3) Match by shared USB token e.g. "(4- USB Audio Device)" on both endpoints.
        out_by_token: dict[str, list[int]] = {}
        for idx, name in usb_outs:
            t = self._usb_audio_token(name)
            if t:
                out_by_token.setdefault(t, []).append(idx)
        in_by_token: dict[str, list[int]] = {}
        for idx, name in usb_ins:
            t = self._usb_audio_token(name)
            if t:
                in_by_token.setdefault(t, []).append(idx)

        shared = [t for t in out_by_token if t in in_by_token and len(out_by_token[t]) == 1 and len(in_by_token[t]) == 1]
        if len(shared) == 1:
            tok = shared[0]
            self._set_audio_device_by_index(out_by_token[tok][0])
            self._set_input_device_by_index(in_by_token[tok][0])
            self._update_audio_hints_from_selection()
            return True

        return False

    def auto_identify_and_connect(self) -> None:
        ports = [p.device for p in list_ports.comports()]
        if not ports:
            self.log("Auto-identify: no COM ports found")
            messagebox.showerror("Auto Identify", "No serial ports found")
            return

        self.log("Auto-identify started...")
        for port in ports:
            self.log(f"Probing {port}...")
            ok, detail = SA818Client.probe_sa818(port, timeout=0.8)
            if ok:
                self.port_var.set(port)
                self.log(f"SA818 detected on {port} ({detail})")
                try:
                    self.connect()
                    messagebox.showinfo("Auto Identify", f"Connected to SA818 on {port}")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"Auto-connect failed on {port}: {exc}")
                return

        self.log("Auto-identify: SA818 not found on scanned ports")
        messagebox.showwarning("Auto Identify", "No SA818 device found on available COM ports")

    def disconnect(self) -> None:
        stop_playback()
        self.client.disconnect()
        self.status_var.set("Disconnected")
        self.log("Disconnected")

    def read_version(self) -> None:
        try:
            reply = self.client.version()
            self.log(f"Version: {reply}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Read version failed: {exc}")
            messagebox.showerror("Error", str(exc))

    def apply_radio(self) -> None:
        try:
            cfg = RadioConfig(
                frequency=float(self.frequency_var.get().strip()),
                offset=float(self.offset_var.get().strip()),
                bandwidth=1 if self.bandwidth_var.get() == "Wide" else 0,
                squelch=int(self.squelch_var.get().strip()),
                ctcss_tx=self._opt(self.ctcss_tx_var.get()),
                ctcss_rx=self._opt(self.ctcss_rx_var.get()),
                dcs_tx=self._opt(self.dcs_tx_var.get()),
                dcs_rx=self._opt(self.dcs_rx_var.get()),
            )
            if (cfg.ctcss_tx or cfg.ctcss_rx) and (cfg.dcs_tx or cfg.dcs_rx):
                raise SA818Error("Use either CTCSS or DCS, not both")
            reply = self.client.set_radio(cfg)
            self.log(f"Radio set OK: {reply}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Radio set failed: {exc}")
            messagebox.showerror("Error", str(exc))

    def apply_filters(self) -> None:
        try:
            reply = self.client.set_filters(
                disable_emphasis=self.disable_emphasis_var.get(),
                disable_highpass=self.disable_highpass_var.get(),
                disable_lowpass=self.disable_lowpass_var.get(),
            )
            self.log(f"Filters set OK: {reply}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Filter set failed: {exc}")
            messagebox.showerror("Error", str(exc))

    def apply_volume(self) -> None:
        try:
            reply = self.client.set_volume(int(self.volume_var.get()))
            self.log(f"Volume set OK: {reply}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Volume set failed: {exc}")
            messagebox.showerror("Error", str(exc))

    def play_test_tone(self) -> None:
        if platform.system().lower() != "windows":
            messagebox.showerror("Audio", "Audio playback is currently implemented for Windows only")
            return
        try:
            freq = float(self.test_tone_freq_var.get().strip())
            seconds = float(self.test_tone_duration_var.get().strip())
            if freq <= 0 or seconds <= 0:
                raise ValueError("Tone frequency and duration must be > 0")

            AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            wav_path = AUDIO_DIR / f"test_tone_{int(freq)}hz.wav"
            write_test_tone_wav(wav_path, frequency_hz=freq, seconds=seconds)
            self._play_audio_with_optional_ptt(wav_path, "test tone")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Play test tone failed: {exc}")
            messagebox.showerror("Audio Error", str(exc))

    def play_aprs_packet(self) -> None:
        if platform.system().lower() != "windows":
            messagebox.showerror("Audio", "Audio playback is currently implemented for Windows only")
            return
        try:
            text = self.aprs_message_var.get().strip()

            if not text:
                raise ValueError("APRS text is required")
            # Use the same TX engine as APRS tab message/position send to avoid path-specific jitter.
            self._send_aprs_payload(text, "manual")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Play APRS failed: {exc}")
            messagebox.showerror("APRS Audio Error", str(exc))

    def stop_audio(self) -> None:
        stop_playback()
        self._set_ptt_safe()
        self.log("Audio playback stopped")

    def _selected_audio_device(self) -> int | None:
        selected = self.audio_device_var.get().strip()
        if not selected or selected == "Default":
            return None
        token = selected.split(":", 1)[0].strip()
        try:
            return int(token)
        except ValueError:
            return None

    def _require_tx_output_device(self) -> int:
        dev = self._selected_audio_device()
        if dev is not None:
            return dev
        if self.auto_audio_select_var.get() and self._auto_select_audio_devices():
            dev = self._selected_audio_device()
            if dev is not None:
                return dev
        raise RuntimeError(
            "TX audio output is still 'Default'. Select the SA818 output device or run 'Auto Find Audio Pair'."
        )

    def _ptt_timings_sec(self) -> tuple[float, float]:
        pre_ms = float(self.ptt_pre_ms_var.get().strip())
        post_ms = float(self.ptt_post_ms_var.get().strip())
        if pre_ms < 0 or post_ms < 0:
            raise ValueError("PTT pre/post must be >= 0")
        return pre_ms / 1000.0, post_ms / 1000.0

    def _play_audio_with_optional_ptt(self, wav_path: Path, label: str) -> None:
        if self._audio_worker and self._audio_worker.is_alive():
            raise RuntimeError("Audio already playing; stop current playback first")

        def worker() -> None:
            try:
                self._play_audio_with_optional_ptt_blocking(wav_path, label)
            except Exception as exc:  # noqa: BLE001
                self._queue_log(f"Playback worker error: {exc}")
            finally:
                self._queue_log(f"Playback done: {label}")

        self._audio_worker = threading.Thread(target=worker, daemon=True)
        self._audio_worker.start()

    def _play_audio_with_optional_ptt_blocking(self, wav_path: Path, label: str) -> None:
        # Avoid accidental routing through system default device, which breaks APRS consistency.
        tx_dev = self._require_tx_output_device()
        pre_s, post_s = self._ptt_timings_sec()
        ptt_enabled = bool(self.ptt_enabled_var.get())
        ptt_line = self.ptt_line_var.get().strip().upper()
        ptt_active_high = bool(self.ptt_active_high_var.get())
        ptt_used = False
        with self._audio_lock:
            device_idx = tx_dev
            duration = wav_duration_seconds(wav_path)
            self._queue_log(f"Starting {label}: {wav_path} ({duration:.2f}s) [out_dev={device_idx}]")
            try:
                if ptt_enabled:
                    if self.client.connected:
                        self.client.set_ptt(True, line=ptt_line, active_high=ptt_active_high)
                        ptt_used = True
                        self._queue_log("PTT asserted")
                        if pre_s > 0:
                            sleep(pre_s)
                    else:
                        self._queue_log("PTT skipped: radio not connected")

                play_wav_blocking(wav_path, device_index=device_idx)

                if ptt_used and post_s > 0:
                    sleep(post_s)
            finally:
                if ptt_used:
                    try:
                        if self.client.connected:
                            self.client.set_ptt(False, line=ptt_line, active_high=ptt_active_high)
                            self._queue_log("PTT released")
                    except Exception as exc:  # noqa: BLE001
                        self._queue_log(f"Failed to release PTT cleanly: {exc}")

    def _set_ptt_tx(self, enabled: bool) -> None:
        if not self.client.connected:
            self.log("PTT skipped: radio not connected")
            return
        line = self.ptt_line_var.get().strip().upper()
        active_high = self.ptt_active_high_var.get()
        self.client.set_ptt(enabled, line=line, active_high=active_high)

    def _set_ptt_safe(self) -> None:
        if not self.client.connected:
            return
        try:
            self._set_ptt_tx(False)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Failed to release PTT cleanly: {exc}")

    def _selected_input_device(self) -> int | None:
        selected = self.aprs_rx_input_var.get().strip()
        if not selected or selected == "Default":
            return None
        token = selected.split(":", 1)[0].strip()
        try:
            return int(token)
        except ValueError:
            return None

    def _set_audio_device_by_index(self, idx: int) -> None:
        token = f"{idx}:"
        for entry in self.audio_device_combo["values"]:
            if str(entry).startswith(token):
                self.audio_device_var.set(str(entry))
                return
        self.audio_device_var.set("Default")

    def _set_input_device_by_index(self, idx: int) -> None:
        if not hasattr(self, "aprs_rx_input_combo"):
            return
        token = f"{idx}:"
        for entry in self.aprs_rx_input_combo["values"]:
            if str(entry).startswith(token):
                self.aprs_rx_input_var.set(str(entry))
                return
        self.aprs_rx_input_var.set("Default")

    def _aprs_log(self, msg: str) -> None:
        self._ui_queue.put(("aprs", msg, None))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                kind, a, b = self._ui_queue.get_nowait()
                if kind == "aprs":
                    if hasattr(self, "aprs_monitor"):
                        self.aprs_monitor.insert("end", a + "\n")
                        self.aprs_monitor.see("end")
                    self.log(a)
                elif kind == "log":
                    self.log(a)
                elif kind == "error":
                    messagebox.showerror(a, b or "")
                elif kind == "set_audio_pair":
                    out_idx = int(a)
                    in_idx = int(b or "0")
                    self.refresh_audio_devices()
                    self.refresh_input_devices()
                    self._set_audio_device_by_index(out_idx)
                    self._set_input_device_by_index(in_idx)
                    self._update_audio_hints_from_selection()
                    self.log(f"Applied audio pair: output {out_idx}, input {in_idx}")
                elif kind == "auto_ack":
                    try:
                        ack_payload = build_aprs_ack_payload(addressee=a, message_id=(b or ""))
                        self._send_aprs_payload(ack_payload, "ack")
                        self._aprs_log(f"Auto-ACK sent to {a} for {b}")
                    except Exception as exc:  # noqa: BLE001
                        self._aprs_log(f"Auto-ACK failed: {exc}")
        except queue.Empty:
            pass
        self.after(100, self._drain_ui_queue)

    def _queue_log(self, msg: str) -> None:
        self._ui_queue.put(("log", msg, None))

    def _queue_error(self, title: str, msg: str) -> None:
        self._ui_queue.put(("error", title, msg))

    def _queue_auto_ack(self, addressee: str, message_id: str) -> None:
        self._ui_queue.put(("auto_ack", addressee, message_id))

    @staticmethod
    def _call_variants(call: str) -> set[str]:
        c = call.strip().upper()
        base = c.split("-", 1)[0]
        out = {base}
        if c:
            out.add(c)
        return out

    def _make_message_id(self) -> str:
        raw = int(datetime.now().timestamp() * 1000) % 100000
        return f"{raw:05d}"

    def _note_ack(self, message_id: str) -> None:
        mid = message_id.strip()[:5]
        if not mid:
            return
        with self._ack_condition:
            self._acked_message_ids.add(mid)
            self._ack_condition.notify_all()

    def _wait_for_ack(self, message_id: str, timeout_s: float) -> bool:
        mid = message_id.strip()[:5]
        if not mid:
            return False
        deadline = datetime.now().timestamp() + max(0.1, timeout_s)
        with self._ack_condition:
            while True:
                if mid in self._acked_message_ids:
                    self._acked_message_ids.discard(mid)
                    return True
                remain = deadline - datetime.now().timestamp()
                if remain <= 0:
                    return False
                self._ack_condition.wait(timeout=remain)

    def _handle_rx_packet(self, pkt_text: str, pkt_source: str, pkt_info: str) -> None:
        parsed = parse_aprs_message_info(pkt_info)
        if not parsed:
            return
        addressee, msg_text, msg_id = parsed
        local_calls = self._call_variants(self.aprs_source_var.get())
        if addressee not in local_calls:
            return

        if msg_text.lower().startswith("ack"):
            ack_id = msg_text[3:].strip()[:5]
            if ack_id:
                self._note_ack(ack_id)
                self._aprs_log(f"ACK received from {pkt_source} for {ack_id}")
            return

        if not msg_id:
            return
        dedupe_key = f"{pkt_source}|{msg_id}"
        if dedupe_key in self._seen_direct_message_ids:
            return
        self._seen_direct_message_ids.add(dedupe_key)
        if len(self._seen_direct_message_ids) > 400:
            # Keep memory bounded during long monitor runs.
            self._seen_direct_message_ids = set(list(self._seen_direct_message_ids)[-200:])

        if self.aprs_auto_ack_var.get():
            self._queue_auto_ack(pkt_source, msg_id)

    def _send_aprs_payload_blocking(self, payload: str, tag: str) -> None:
        cfg = self._build_tx_config()
        self._send_aprs_payload_blocking_with_config(payload, tag, cfg)

    def _prepare_radio_for_aprs_tx(self) -> None:
        if self.aprs_tx_reinit_var.get():
            port = self.port_var.get().strip()
            if not port:
                raise SA818Error("Select a serial port before APRS TX")
            # Mirror known-good standalone sender behavior: fresh SA818 session before TX.
            self.client.connect(port)
        if not self.client.connected:
            raise SA818Error("Radio must be connected for APRS TX")
        freq = float(self.frequency_var.get().strip())
        bw = 1 if self.bandwidth_var.get() == "Wide" else 0
        # Keep APRS TX setup consistent with known-good diagnostic settings.
        sq = 4
        cfg = RadioConfig(
            frequency=freq,
            offset=0.0,
            bandwidth=bw,
            squelch=sq,
            ctcss_tx=None,
            ctcss_rx=None,
            dcs_tx=None,
            dcs_rx=None,
        )
        self.client.set_radio(cfg)

    def _build_tx_config(self) -> dict[str, object]:
        source = self.aprs_source_var.get().strip().upper()
        destination = self.aprs_dest_var.get().strip().upper()
        path = self.aprs_path_var.get().strip().upper() or "WIDE1-1"
        if not source or not destination:
            raise ValueError("APRS source and destination are required")
        gain = self._aprs_tx_gain()
        preamble_flags = self._aprs_preamble_flags()
        repeats = self._aprs_tx_repeats()
        pre_s, post_s = self._ptt_timings_sec()
        out_dev = self._require_tx_output_device()
        return {
            "source": source,
            "destination": destination,
            "path": path,
            "gain": gain,
            "preamble_flags": preamble_flags,
            "repeats": repeats,
            "pre_s": pre_s,
            "post_s": post_s,
            "out_dev": out_dev,
        }

    def _send_aprs_payload_blocking_with_config(self, payload: str, tag: str, cfg: dict[str, object]) -> None:
        source = str(cfg["source"])
        destination = str(cfg["destination"])
        path = str(cfg["path"])
        gain = float(cfg["gain"])
        preamble_flags = int(cfg["preamble_flags"])

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        wav_path = AUDIO_DIR / f"aprs_tx_{tag}_{ts}.wav"

        write_aprs_wav(
            wav_path,
            source=source,
            destination=destination,
            path_via=path,
            message=payload,
            tx_gain=gain,
            preamble_flags=preamble_flags,
            trailing_flags=12,
        )
        self._transmit_aprs_wav_worker(wav_path, cfg, f"APRS {tag}")
        self._aprs_log(f"TX {source}>{destination},{path}:{payload}")

    def _transmit_aprs_wav_worker(self, wav_path: Path, cfg: dict[str, object], label: str) -> None:
        port = self.port_var.get().strip()
        if not port:
            raise RuntimeError("Serial port is not selected")
        out_dev = int(cfg["out_dev"])
        freq = float(self.frequency_var.get().strip())
        bw = 1 if self.bandwidth_var.get() == "Wide" else 0
        sq = 4
        vol = int(self.volume_var.get())
        ptt_line = self.ptt_line_var.get().strip().upper()
        ptt_active_high = bool(self.ptt_active_high_var.get())
        pre_ms = float(self.ptt_pre_ms_var.get().strip())
        post_ms = float(self.ptt_post_ms_var.get().strip())
        if not self.client.connected:
            self.client.connect(port)
            self.status_var.set(f"Connected: {port}")

        self.client.set_radio(
            RadioConfig(
                frequency=freq,
                offset=0.0,
                bandwidth=bw,
                squelch=sq,
                ctcss_tx=None,
                ctcss_rx=None,
                dcs_tx=None,
                dcs_rx=None,
            )
        )
        self.client.set_volume(max(1, min(8, vol)))

        self._queue_log(f"Starting {label}: {wav_path} [out_dev={out_dev}]")
        with self._audio_lock:
            self.client.set_ptt(True, line=ptt_line, active_high=ptt_active_high)
            try:
                sleep(max(0.0, pre_ms / 1000.0))
                play_wav_blocking(wav_path, device_index=out_dev)
            finally:
                sleep(max(0.0, post_ms / 1000.0))
                self.client.set_ptt(False, line=ptt_line, active_high=ptt_active_high)

    def auto_find_audio_pair(self) -> None:
        if platform.system().lower() != "windows":
            messagebox.showerror("Audio Mapping", "Audio mapping is currently implemented for Windows only")
            return
        if not self.client.connected:
            messagebox.showerror("Audio Mapping", "Connect to a radio first")
            return
        if self._audio_worker and self._audio_worker.is_alive():
            messagebox.showwarning("Audio Mapping", "Audio worker is busy; stop current playback/capture first")
            return

        def rank_output(name: str) -> int:
            s = name.lower()
            if "usb audio" in s:
                return 0
            if "speakers" in s:
                return 1
            return 2

        def rank_input(name: str) -> int:
            s = name.lower()
            if "usb audio" in s:
                return 0
            if "microphone" in s:
                return 1
            return 2

        def worker() -> None:
            aux_client: SA818Client | None = None
            aux_port: str | None = None
            try:
                was_rx_running = self._rx_monitor_running
                self._rx_monitor_running = False
                self._rx_overlap_samples = None

                # Use a second SA818 (if available) as the controlled receiver during calibration.
                this_port = self.port_var.get().strip()
                for p in [cp.device for cp in list_ports.comports()]:
                    if not p or p == this_port:
                        continue
                    ok, _ = SA818Client.probe_sa818(p, timeout=0.6)
                    if ok:
                        aux_port = p
                        break
                if aux_port:
                    aux_client = SA818Client()
                    aux_client.connect(aux_port, timeout=1.2)
                    freq = float(self.frequency_var.get().strip())
                    bw = 1 if self.bandwidth_var.get() == "Wide" else 0
                    aux_client.set_radio(RadioConfig(frequency=freq, offset=0.0, bandwidth=bw, squelch=0))
                    try:
                        aux_client.set_filters(True, True, True)
                    except Exception:
                        pass
                    self._queue_log(f"Calibration receiver SA818 connected on {aux_port}")
                else:
                    self._queue_log("No second SA818 found; calibration may be ambiguous")

                outputs = sorted(list_output_devices(), key=lambda x: (rank_output(x[1]), x[0]))
                inputs = sorted(list_input_devices(), key=lambda x: (rank_input(x[1]), x[0]))
                if not outputs or not inputs:
                    raise RuntimeError("No audio input/output devices were found")
                usb_outputs = [(idx, name) for idx, name in outputs if "usb audio device" in name.lower()]
                usb_inputs = [(idx, name) for idx, name in inputs if "usb audio device" in name.lower()]
                if usb_outputs and usb_inputs:
                    outputs = usb_outputs
                    inputs = usb_inputs
                    self._queue_log("Focusing auto-find on USB audio devices")

                source = self.aprs_source_var.get().strip().upper() or "N0CALL-9"
                destination = self.aprs_dest_var.get().strip().upper() or "APRS"
                path = self.aprs_path_var.get().strip().upper() or "WIDE1-1"
                gain = self._aprs_tx_gain()
                preamble_flags = self._aprs_preamble_flags()
                pre_s, post_s = self._ptt_timings_sec()
                line = self.ptt_line_var.get().strip().upper()
                active_high = self.ptt_active_high_var.get()

                self._queue_log("Audio pair auto-find started")
                self._queue_log(f"Trying {len(outputs)} output(s) x {len(inputs)} input(s)")
                attempts_per_pair = 3
                best: tuple[int, int, int] | None = None  # (hits, out_idx, in_idx)

                for out_idx, out_name in outputs:
                    for in_idx, in_name in inputs:
                        hits = 0
                        self._queue_log(f"Test out {out_idx} ({out_name}) -> in {in_idx} ({in_name})")
                        for attempt in range(1, attempts_per_pair + 1):
                            tag = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                            msg = f"MAP-{out_idx}-{in_idx}-{attempt}-{tag[-4:]}"
                            tx_wav = AUDIO_DIR / f"map_tx_{tag}.wav"
                            rx_wav = AUDIO_DIR / f"map_rx_{tag}.wav"

                            write_aprs_wav(
                                tx_wav,
                                source=source,
                                destination=destination,
                                path_via=path,
                                message=msg,
                                tx_gain=gain,
                                preamble_flags=preamble_flags,
                                trailing_flags=12,
                            )
                            tx_sec = wav_duration_seconds(tx_wav)
                            rec_sec = tx_sec + 1.3

                            rec_exc: list[Exception] = []

                            def rec_worker() -> None:
                                try:
                                    record_wav(rx_wav, seconds=rec_sec, device_index=in_idx)
                                except Exception as exc:  # noqa: BLE001
                                    rec_exc.append(exc)

                            t = threading.Thread(target=rec_worker, daemon=True)
                            with self._audio_lock:
                                t.start()
                                sleep(0.08)
                                self.client.set_ptt(True, line=line, active_high=active_high)
                                try:
                                    if pre_s > 0:
                                        sleep(pre_s)
                                    play_wav_blocking(tx_wav, device_index=out_idx)
                                finally:
                                    if post_s > 0:
                                        sleep(post_s)
                                    self.client.set_ptt(False, line=line, active_high=active_high)
                                t.join()

                            if rec_exc:
                                self._queue_log(f"Capture failed on in {in_idx}: {rec_exc[0]}")
                                continue

                            packets = decode_ax25_from_wav(str(rx_wav))
                            hit = any(msg in pkt.text for pkt in packets)
                            hits += 1 if hit else 0
                        self._queue_log(
                            f"Result out {out_idx} -> in {in_idx}: hits={hits}/{attempts_per_pair}"
                        )
                        if best is None or hits > best[0]:
                            best = (hits, out_idx, in_idx)

                if best and best[0] > 0:
                    _, out_idx, in_idx = best
                    self._ui_queue.put(("set_audio_pair", str(out_idx), str(in_idx)))
                    self._queue_log(f"Audio pair found: output {out_idx}, input {in_idx}")
                else:
                    self._queue_error("Audio Mapping", "No working APRS audio pair found. Check cabling and levels.")
            except Exception as exc:  # noqa: BLE001
                self._queue_error("Audio Mapping", str(exc))
            finally:
                if aux_client:
                    try:
                        aux_client.disconnect()
                        self._queue_log(f"Calibration receiver disconnected ({aux_port})")
                    except Exception:
                        pass
                if was_rx_running and self.aprs_rx_auto_var.get():
                    self.start_rx_monitor()

        self._audio_worker = threading.Thread(target=worker, daemon=True)
        self._audio_worker.start()

    def _send_aprs_payload(self, payload: str, tag: str) -> None:
        cfg = self._build_tx_config()
        repeats = int(cfg["repeats"])
        source = str(cfg["source"])
        destination = str(cfg["destination"])
        path = str(cfg["path"])
        gain = float(cfg["gain"])
        preamble_flags = int(cfg["preamble_flags"])
        pre_s = float(cfg["pre_s"])
        post_s = float(cfg["post_s"])
        out_dev = int(cfg["out_dev"])

        def worker() -> None:
            try:
                self._aprs_log(
                    f"TX config: out_dev={out_dev} gain={gain:.2f} preamble={preamble_flags} "
                    f"repeats={repeats} ptt_pre_ms={int(pre_s*1000)} ptt_post_ms={int(post_s*1000)}"
                )
                for idx in range(repeats):
                    self._send_aprs_payload_blocking_with_config(payload, f"{tag}_{idx + 1}", cfg)
                self._aprs_log(f"TX {source}>{destination},{path}:{payload}")
            except Exception as exc:  # noqa: BLE001
                self._aprs_log(f"TX worker failed: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def send_aprs_message(self) -> None:
        try:
            if self.aprs_reliable_var.get():
                self._send_aprs_message_reliable()
            else:
                payload = build_aprs_message_payload(
                    addressee=self.aprs_msg_to_var.get(),
                    text=self.aprs_msg_text_var.get(),
                    message_id=self.aprs_msg_id_var.get(),
                )
                self._send_aprs_payload(payload, "message")
        except Exception as exc:  # noqa: BLE001
            self._aprs_log(f"Send APRS message failed: {exc}")
            messagebox.showerror("APRS TX Error", str(exc))

    def _send_aprs_message_reliable(self) -> None:
        addressee = self.aprs_msg_to_var.get().strip().upper()
        text = self.aprs_msg_text_var.get().strip()
        if not addressee or not text:
            raise ValueError("Message addressee and text are required")
        message_id = self.aprs_msg_id_var.get().strip()[:5] or self._make_message_id()
        timeout_s = float(self.aprs_ack_timeout_var.get().strip())
        retries = int(self.aprs_ack_retries_var.get().strip())
        if timeout_s <= 0:
            raise ValueError("ACK timeout must be > 0")
        if retries < 1 or retries > 10:
            raise ValueError("ACK retries must be in 1..10")

        payload = build_aprs_message_payload(addressee=addressee, text=text, message_id=message_id)
        cfg = self._build_tx_config()

        def worker() -> None:
            try:
                self._aprs_log(f"Reliable TX started: id={message_id}, retries={retries}, timeout={timeout_s:.1f}s")
                for attempt in range(1, retries + 1):
                    self._send_aprs_payload_blocking_with_config(payload, f"message_rel_{attempt}", cfg)
                    if self._wait_for_ack(message_id, timeout_s):
                        self._aprs_log(f"Reliable TX delivered: ack {message_id} on attempt {attempt}")
                        return
                    self._aprs_log(f"Reliable TX attempt {attempt}: ACK timeout for {message_id}")
                self._aprs_log(f"Reliable TX failed: no ACK for {message_id} after {retries} attempts")
            except Exception as exc:  # noqa: BLE001
                self._aprs_log(f"Reliable TX worker failed: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def send_aprs_position(self) -> None:
        try:
            lat = float(self.aprs_lat_var.get().strip())
            lon = float(self.aprs_lon_var.get().strip())
            payload = build_aprs_position_payload(
                lat_deg=lat,
                lon_deg=lon,
                comment=self.aprs_comment_var.get().strip(),
            )
            self._send_aprs_payload(payload, "position")
        except Exception as exc:  # noqa: BLE001
            self._aprs_log(f"Send APRS position failed: {exc}")
            messagebox.showerror("APRS TX Error", str(exc))

    def receive_aprs_capture(self) -> None:
        if platform.system().lower() != "windows":
            messagebox.showerror("APRS RX", "APRS RX capture is currently implemented for Windows only")
            return
        if self._audio_worker and self._audio_worker.is_alive():
            messagebox.showwarning("APRS RX", "Audio worker is busy; stop current playback/capture first")
            return

        def worker() -> None:
            try:
                secs = float(self.aprs_rx_duration_var.get().strip())
                if secs <= 0:
                    raise ValueError("Capture duration must be > 0")
                AUDIO_DIR.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                wav_path = AUDIO_DIR / f"aprs_rx_{ts}.wav"
                dev = self._selected_input_device()
                self._aprs_log(f"RX capture started ({secs:.1f}s) to {wav_path}")
                with self._audio_lock:
                    record_wav(wav_path, seconds=secs, device_index=dev)
                packets = decode_ax25_from_wav(str(wav_path))
                if not packets:
                    self._aprs_log("RX decode: no APRS packets found")
                    return
                self._aprs_log(f"RX decode: {len(packets)} packet(s)")
                for pkt in packets:
                    self._aprs_log(f"RX {pkt.text}")
                    self._handle_rx_packet(pkt.text, pkt.source, pkt.info)
            except Exception as exc:  # noqa: BLE001
                self._aprs_log(f"Receive APRS failed: {exc}")
                self._queue_error("APRS RX Error", str(exc))

        self._audio_worker = threading.Thread(target=worker, daemon=True)
        self._audio_worker.start()

    def start_rx_monitor(self) -> None:
        if self._rx_monitor_running:
            self._aprs_log("RX monitor already running")
            return
        self._rx_monitor_running = True
        self._rx_overlap_samples = None
        self._rx_monitor_thread = threading.Thread(target=self._rx_monitor_loop, daemon=True)
        self._rx_monitor_thread.start()
        self._aprs_log("RX monitor started")

    def stop_rx_monitor(self) -> None:
        self._rx_monitor_running = False
        self._rx_overlap_samples = None
        self._aprs_log("RX monitor stop requested")

    def _on_auto_rx_toggle(self) -> None:
        if self.aprs_rx_auto_var.get():
            self.start_rx_monitor()
        else:
            self.stop_rx_monitor()

    def _rx_monitor_loop(self) -> None:
        while self._rx_monitor_running:
            try:
                chunk = float(self.aprs_rx_chunk_var.get().strip())
                if chunk <= 0:
                    chunk = 2.0
                dev = self._selected_input_device()
                if not self._audio_lock.acquire(timeout=0.15):
                    sleep(0.05)
                    continue
                try:
                    rate, mono = capture_samples(seconds=chunk, device_index=dev)
                finally:
                    self._audio_lock.release()
                overlap = self._rx_overlap_samples
                if overlap is not None and len(overlap) > 0:
                    decode_samples = np.concatenate((overlap, mono))
                else:
                    decode_samples = mono
                keep = max(1, int(rate * 1.2))
                self._rx_overlap_samples = decode_samples[-keep:].copy()

                packets = decode_ax25_from_samples(rate, decode_samples)
                for pkt in packets:
                    now_ts = datetime.now().timestamp()
                    # Suppress immediate duplicates only (same decode repeated from overlap).
                    if pkt.text == self._last_rx_text and (now_ts - self._last_rx_time) < 2.0:
                        continue
                    self._last_rx_text = pkt.text
                    self._last_rx_time = now_ts
                    self._aprs_log(f"RX {pkt.text}")
                    self._handle_rx_packet(pkt.text, pkt.source, pkt.info)
            except Exception as exc:  # noqa: BLE001
                self._aprs_log(f"RX monitor error: {exc}")
                sleep(1.0)

    def _aprs_tx_gain(self) -> float:
        gain = float(self.aprs_tx_gain_var.get().strip())
        if gain < 0.05 or gain > 0.40:
            raise ValueError("APRS TX gain must be in 0.05..0.40")
        return gain

    def _aprs_preamble_flags(self) -> int:
        n = int(self.aprs_preamble_flags_var.get().strip())
        if n < 16 or n > 400:
            raise ValueError("Preamble flags must be in 16..400")
        return n

    def _aprs_tx_repeats(self) -> int:
        n = int(self.aprs_tx_repeats_var.get().strip())
        if n < 1 or n > 5:
            raise ValueError("TX repeats must be in 1..5")
        return n

    def save_profile(self) -> None:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._update_audio_hints_from_selection()
        data = {
            "frequency": self.frequency_var.get(),
            "offset": self.offset_var.get(),
            "squelch": self.squelch_var.get(),
            "bandwidth": self.bandwidth_var.get(),
            "ctcss_tx": self.ctcss_tx_var.get(),
            "ctcss_rx": self.ctcss_rx_var.get(),
            "dcs_tx": self.dcs_tx_var.get(),
            "dcs_rx": self.dcs_rx_var.get(),
            "disable_emphasis": self.disable_emphasis_var.get(),
            "disable_highpass": self.disable_highpass_var.get(),
            "disable_lowpass": self.disable_lowpass_var.get(),
            "volume": int(self.volume_var.get()),
            "test_tone_freq": self.test_tone_freq_var.get(),
            "test_tone_duration": self.test_tone_duration_var.get(),
            "aprs_source": self.aprs_source_var.get(),
            "aprs_dest": self.aprs_dest_var.get(),
            "aprs_path": self.aprs_path_var.get(),
            "aprs_message": self.aprs_message_var.get(),
            "aprs_msg_to": self.aprs_msg_to_var.get(),
            "aprs_msg_text": self.aprs_msg_text_var.get(),
            "aprs_msg_id": self.aprs_msg_id_var.get(),
            "aprs_reliable": self.aprs_reliable_var.get(),
            "aprs_ack_timeout": self.aprs_ack_timeout_var.get(),
            "aprs_ack_retries": self.aprs_ack_retries_var.get(),
            "aprs_auto_ack": self.aprs_auto_ack_var.get(),
            "aprs_lat": self.aprs_lat_var.get(),
            "aprs_lon": self.aprs_lon_var.get(),
            "aprs_comment": self.aprs_comment_var.get(),
            "aprs_rx_input": self.aprs_rx_input_var.get(),
            "aprs_rx_duration": self.aprs_rx_duration_var.get(),
            "aprs_rx_chunk": self.aprs_rx_chunk_var.get(),
            "aprs_rx_auto": self.aprs_rx_auto_var.get(),
            "aprs_tx_gain": self.aprs_tx_gain_var.get(),
            "aprs_preamble_flags": self.aprs_preamble_flags_var.get(),
            "aprs_tx_repeats": self.aprs_tx_repeats_var.get(),
            "audio_device": self.audio_device_var.get(),
            "sa818_audio_output_hint": self.sa818_audio_output_hint,
            "sa818_audio_input_hint": self.sa818_audio_input_hint,
            "auto_audio_select": self.auto_audio_select_var.get(),
            "aprs_tx_reinit": self.aprs_tx_reinit_var.get(),
            "ptt_enabled": self.ptt_enabled_var.get(),
            "ptt_line": self.ptt_line_var.get(),
            "ptt_active_high": self.ptt_active_high_var.get(),
            "ptt_pre_ms": self.ptt_pre_ms_var.get(),
            "ptt_post_ms": self.ptt_post_ms_var.get(),
        }
        PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.log(f"Profile saved: {PROFILE_PATH}")

    def load_profile(self, silent: bool = False) -> None:
        if not PROFILE_PATH.exists():
            if not silent:
                messagebox.showinfo("Info", "No saved profile found")
            return
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        self.frequency_var.set(data.get("frequency", "145.070"))
        self.offset_var.set(data.get("offset", "0.6"))
        self.squelch_var.set(data.get("squelch", "4"))
        self.bandwidth_var.set(data.get("bandwidth", "Wide"))
        self.ctcss_tx_var.set(data.get("ctcss_tx", ""))
        self.ctcss_rx_var.set(data.get("ctcss_rx", ""))
        self.dcs_tx_var.set(data.get("dcs_tx", ""))
        self.dcs_rx_var.set(data.get("dcs_rx", ""))
        self.disable_emphasis_var.set(bool(data.get("disable_emphasis", True)))
        self.disable_highpass_var.set(bool(data.get("disable_highpass", True)))
        self.disable_lowpass_var.set(bool(data.get("disable_lowpass", True)))
        self.volume_var.set(int(data.get("volume", 5)))
        self.test_tone_freq_var.set(data.get("test_tone_freq", "1200"))
        self.test_tone_duration_var.set(data.get("test_tone_duration", "2.0"))
        self.aprs_source_var.set(data.get("aprs_source", "N0CALL-9"))
        self.aprs_dest_var.set(data.get("aprs_dest", "APRS"))
        self.aprs_path_var.set(data.get("aprs_path", "WIDE1-1"))
        self.aprs_message_var.set(data.get("aprs_message", "uConsole HAM HAT test"))
        self.aprs_msg_to_var.set(data.get("aprs_msg_to", "N0CALL"))
        self.aprs_msg_text_var.set(data.get("aprs_msg_text", "hello from uConsole"))
        self.aprs_msg_id_var.set(data.get("aprs_msg_id", ""))
        self.aprs_reliable_var.set(bool(data.get("aprs_reliable", False)))
        self.aprs_ack_timeout_var.set(data.get("aprs_ack_timeout", "8"))
        self.aprs_ack_retries_var.set(data.get("aprs_ack_retries", "4"))
        self.aprs_auto_ack_var.set(bool(data.get("aprs_auto_ack", True)))
        self.aprs_lat_var.set(data.get("aprs_lat", "49.2827"))
        self.aprs_lon_var.set(data.get("aprs_lon", "-123.1207"))
        self.aprs_comment_var.set(data.get("aprs_comment", "uConsole HAM HAT"))
        self.aprs_rx_input_var.set(data.get("aprs_rx_input", "Default"))
        self.aprs_rx_duration_var.set(data.get("aprs_rx_duration", "10"))
        self.aprs_rx_chunk_var.set(data.get("aprs_rx_chunk", "2.0"))
        self.aprs_rx_auto_var.set(bool(data.get("aprs_rx_auto", False)))
        self.aprs_tx_gain_var.set(data.get("aprs_tx_gain", "0.24"))
        self.aprs_preamble_flags_var.set(data.get("aprs_preamble_flags", "160"))
        self.aprs_tx_repeats_var.set(data.get("aprs_tx_repeats", "1"))
        self.audio_device_var.set(data.get("audio_device", "Default"))
        self.sa818_audio_output_hint = data.get("sa818_audio_output_hint", "")
        self.sa818_audio_input_hint = data.get("sa818_audio_input_hint", "")
        self.auto_audio_select_var.set(bool(data.get("auto_audio_select", True)))
        self.aprs_tx_reinit_var.set(bool(data.get("aprs_tx_reinit", True)))
        self.ptt_enabled_var.set(bool(data.get("ptt_enabled", True)))
        self.ptt_line_var.set(data.get("ptt_line", "RTS"))
        self.ptt_active_high_var.set(bool(data.get("ptt_active_high", True)))
        self.ptt_pre_ms_var.set(data.get("ptt_pre_ms", "400"))
        self.ptt_post_ms_var.set(data.get("ptt_post_ms", "120"))
        if self.auto_audio_select_var.get():
            self._auto_select_audio_devices()
        self.log(f"Profile loaded: {PROFILE_PATH}")

    def run_bootstrap(self) -> None:
        script = APP_DIR / "scripts" / "bootstrap_third_party.py"
        if not script.exists():
            messagebox.showerror("Error", f"Missing script: {script}")
            return

        cmd = [sys.executable, str(script), "--target", str(APP_DIR / "third_party")]
        if self.offline_bootstrap_var.get():
            cmd.append("--offline")

        def worker() -> None:
            self._queue_log(f"Bootstrap starting: {' '.join(cmd)}")
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if proc.stdout:
                    self._queue_log(proc.stdout.strip())
                if proc.stderr:
                    self._queue_log(proc.stderr.strip())
                if proc.returncode == 0:
                    self._queue_log("Bootstrap completed successfully")
                else:
                    self._queue_log(f"Bootstrap failed with exit code {proc.returncode}")
            except Exception as exc:  # noqa: BLE001
                self._queue_log(f"Bootstrap exception: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_close(self) -> None:
        self.stop_rx_monitor()
        stop_playback()
        self._set_ptt_safe()
        try:
            self.client.disconnect()
        except Exception:
            pass
        self.destroy()

    @staticmethod
    def _opt(value: str) -> str | None:
        v = value.strip()
        return v or None


def main() -> int:
    app = HamHatControlApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

