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
import wave
import webbrowser
from ctypes import POINTER, cast
from datetime import datetime
from pathlib import Path
from time import sleep
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import numpy as np
from serial.tools import list_ports
import sounddevice as sd

from aprs_modem import (
    APRS_MESSAGE_TEXT_MAX,
    build_aprs_ack_payload,
    build_group_wire_text,
    build_intro_wire_text,
    build_aprs_message_payload,
    build_aprs_position_payload,
    decode_ax25_from_samples,
    decode_ax25_from_wav,
    parse_intro_wire_text,
    parse_aprs_message_info,
    parse_group_wire_text,
    parse_aprs_position_info,
    split_aprs_text_chunks,
)
from audio_tools import (
    capture_samples,
    list_input_devices,
    list_output_devices,
    play_wav_blocking_compatible,
    record_wav,
    stop_playback,
    wav_duration_seconds,
    write_aprs_wav,
    write_test_tone_wav,
)
from sa818_client import RadioConfig, SA818Client, SA818Error

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, DEVICE_STATE, EDataFlow, IAudioEndpointVolume

    HAS_PYCAW = True
except Exception:
    AudioUtilities = None
    DEVICE_STATE = None
    EDataFlow = None
    IAudioEndpointVolume = None
    CLSCTX_ALL = None
    HAS_PYCAW = False


APP_DIR = Path(__file__).resolve().parents[1]
PROFILE_PATH = APP_DIR / "profiles" / "last_profile.json"
AUDIO_DIR = APP_DIR / "audio_out"
VERSION_PATH = APP_DIR / "VERSION"


def _load_app_version() -> str:
    try:
        txt = VERSION_PATH.read_text(encoding="utf-8").strip()
        return txt or "0.0.0-dev"
    except Exception:
        return "0.0.0-dev"


class HamHatControlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.app_version = _load_app_version()
        self.title(f"uConsole HAM HAT Control Center  |  v{self.app_version}")
        sw = max(900, int(self.winfo_screenwidth()))
        sh = max(620, int(self.winfo_screenheight()))
        ww = max(900, min(1280, sw - 80))
        wh = max(620, min(920, sh - 100))
        self.geometry(f"{ww}x{wh}")
        self.minsize(860, 560)

        self.client = SA818Client()

        self._vars()
        self._build_ui()
        self.log(f"App version: v{self.app_version}")
        self.refresh_ports()
        self.refresh_audio_devices()
        self.refresh_input_devices()
        self.load_profile(silent=True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_ui_queue)
        self._start_audio_visualizer()
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

        self.volume_var = tk.IntVar(value=8)
        self.offline_bootstrap_var = tk.BooleanVar(value=False)
        self.test_tone_freq_var = tk.StringVar(value="1200")
        self.test_tone_duration_var = tk.StringVar(value="2.0")
        self.aprs_source_var = tk.StringVar(value="VA7AYG-00")
        self.aprs_dest_var = tk.StringVar(value="APRS")
        self.aprs_path_var = tk.StringVar(value="WIDE1-1")
        self.aprs_message_var = tk.StringVar(value="uConsole HAM HAT test")
        self.audio_device_var = tk.StringVar(value="Default")
        self.aprs_msg_to_var = tk.StringVar(value="VA7AYG-01")
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
        self.aprs_rx_chunk_var = tk.StringVar(value="8.0")
        self.aprs_rx_trim_db_var = tk.DoubleVar(value=-12.0)
        self.aprs_rx_os_level_var = tk.IntVar(value=35)
        self.aprs_rx_clip_var = tk.StringVar(value="0.0%")
        self.aprs_rx_auto_var = tk.BooleanVar(value=False)
        # Baseline defaults validated over-the-air with handheld decode.
        self.aprs_tx_gain_var = tk.StringVar(value="0.34")
        self.aprs_preamble_flags_var = tk.StringVar(value="240")
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
        self._rx_chunk_floor_logged = False
        self._last_rx_text = ""
        self._last_rx_time = 0.0
        self._recent_rx_times: dict[str, float] = {}
        self._rx_saved_squelch: str | None = None
        self._ui_queue: queue.Queue[tuple[str, str, str | None]] = queue.Queue()
        self._ack_condition = threading.Condition()
        self._acked_message_ids: set[str] = set()
        self._seen_direct_message_ids: set[str] = set()
        self._map_points: list[tuple[float, float, str]] = []
        self._last_aprs_position: tuple[float, float, str] | None = None
        self._map_zoom = 1.0
        self._map_pan_x = 0.0
        self._map_pan_y = 0.0
        self._map_drag_last: tuple[int, int] | None = None
        self._map_pick_radius_px = 8.0
        self.input_level_var = tk.DoubleVar(value=0.0)
        self.output_level_var = tk.DoubleVar(value=0.0)
        self._visualizer_running = False
        self._visualizer_thread: threading.Thread | None = None
        self._visualizer_error_logged = False
        self._tx_active = False
        self._tx_level_hold = 0.0
        self._waterfall_width = 320
        self._waterfall_height = 96
        self._waterfall_target_h = 96
        self._waterfall_buffer = np.zeros((self._waterfall_height, self._waterfall_width), dtype=np.uint8)
        self._waterfall_photo: tk.PhotoImage | None = None
        self._tab_scroll_canvases: list[tk.Canvas] = []
        self._chat_contacts: list[str] = []
        self._heard_stations: list[str] = []
        self._chat_groups: dict[str, list[str]] = {}
        self._chat_messages: list[dict[str, str]] = []
        self._chat_threads_unread: dict[str, int] = {}
        self._active_thread_key = ""
        self._last_direct_sender = ""
        self._intro_seen: set[str] = set()
        self.chat_new_contact_var = tk.StringVar(value="")
        self.chat_group_name_var = tk.StringVar(value="")
        self.chat_group_members_var = tk.StringVar(value="")
        self.chat_compose_var = tk.StringVar(value="")
        self.chat_target_var = tk.StringVar(value="")
        self.chat_intro_note_var = tk.StringVar(value="uConsole HAM HAT online")

    def _build_ui(self) -> None:
        root_pane = ttk.Panedwindow(self, orient="vertical")
        root_pane.pack(fill="both", expand=True, padx=10, pady=(10, 10))

        top_frame = ttk.Frame(root_pane)
        log_frame = ttk.LabelFrame(root_pane, text="Log", padding=8)
        root_pane.add(top_frame, weight=6)
        root_pane.add(log_frame, weight=2)

        top_pane = ttk.Panedwindow(top_frame, orient="vertical")
        top_pane.pack(fill="both", expand=True)
        notebook_frame = ttk.Frame(top_pane)
        spectrum_frame = ttk.Frame(top_pane)
        top_pane.add(notebook_frame, weight=5)
        top_pane.add(spectrum_frame, weight=2)

        version_row = ttk.Frame(notebook_frame)
        version_row.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(version_row, text=f"Version v{self.app_version}").pack(side="right")

        notebook = ttk.Notebook(notebook_frame)
        notebook.pack(fill="both", expand=True)

        main_tab = ttk.Frame(notebook)
        aprs_tab = ttk.Frame(notebook)
        comms_tab = ttk.Frame(notebook)
        setup_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="Main")
        notebook.add(aprs_tab, text="APRS")
        notebook.add(comms_tab, text="Comms")
        notebook.add(setup_tab, text="Setup")

        main_content = self._create_scrollable_tab(main_tab)
        aprs_content = self._create_scrollable_tab(aprs_tab)
        comms_content = self._create_scrollable_tab(comms_tab)
        setup_content = self._create_scrollable_tab(setup_tab)

        self._build_control_tab(main_content)
        self._build_aprs_tab(aprs_content)
        self._build_comms_tab(comms_content)
        self._build_setup_tab(setup_content)

        spectrum = ttk.LabelFrame(spectrum_frame, text="Live Audio Spectrum (All Tabs)", padding=8)
        spectrum.pack(fill="both", expand=True, pady=(6, 0))
        spectrum.columnconfigure(1, weight=1)
        ttk.Label(spectrum, text="Input").grid(row=0, column=0, sticky="w")
        ttk.Progressbar(spectrum, maximum=1.0, variable=self.input_level_var).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Label(spectrum, text="Output").grid(row=0, column=2, sticky="w")
        ttk.Progressbar(spectrum, maximum=1.0, variable=self.output_level_var).grid(row=0, column=3, sticky="ew", padx=(8, 0))
        spectrum.columnconfigure(3, weight=1)
        self._waterfall_width = 640
        self._waterfall_buffer = np.zeros((self._waterfall_height, self._waterfall_width), dtype=np.uint8)
        self.waterfall_canvas = tk.Canvas(
            spectrum,
            width=self._waterfall_width,
            height=self._waterfall_target_h,
            background="#081018",
            highlightthickness=1,
            highlightbackground="#1d3448",
        )
        self.waterfall_canvas.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        spectrum.rowconfigure(1, weight=1)
        self.waterfall_canvas.bind("<Configure>", self._on_waterfall_resize)
        self._waterfall_photo = tk.PhotoImage(width=self._waterfall_width, height=self._waterfall_height)
        self.waterfall_canvas.create_image(0, 0, image=self._waterfall_photo, anchor="nw")

        self.log_text = ScrolledText(log_frame, height=8)
        self.log_text.pack(fill="both", expand=True)

    def _create_scrollable_tab(self, parent: ttk.Frame) -> ttk.Frame:
        container = ttk.Frame(parent, padding=0)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        inner = ttk.Frame(canvas, padding=10)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner_config(_e: tk.Event) -> None:  # type: ignore[type-arg]
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_config(_e: tk.Event) -> None:  # type: ignore[type-arg]
            new_w = canvas.winfo_width()
            new_h = max(canvas.winfo_height(), inner.winfo_reqheight())
            canvas.itemconfigure(win, width=new_w, height=new_h)

        def on_mousewheel(e: tk.Event) -> None:  # type: ignore[type-arg]
            delta = -1 * int(e.delta / 120) if e.delta else 0
            if delta != 0:
                canvas.yview_scroll(delta, "units")

        inner.bind("<Configure>", on_inner_config)
        canvas.bind("<Configure>", on_canvas_config)
        canvas.bind("<MouseWheel>", on_mousewheel)
        self._tab_scroll_canvases.append(canvas)
        return inner

    def _on_waterfall_resize(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        new_w = max(240, int(event.width))
        new_h = max(64, min(140, int(event.height)))
        if new_w == self._waterfall_width and new_h == self._waterfall_height:
            return
        self._waterfall_width = new_w
        self._waterfall_height = new_h
        self._waterfall_buffer = np.zeros((self._waterfall_height, self._waterfall_width), dtype=np.uint8)
        self._waterfall_photo = tk.PhotoImage(width=self._waterfall_width, height=self._waterfall_height)
        self.waterfall_canvas.delete("all")
        self.waterfall_canvas.create_image(0, 0, image=self._waterfall_photo, anchor="nw")

    def _build_control_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)
        parent.columnconfigure(3, weight=1)

        conn = ttk.LabelFrame(parent, text="Connection", padding=8)
        conn.grid(row=0, column=0, columnspan=4, sticky="ew")
        conn.columnconfigure(1, weight=1)
        ttk.Label(conn, text="Serial Port").grid(row=0, column=0, sticky="w", pady=3)
        self.port_combo = ttk.Combobox(conn, textvariable=self.port_var, width=22, state="readonly")
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=(6, 6), pady=3)
        ttk.Label(conn, textvariable=self.status_var).grid(row=0, column=2, sticky="e")

        btn_row = ttk.Frame(conn)
        btn_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        for i in range(5):
            btn_row.columnconfigure(i, weight=1)
        ttk.Button(btn_row, text="Refresh", command=self.refresh_ports).grid(row=0, column=0, sticky="ew")
        ttk.Button(btn_row, text="Auto Identify", command=self.auto_identify_and_connect).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(btn_row, text="Connect", command=self.connect).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ttk.Button(btn_row, text="Disconnect", command=self.disconnect).grid(row=0, column=3, sticky="ew", padx=(6, 0))
        ttk.Button(btn_row, text="Read Version", command=self.read_version).grid(row=0, column=4, sticky="ew", padx=(6, 0))

        radio = ttk.LabelFrame(parent, text="Radio Parameters", padding=8)
        radio.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        radio.columnconfigure(1, weight=1)
        self._row(radio, "Frequency (MHz)", ttk.Entry(radio, textvariable=self.frequency_var, width=14), 0)
        self._row(radio, "Offset (MHz)", ttk.Entry(radio, textvariable=self.offset_var, width=14), 1)
        self._row(radio, "Squelch (0-8)", ttk.Entry(radio, textvariable=self.squelch_var, width=14), 2)
        bw_combo = ttk.Combobox(radio, textvariable=self.bandwidth_var, values=["Wide", "Narrow"], width=12, state="readonly")
        self._row(radio, "Bandwidth", bw_combo, 3)
        ttk.Button(radio, text="Apply Radio", command=self.apply_radio).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        audio = ttk.LabelFrame(parent, text="Audio Routing + Auto Detection", padding=8)
        audio.grid(row=1, column=2, columnspan=2, sticky="nsew", padx=(8, 0), pady=(8, 0))
        audio.columnconfigure(1, weight=1)
        self.audio_device_combo = ttk.Combobox(audio, textvariable=self.audio_device_var, width=34, state="readonly")
        self._row(audio, "Audio Output", self.audio_device_combo, 0)
        self.aprs_rx_input_combo = ttk.Combobox(audio, textvariable=self.aprs_rx_input_var, width=34, state="readonly")
        self._row(audio, "Audio Input", self.aprs_rx_input_combo, 1)
        ttk.Button(audio, text="Refresh Audio Devices", command=self._refresh_all_audio_devices).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Button(audio, text="Auto Find TX/RX Pair", command=self.auto_find_audio_pair).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Button(audio, text="TX Channel Announce Sweep", command=self.tx_channel_announce_sweep).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Button(audio, text="Auto Detect RX by Voice", command=self.auto_detect_input_by_voice).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Checkbutton(
            audio,
            text="Auto-select SA818 audio on connect",
            variable=self.auto_audio_select_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ptt = ttk.LabelFrame(parent, text="PTT", padding=8)
        ptt.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ptt.columnconfigure(1, weight=1)
        ttk.Checkbutton(ptt, text="Key PTT during TX audio", variable=self.ptt_enabled_var).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        ptt_line_combo = ttk.Combobox(ptt, textvariable=self.ptt_line_var, values=["RTS", "DTR"], width=10, state="readonly")
        self._row(ptt, "PTT Line", ptt_line_combo, 1)
        ttk.Checkbutton(ptt, text="PTT Active High", variable=self.ptt_active_high_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        self._row(ptt, "PTT Pre (ms)", ttk.Entry(ptt, textvariable=self.ptt_pre_ms_var, width=10), 3)
        self._row(ptt, "PTT Post (ms)", ttk.Entry(ptt, textvariable=self.ptt_post_ms_var, width=10), 4)

    def _build_aprs_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew")
        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        left.columnconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        identity = ttk.LabelFrame(left, text="APRS Identity + TX Tuning", padding=8)
        identity.pack(fill="x")
        self._row(identity, "Source", ttk.Entry(identity, textvariable=self.aprs_source_var, width=16), 0)
        preset_row = ttk.Frame(identity)
        preset_row.grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Button(preset_row, text="Use VA7AYG-00", command=lambda: self.apply_callsign_preset("VA7AYG-00", "VA7AYG-01")).pack(
            side="left"
        )
        ttk.Button(preset_row, text="Use VA7AYG-01", command=lambda: self.apply_callsign_preset("VA7AYG-01", "VA7AYG-00")).pack(
            side="left", padx=(6, 0)
        )
        self._row(identity, "Destination", ttk.Entry(identity, textvariable=self.aprs_dest_var, width=16), 1)
        self._row(identity, "Path", ttk.Entry(identity, textvariable=self.aprs_path_var, width=20), 2)
        self._row(identity, "TX Gain (0.05-0.40)", ttk.Entry(identity, textvariable=self.aprs_tx_gain_var, width=10), 3)
        self._row(identity, "Preamble Flags", ttk.Entry(identity, textvariable=self.aprs_preamble_flags_var, width=10), 4)
        self._row(identity, "TX Repeats", ttk.Entry(identity, textvariable=self.aprs_tx_repeats_var, width=10), 5)
        ttk.Checkbutton(
            identity,
            text="Re-init SA818 before APRS TX",
            variable=self.aprs_tx_reinit_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 0))

        tx_pos = ttk.LabelFrame(left, text="Position TX", padding=8)
        tx_pos.pack(fill="x", pady=(8, 0))
        self._row(tx_pos, "Latitude (deg)", ttk.Entry(tx_pos, textvariable=self.aprs_lat_var, width=16), 0)
        self._row(tx_pos, "Longitude (deg)", ttk.Entry(tx_pos, textvariable=self.aprs_lon_var, width=16), 1)
        self._row(tx_pos, "Comment", ttk.Entry(tx_pos, textvariable=self.aprs_comment_var, width=32), 2)
        ttk.Button(tx_pos, text="Send Position", command=self.send_aprs_position).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        rx = ttk.LabelFrame(left, text="RX Monitor", padding=8)
        rx.pack(fill="x", pady=(8, 0))
        self._row(rx, "Capture Sec", ttk.Entry(rx, textvariable=self.aprs_rx_duration_var, width=8), 0)
        self._row(rx, "Chunk Sec", ttk.Entry(rx, textvariable=self.aprs_rx_chunk_var, width=8), 1)
        trim_row = ttk.Frame(rx)
        trim_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        trim_row.columnconfigure(1, weight=1)
        ttk.Label(trim_row, text="RX Trim (dB)").grid(row=0, column=0, sticky="w")
        ttk.Scale(
            trim_row,
            variable=self.aprs_rx_trim_db_var,
            from_=-30.0,
            to=0.0,
            orient="horizontal",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Label(trim_row, textvariable=self.aprs_rx_trim_db_var, width=6).grid(row=0, column=2, sticky="e")
        ttk.Label(trim_row, text="Input Clip").grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Label(trim_row, textvariable=self.aprs_rx_clip_var).grid(row=1, column=1, sticky="w", pady=(2, 0))
        os_row = ttk.Frame(rx)
        os_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        os_row.columnconfigure(1, weight=1)
        ttk.Label(os_row, text="OS Mic Level").grid(row=0, column=0, sticky="w")
        ttk.Scale(
            os_row,
            variable=self.aprs_rx_os_level_var,
            from_=1,
            to=100,
            orient="horizontal",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Label(os_row, textvariable=self.aprs_rx_os_level_var, width=4).grid(row=0, column=2, sticky="e")
        ttk.Button(os_row, text="Apply OS Level", command=self.apply_os_rx_level).grid(
            row=0, column=3, sticky="e", padx=(8, 0)
        )
        ttk.Checkbutton(
            rx,
            text="Always-on RX Monitor",
            variable=self.aprs_rx_auto_var,
            command=self._on_auto_rx_toggle,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Checkbutton(
            rx,
            text="Auto-ACK direct messages",
            variable=self.aprs_auto_ack_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Button(rx, text="One-Shot Decode", command=self.receive_aprs_capture).grid(
            row=6, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(rx, text="Start Monitor", command=self.start_rx_monitor).grid(
            row=6, column=1, sticky="ew", pady=(8, 0), padx=(8, 0)
        )
        ttk.Button(rx, text="Stop Monitor", command=self.stop_rx_monitor).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )

        map_box = ttk.LabelFrame(right, text="Stations Map (Offline)", padding=8)
        map_box.grid(row=0, column=0, sticky="nsew")
        map_box.columnconfigure(0, weight=1)
        self.aprs_map_canvas = tk.Canvas(map_box, height=260, background="#10212b", highlightthickness=0)
        self.aprs_map_canvas.grid(row=0, column=0, sticky="nsew")
        self.aprs_map_canvas.bind("<Configure>", lambda _e: self._draw_aprs_map_base())
        self.aprs_map_canvas.bind("<ButtonPress-1>", self._on_map_press)
        self.aprs_map_canvas.bind("<B1-Motion>", self._on_map_drag)
        self.aprs_map_canvas.bind("<ButtonRelease-1>", self._on_map_release)
        self.aprs_map_canvas.bind("<MouseWheel>", self._on_map_mousewheel)
        map_btns = ttk.Frame(map_box)
        map_btns.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(map_btns, text="Clear Map", command=self.clear_aprs_map).pack(side="left")
        ttk.Button(map_btns, text="Open Last In Browser", command=self.open_last_position_in_browser).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(
            map_box,
            text="Offline map plots APRS position packets. Browser button opens last fix on OpenStreetMap.",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        self._draw_aprs_map_base()

        monitor = ttk.LabelFrame(right, text="APRS Monitor", padding=8)
        monitor.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        monitor.rowconfigure(0, weight=1)
        monitor.columnconfigure(0, weight=1)
        self.aprs_monitor = ScrolledText(monitor, height=18)
        self.aprs_monitor.grid(row=0, column=0, sticky="nsew")

    def _build_setup_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        advanced_radio = ttk.LabelFrame(parent, text="Advanced Radio", padding=8)
        advanced_radio.grid(row=0, column=0, sticky="nsew")
        advanced_radio.columnconfigure(1, weight=1)
        self._row(advanced_radio, "CTCSS TX", ttk.Entry(advanced_radio, textvariable=self.ctcss_tx_var, width=16), 0)
        self._row(advanced_radio, "CTCSS RX", ttk.Entry(advanced_radio, textvariable=self.ctcss_rx_var, width=16), 1)
        self._row(advanced_radio, "DCS TX", ttk.Entry(advanced_radio, textvariable=self.dcs_tx_var, width=16), 2)
        self._row(advanced_radio, "DCS RX", ttk.Entry(advanced_radio, textvariable=self.dcs_rx_var, width=16), 3)
        ttk.Button(advanced_radio, text="Apply Radio (With Tone)", command=self.apply_radio).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        ttk.Checkbutton(advanced_radio, text="Disable pre/de-emphasis", variable=self.disable_emphasis_var).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(advanced_radio, text="Disable high-pass", variable=self.disable_highpass_var).grid(
            row=6, column=0, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(advanced_radio, text="Disable low-pass", variable=self.disable_lowpass_var).grid(
            row=7, column=0, columnspan=2, sticky="w"
        )
        ttk.Button(advanced_radio, text="Apply Filters", command=self.apply_filters).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        ttk.Label(advanced_radio, text="Volume").grid(row=9, column=0, sticky="w", pady=(8, 0))
        ttk.Scale(advanced_radio, from_=1, to=8, variable=self.volume_var, orient="horizontal").grid(
            row=9, column=1, sticky="ew", pady=(8, 0)
        )
        ttk.Button(advanced_radio, text="Apply Volume", command=self.apply_volume).grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        tools = ttk.LabelFrame(parent, text="Audio + Profile Tools", padding=8)
        tools.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        tools.columnconfigure(1, weight=1)
        self._row(tools, "Tone Freq (Hz)", ttk.Entry(tools, textvariable=self.test_tone_freq_var, width=12), 0)
        self._row(tools, "Tone Sec", ttk.Entry(tools, textvariable=self.test_tone_duration_var, width=12), 1)
        self._row(tools, "Manual APRS Text", ttk.Entry(tools, textvariable=self.aprs_message_var, width=26), 2)
        ttk.Button(tools, text="Play Test Tone", command=self.play_test_tone).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        ttk.Button(tools, text="Play APRS Packet (Message)", command=self.play_aprs_packet).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Button(tools, text="Stop Audio", command=self.stop_audio).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Separator(tools).grid(row=6, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Button(tools, text="Save Profile", command=self.save_profile).grid(
            row=7, column=0, columnspan=2, sticky="ew"
        )
        ttk.Button(tools, text="Load Profile", command=self.load_profile).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )

        bootstrap = ttk.LabelFrame(parent, text="Third-Party Bootstrap", padding=8)
        bootstrap.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        bootstrap.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            bootstrap,
            text="Offline mode (use local fallback snapshots)",
            variable=self.offline_bootstrap_var,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(bootstrap, text="Run Third-Party Bootstrap", command=self.run_bootstrap).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        help_text = (
            "Bootstrap installs pyserial and syncs SA818/SRFRS tools.\n"
            "Use only when setting up a new machine."
        )
        ttk.Label(bootstrap, text=help_text, justify="left").grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _build_comms_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=3)
        parent.rowconfigure(0, weight=1)

        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew")
        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        left.columnconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        contacts = ttk.LabelFrame(left, text="Contacts", padding=8)
        contacts.pack(fill="both", expand=True)
        contacts.columnconfigure(0, weight=1)
        self.contacts_list = tk.Listbox(contacts, height=8, exportselection=False)
        self.contacts_list.grid(row=0, column=0, sticky="nsew")
        self.contacts_list.bind("<<ListboxSelect>>", lambda _e: self._on_contact_selected())
        add_row = ttk.Frame(contacts)
        add_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        add_row.columnconfigure(0, weight=1)
        ttk.Entry(add_row, textvariable=self.chat_new_contact_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(add_row, text="Add", command=self.add_contact).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(contacts, text="Remove Selected", command=self.remove_selected_contact).grid(
            row=2, column=0, sticky="ew", pady=(6, 0)
        )

        heard = ttk.LabelFrame(left, text="Heard Stations", padding=8)
        heard.pack(fill="both", expand=True, pady=(8, 0))
        heard.columnconfigure(0, weight=1)
        self.heard_list = tk.Listbox(heard, height=6, exportselection=False)
        self.heard_list.grid(row=0, column=0, sticky="nsew")
        ttk.Button(heard, text="Add Heard To Contacts", command=self.add_heard_to_contacts).grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )

        groups = ttk.LabelFrame(left, text="Groups", padding=8)
        groups.pack(fill="both", expand=True, pady=(8, 0))
        groups.columnconfigure(1, weight=1)
        ttk.Label(groups, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(groups, textvariable=self.chat_group_name_var).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(groups, text="Members (CSV)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(groups, textvariable=self.chat_group_members_var).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        ttk.Button(groups, text="Save Group", command=self.save_group_from_fields).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        self.groups_list = tk.Listbox(groups, height=4, exportselection=False)
        self.groups_list.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        self.groups_list.bind("<<ListboxSelect>>", lambda _e: self._on_group_selected())

        target = ttk.LabelFrame(right, text="Conversation", padding=8)
        target.grid(row=0, column=0, sticky="ew")
        target.columnconfigure(0, weight=1)
        ttk.Label(target, text="Selected Thread").grid(row=0, column=0, sticky="w")
        ttk.Label(target, textvariable=self.chat_target_var).grid(row=1, column=0, sticky="w", pady=(2, 4))
        ttk.Button(target, text="Reply Last RX", command=self.reply_last_sender).grid(row=0, column=1, rowspan=2, padx=(8, 0))

        threads = ttk.LabelFrame(right, text="Inbox Threads", padding=8)
        threads.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        threads.columnconfigure(0, weight=1)
        threads.rowconfigure(0, weight=1)
        self.chat_threads_list = tk.Listbox(threads, height=7, exportselection=False)
        self.chat_threads_list.grid(row=0, column=0, sticky="nsew")
        self.chat_threads_list.bind("<<ListboxSelect>>", lambda _e: self._on_thread_selected())

        chat_box = ttk.LabelFrame(right, text="Chat History", padding=8)
        chat_box.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        chat_box.rowconfigure(0, weight=1)
        chat_box.columnconfigure(0, weight=1)
        self.chat_history = ScrolledText(chat_box, height=18)
        self.chat_history.grid(row=0, column=0, sticky="nsew")
        self.chat_history.configure(wrap="word", state="normal")
        self.chat_history.tag_configure("rx_head", foreground="#25526e", font=("Segoe UI", 9, "bold"))
        self.chat_history.tag_configure("rx_body", foreground="#0d2b3e", background="#dff1ff", lmargin1=8, lmargin2=8)
        self.chat_history.tag_configure("tx_head", foreground="#1a5a2a", font=("Segoe UI", 9, "bold"), justify="right")
        self.chat_history.tag_configure("tx_body", foreground="#13361d", background="#e7f9e4", lmargin1=70, lmargin2=70, justify="right")
        self.chat_history.tag_configure("sys", foreground="#6b5f1f", background="#fff7d0", lmargin1=8, lmargin2=8)

        compose = ttk.LabelFrame(right, text="Compose", padding=8)
        compose.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        compose.columnconfigure(0, weight=1)
        ttk.Entry(compose, textvariable=self.chat_compose_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(compose, text="Send To Selected Contact", command=self.send_chat_to_selected_contact).grid(
            row=0, column=1, padx=(6, 0)
        )
        ttk.Button(compose, text="Send To Group", command=self.send_chat_to_selected_group).grid(
            row=0, column=2, padx=(6, 0)
        )
        intro = ttk.LabelFrame(right, text="Discovery", padding=8)
        intro.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        intro.columnconfigure(0, weight=1)
        ttk.Entry(intro, textvariable=self.chat_intro_note_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(intro, text="Broadcast Intro + Location", command=self.send_intro_packet).grid(
            row=0, column=1, padx=(6, 0)
        )

    @staticmethod
    def _row(frame: ttk.Frame, label: str, widget: ttk.Widget, row: int) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        widget.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        frame.columnconfigure(1, weight=1)

    @staticmethod
    def _norm_call(token: str) -> str:
        return token.strip().upper()

    def _refresh_contacts_ui(self) -> None:
        if hasattr(self, "contacts_list"):
            self.contacts_list.delete(0, "end")
            for c in sorted(set(self._chat_contacts)):
                self.contacts_list.insert("end", c)
        if hasattr(self, "heard_list"):
            self.heard_list.delete(0, "end")
            for c in self._heard_stations[-200:]:
                self.heard_list.insert("end", c)
        if hasattr(self, "groups_list"):
            self.groups_list.delete(0, "end")
            for g in sorted(self._chat_groups.keys()):
                members = ",".join(self._chat_groups[g][:6])
                self.groups_list.insert("end", f"{g}: {members}")
        self._refresh_thread_list()

    def _append_chat_message(
        self,
        direction: str,
        src: str,
        dst: str,
        text: str,
        mid: str = "",
        thread: str = "",
        group: str = "",
        remote_copy: str = "",
    ) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        t = thread.strip().upper() or self._infer_thread_key(src, dst, text)
        item = {
            "ts": ts,
            "dir": direction,
            "src": src,
            "dst": dst,
            "text": text,
            "id": mid,
            "thread": t,
            "group": group.strip().upper(),
            "remote_copy": remote_copy.strip().upper(),
        }
        self._chat_messages.append(item)
        if len(self._chat_messages) > 800:
            self._chat_messages = self._chat_messages[-500:]
        if direction == "RX" and t and t != self._active_thread_key:
            self._chat_threads_unread[t] = self._chat_threads_unread.get(t, 0) + 1
        self._refresh_thread_list()
        self._render_chat_history()

    def _render_chat_history(self) -> None:
        if not hasattr(self, "chat_history"):
            return
        target = (self._active_thread_key or self.chat_target_var.get().strip().upper())
        self.chat_history.delete("1.0", "end")
        for m in self._chat_messages:
            if target:
                if m.get("thread", "") != target:
                    continue
            ts = m["ts"]
            src = m["src"]
            text = m["text"]
            msg_id = m.get("id", "")
            if m["dir"] == "TX":
                head = f"{ts}  You -> {m.get('remote_copy') or m['dst']}\n"
                self.chat_history.insert("end", head, "tx_head")
                self.chat_history.insert("end", f"{text}\n", "tx_body")
            elif m["dir"] == "SYS":
                self.chat_history.insert("end", f"{ts}  {text}\n", "sys")
            else:
                head = f"{ts}  {src}\n"
                self.chat_history.insert("end", head, "rx_head")
                self.chat_history.insert("end", f"{text}\n", "rx_body")
            if msg_id:
                self.chat_history.insert("end", f"id:{msg_id}\n", "sys")
            self.chat_history.insert("end", "\n")
        self.chat_history.see("end")

    def _refresh_thread_list(self) -> None:
        if not hasattr(self, "chat_threads_list"):
            return
        last_by_thread: dict[str, dict[str, str]] = {}
        for msg in self._chat_messages:
            t = msg.get("thread", "")
            if t:
                last_by_thread[t] = msg
        for c in self._chat_contacts:
            key = c.upper()
            if key and key not in last_by_thread:
                last_by_thread[key] = {"thread": key, "text": "(new conversation)", "ts": "--:--:--"}
        for g in self._chat_groups:
            key = f"GROUP:{g.upper()}"
            if key not in last_by_thread:
                last_by_thread[key] = {"thread": key, "text": "(group)", "ts": "--:--:--"}
        ordered = sorted(last_by_thread.values(), key=lambda m: m.get("ts", "00:00:00"), reverse=True)
        self.chat_threads_list.delete(0, "end")
        for row in ordered:
            thread = row.get("thread", "")
            preview = row.get("text", "").replace("\n", " ").strip()
            if len(preview) > 36:
                preview = preview[:33] + "..."
            unread = self._chat_threads_unread.get(thread, 0)
            badge = f" ({unread})" if unread > 0 else ""
            label = f"{thread}{badge}  |  {preview}"
            self.chat_threads_list.insert("end", label)
        if self._active_thread_key:
            for idx in range(self.chat_threads_list.size()):
                token = self.chat_threads_list.get(idx).split("|", 1)[0].strip()
                token = token.rsplit("(", 1)[0].strip()
                if token == self._active_thread_key:
                    self.chat_threads_list.selection_clear(0, "end")
                    self.chat_threads_list.selection_set(idx)
                    self.chat_threads_list.see(idx)
                    break

    def _on_thread_selected(self) -> None:
        if not hasattr(self, "chat_threads_list"):
            return
        sel = self.chat_threads_list.curselection()
        if not sel:
            return
        raw = self.chat_threads_list.get(sel[0])
        thread = raw.split("|", 1)[0].strip()
        thread = thread.rsplit("(", 1)[0].strip()
        self._set_active_thread(thread)

    def _set_active_thread(self, thread: str) -> None:
        t = thread.strip().upper()
        if not t:
            return
        self._active_thread_key = t
        self.chat_target_var.set(t)
        self._chat_threads_unread[t] = 0
        self._refresh_thread_list()
        self._render_chat_history()

    def _infer_thread_key(self, src: str, dst: str, text: str) -> str:
        src_u = self._norm_call(src)
        dst_u = self._norm_call(dst)
        g = parse_group_wire_text(text or "")
        if g:
            return f"GROUP:{g[0]}"
        local_calls = self._call_variants(self.aprs_source_var.get())
        if dst_u in local_calls:
            return src_u
        if src_u in local_calls:
            return dst_u
        return src_u or dst_u

    def _split_direct_text(self, text: str) -> list[str]:
        chunks = split_aprs_text_chunks(text, APRS_MESSAGE_TEXT_MAX)
        if len(chunks) <= 1:
            return chunks
        out: list[str] = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            prefix = f"[{idx}/{total}] "
            max_len = APRS_MESSAGE_TEXT_MAX - len(prefix)
            out.append(prefix + chunk[:max(1, max_len)])
        return out

    def _split_group_wire_chunks(self, group: str, text: str) -> list[str]:
        base = build_group_wire_text(group, "")
        max_body = APRS_MESSAGE_TEXT_MAX - len(base)
        if max_body < 8:
            raise ValueError("Group name is too long for APRS messaging")
        body_chunks = split_aprs_text_chunks(text, max_body)
        if len(body_chunks) <= 1:
            return [build_group_wire_text(group, body_chunks[0] if body_chunks else text)]
        total = len(body_chunks)
        out: list[str] = []
        for idx, body in enumerate(body_chunks, start=1):
            envelope = build_group_wire_text(group, "", part=idx, total=total)
            max_wire = APRS_MESSAGE_TEXT_MAX - len(envelope)
            out.append(build_group_wire_text(group, body[:max(1, max_wire)], part=idx, total=total))
        return out

    def _note_heard_station(self, call: str) -> None:
        c = self._norm_call(call)
        if not c:
            return
        if c in self._heard_stations:
            self._heard_stations = [x for x in self._heard_stations if x != c]
        self._heard_stations.append(c)
        if len(self._heard_stations) > 400:
            self._heard_stations = self._heard_stations[-200:]
        self._refresh_contacts_ui()

    def _ensure_contact(self, call: str) -> None:
        c = self._norm_call(call)
        if not c:
            return
        if c not in self._chat_contacts:
            self._chat_contacts.append(c)
        self._refresh_contacts_ui()

    def add_contact(self) -> None:
        c = self._norm_call(self.chat_new_contact_var.get())
        if not c:
            return
        self._ensure_contact(c)
        self.chat_new_contact_var.set("")

    def remove_selected_contact(self) -> None:
        if not hasattr(self, "contacts_list"):
            return
        sel = self.contacts_list.curselection()
        if not sel:
            return
        c = self.contacts_list.get(sel[0]).strip().upper()
        self._chat_contacts = [x for x in self._chat_contacts if x != c]
        self._refresh_contacts_ui()

    def add_heard_to_contacts(self) -> None:
        if not hasattr(self, "heard_list"):
            return
        sel = self.heard_list.curselection()
        if not sel:
            return
        c = self.heard_list.get(sel[0]).strip().upper()
        self._ensure_contact(c)

    def save_group_from_fields(self) -> None:
        name = self.chat_group_name_var.get().strip().upper()
        if not name:
            return
        members = [self._norm_call(x) for x in self.chat_group_members_var.get().split(",")]
        members = [m for m in members if m]
        if not members:
            messagebox.showerror("Group", "Group members are required")
            return
        self._chat_groups[name] = members
        self._refresh_contacts_ui()
        self.log(f"Group saved: {name} ({len(members)} members)")

    def _selected_contact(self) -> str:
        if not hasattr(self, "contacts_list"):
            t = self.chat_target_var.get().strip().upper()
            return "" if t.startswith("GROUP:") else t
        sel = self.contacts_list.curselection()
        if not sel:
            t = self.chat_target_var.get().strip().upper()
            return "" if t.startswith("GROUP:") else t
        return self.contacts_list.get(sel[0]).strip().upper()

    def _selected_group_name(self) -> str:
        if not hasattr(self, "groups_list"):
            return ""
        sel = self.groups_list.curselection()
        if not sel:
            return ""
        token = self.groups_list.get(sel[0])
        return token.split(":", 1)[0].strip().upper()

    def _on_contact_selected(self) -> None:
        c = self._selected_contact()
        if not c:
            return
        self._set_active_thread(c)

    def _on_group_selected(self) -> None:
        g = self._selected_group_name()
        if not g:
            return
        self._set_active_thread(f"GROUP:{g}")
        members = ",".join(self._chat_groups.get(g, []))
        self.chat_group_name_var.set(g)
        self.chat_group_members_var.set(members)

    def _send_chat_payload_to(self, to_call: str, text: str, thread: str, remote_copy: str = "") -> None:
        src = self.aprs_source_var.get().strip().upper()
        chunks = self._split_direct_text(text)
        if not chunks:
            raise ValueError("Message text is required")
        for chunk in chunks:
            msg_id = self._make_message_id()
            payload = build_aprs_message_payload(addressee=to_call, text=chunk, message_id=msg_id)
            self._send_aprs_payload(payload, "chat")
            self._append_chat_message("TX", src, to_call, chunk, msg_id, thread=thread, remote_copy=remote_copy)
        self._set_active_thread(thread)

    def send_chat_to_selected_contact(self) -> None:
        to_call = self._selected_contact()
        if not to_call:
            messagebox.showerror("Comms", "Select a contact first")
            return
        text = self.chat_compose_var.get().strip()
        if not text:
            messagebox.showerror("Comms", "Message text is required")
            return
        self._send_chat_payload_to(to_call, text, thread=to_call)
        self.chat_compose_var.set("")

    def send_intro_packet(self) -> None:
        try:
            call = self.aprs_source_var.get().strip().upper()
            lat = float(self.aprs_lat_var.get().strip())
            lon = float(self.aprs_lon_var.get().strip())
            note = self.chat_intro_note_var.get().strip()
            wire = build_intro_wire_text(call, lat, lon, note=note)
            # Broadcast intro as an APRS message to QST so all peers can discover.
            payload = build_aprs_message_payload(addressee="QST", text=wire, message_id=self._make_message_id())
            self._send_aprs_payload(payload, "intro")
            self._append_chat_message(
                "SYS",
                call,
                "QST",
                f"Intro broadcast: {call} @ {lat:.5f},{lon:.5f} {note}".strip(),
                thread="SYSTEM",
            )
            self._add_aprs_map_point(lat, lon, f"TX {call} INTRO")
            self._ensure_contact(call)
            self._set_active_thread("SYSTEM")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Intro", str(exc))

    def send_chat_to_selected_group(self) -> None:
        g = self._selected_group_name()
        if not g:
            messagebox.showerror("Comms", "Select a group first")
            return
        text = self.chat_compose_var.get().strip()
        if not text:
            messagebox.showerror("Comms", "Message text is required")
            return
        members = self._chat_groups.get(g, [])
        if not members:
            messagebox.showerror("Comms", "Selected group has no members")
            return
        wire_chunks = self._split_group_wire_chunks(g, text)
        src = self.aprs_source_var.get().strip().upper()
        for m in members:
            for chunk in wire_chunks:
                msg_id = self._make_message_id()
                payload = build_aprs_message_payload(addressee=m, text=chunk, message_id=msg_id)
                self._send_aprs_payload(payload, "chat_group")
        display = text if len(wire_chunks) == 1 else f"{text} ({len(wire_chunks)} parts)"
        self._append_chat_message(
            "TX",
            src,
            f"GROUP:{g}",
            display,
            "",
            thread=f"GROUP:{g}",
            group=g,
            remote_copy=f"{len(members)} recipients",
        )
        self.chat_compose_var.set("")
        self._set_active_thread(f"GROUP:{g}")

    def reply_last_sender(self) -> None:
        c = self._norm_call(self._last_direct_sender)
        if not c:
            messagebox.showinfo("Comms", "No direct sender to reply to yet.")
            return
        if c not in self._chat_contacts:
            self._chat_contacts.append(c)
        self._refresh_contacts_ui()
        self._set_active_thread(c)

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

    def _refresh_all_audio_devices(self) -> None:
        self.refresh_audio_devices()
        self.refresh_input_devices()

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
    def _normalize_audio_name(name: str) -> str:
        # Normalize across legacy saved values like "... [Windows WDM-KS]".
        base = re.sub(r"\s*\[[^]]+\]\s*$", "", name.strip(), flags=re.IGNORECASE)
        return " ".join(base.lower().split())

    @staticmethod
    def _usb_audio_token(name: str) -> str:
        m = re.search(r"\(([^)]*usb audio device[^)]*)\)", name, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().lower()
        if "usb audio device" in name.lower():
            return name.strip().lower()
        return ""

    def _find_output_entry_by_name(self, name_hint: str) -> str | None:
        hint = self._normalize_audio_name(name_hint)
        if not hint:
            return None
        for entry in self.audio_device_combo["values"]:
            if self._normalize_audio_name(self._entry_name(str(entry))) == hint:
                return str(entry)
        return None

    def _find_input_entry_by_name(self, name_hint: str) -> str | None:
        hint = self._normalize_audio_name(name_hint)
        if not hint or not hasattr(self, "aprs_rx_input_combo"):
            return None
        for entry in self.aprs_rx_input_combo["values"]:
            if self._normalize_audio_name(self._entry_name(str(entry))) == hint:
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
        self._tx_active = False
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
            # Emit a valid APRS message payload rather than raw text.
            payload = build_aprs_message_payload(
                addressee=self.aprs_msg_to_var.get(),
                text=text,
                message_id=self.aprs_msg_id_var.get(),
            )
            # Use the same TX engine as APRS tab message/position send to avoid path-specific jitter.
            self._send_aprs_payload(payload, "manual")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Play APRS failed: {exc}")
            messagebox.showerror("APRS Audio Error", str(exc))

    def stop_audio(self) -> None:
        stop_playback()
        self._tx_active = False
        self._queue_output_level(0.0)
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

    @staticmethod
    def _estimate_wav_level(path: Path) -> float:
        try:
            with wave.open(str(path), "rb") as wavf:
                width = wavf.getsampwidth()
                channels = wavf.getnchannels()
                raw = wavf.readframes(wavf.getnframes())
            if width != 2:
                return 0.6
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            if channels > 1:
                x = x.reshape(-1, channels)[:, 0]
            rms = float(np.sqrt(np.mean((x / 32768.0) ** 2)))
            return max(0.05, min(1.0, rms * 6.0))
        except Exception:
            return 0.6

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

                self._tx_level_hold = self._estimate_wav_level(wav_path)
                self._tx_active = True
                self._play_wav_on_device_compatible(wav_path, device_idx)
                self._tx_active = False

                if ptt_used and post_s > 0:
                    sleep(post_s)
            finally:
                self._tx_active = False
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

    def _record_wav_compatible(self, path: Path, seconds: float, device_index: int | None = None) -> None:
        # Some Windows USB audio drivers fail when opened from background threads.
        if platform.system().lower() == "windows" and threading.current_thread() is not threading.main_thread():
            script = APP_DIR / "scripts" / "capture_wav_worker.py"
            if not script.exists():
                raise RuntimeError(f"Missing script: {script}")
            dev = -1 if device_index is None else int(device_index)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--wav",
                    str(path),
                    "--seconds",
                    f"{float(seconds):.3f}",
                    "--input-device",
                    str(dev),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()
                raise RuntimeError(detail)
            return
        record_wav(path, seconds=seconds, device_index=device_index)

    def _capture_samples_compatible(self, seconds: float, device_index: int | None = None) -> tuple[int, np.ndarray]:
        if platform.system().lower() != "windows" or threading.current_thread() is threading.main_thread():
            return capture_samples(seconds=seconds, device_index=device_index)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        wav_path = AUDIO_DIR / f"rx_chunk_{ts}.wav"
        self._record_wav_compatible(wav_path, seconds=seconds, device_index=device_index)
        with wave.open(str(wav_path), "rb") as wavf:
            rate = int(wavf.getframerate())
            channels = int(wavf.getnchannels())
            frames = wavf.readframes(wavf.getnframes())
        mono = np.frombuffer(frames, dtype=np.int16)
        if channels > 1:
            mono = mono.reshape(-1, channels)[:, 0]
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass
        return rate, mono.astype(np.float32) / 32768.0

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

    def _draw_aprs_map_base(self) -> None:
        if not hasattr(self, "aprs_map_canvas"):
            return
        c = self.aprs_map_canvas
        c.delete("all")
        w = max(10, int(c.winfo_width() or c.cget("width")))
        h = max(10, int(c.winfo_height() or c.cget("height")))
        c.create_rectangle(0, 0, w, h, fill="#0f2531", outline="")
        for lon in range(-180, 181, 30):
            x, _ = self._latlon_to_map_xy(0.0, float(lon), w, h)
            if 0 <= x <= w:
                c.create_line(x, 0, x, h, fill="#21465d")
        for lat in range(-90, 91, 15):
            _, y = self._latlon_to_map_xy(float(lat), 0.0, w, h)
            if 0 <= y <= h:
                c.create_line(0, y, w, y, fill="#21465d")
        c.create_text(8, 8, anchor="nw", text="Offline APRS Map (drag to pan, wheel to zoom)", fill="#d9edf7")
        self._redraw_aprs_map_points()

    def _latlon_to_map_xy(self, lat: float, lon: float, width: int, height: int) -> tuple[float, float]:
        lon_c = max(-180.0, min(180.0, lon))
        lat_c = max(-90.0, min(90.0, lat))
        world_w = width * self._map_zoom
        world_h = height * self._map_zoom
        world_x = ((lon_c + 180.0) / 360.0) * world_w
        world_y = ((90.0 - lat_c) / 180.0) * world_h
        x = world_x - self._map_pan_x
        y = world_y - self._map_pan_y
        return x, y

    def _map_xy_to_latlon(self, x: float, y: float, width: int, height: int) -> tuple[float, float]:
        world_w = width * self._map_zoom
        world_h = height * self._map_zoom
        world_x = x + self._map_pan_x
        world_y = y + self._map_pan_y
        lon = (world_x / max(1.0, world_w)) * 360.0 - 180.0
        lat = 90.0 - (world_y / max(1.0, world_h)) * 180.0
        return max(-90.0, min(90.0, lat)), max(-180.0, min(180.0, lon))

    def _redraw_aprs_map_points(self) -> None:
        if not hasattr(self, "aprs_map_canvas"):
            return
        c = self.aprs_map_canvas
        w = max(10, int(c.winfo_width() or c.cget("width")))
        h = max(10, int(c.winfo_height() or c.cget("height")))
        if not self._map_points:
            c.create_text(w / 2, h / 2, text="No APRS positions yet", fill="#9cc4dd")
            return
        for lat, lon, label in self._map_points[-120:]:
            x, y = self._latlon_to_map_xy(lat, lon, w, h)
            if x < -10 or y < -10 or x > (w + 10) or y > (h + 10):
                continue
            c.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#ffd166", outline="")
            c.create_text(x + 6, y - 6, anchor="nw", text=label[:18], fill="#f5f7fa")

    def _on_map_press(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._map_drag_last = (int(event.x), int(event.y))

    def _on_map_drag(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._map_drag_last is None:
            return
        lx, ly = self._map_drag_last
        dx = int(event.x) - lx
        dy = int(event.y) - ly
        self._map_pan_x -= dx
        self._map_pan_y -= dy
        self._map_drag_last = (int(event.x), int(event.y))
        self._draw_aprs_map_base()

    def _on_map_release(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        click = self._map_drag_last is not None and abs(int(event.x) - self._map_drag_last[0]) < 4 and abs(int(event.y) - self._map_drag_last[1]) < 4
        self._map_drag_last = None
        if not click:
            return
        # If clicked near a station, show details.
        if not hasattr(self, "aprs_map_canvas"):
            return
        c = self.aprs_map_canvas
        w = max(10, int(c.winfo_width() or c.cget("width")))
        h = max(10, int(c.winfo_height() or c.cget("height")))
        ex = float(event.x)
        ey = float(event.y)
        nearest: tuple[float, float, str, float] | None = None
        for lat, lon, label in self._map_points[-120:]:
            x, y = self._latlon_to_map_xy(lat, lon, w, h)
            d = ((x - ex) ** 2 + (y - ey) ** 2) ** 0.5
            if nearest is None or d < nearest[3]:
                nearest = (lat, lon, label, d)
        if nearest and nearest[3] <= self._map_pick_radius_px:
            lat, lon, label, _ = nearest
            self._aprs_log(f"Map pick: {label} @ {lat:.5f}, {lon:.5f}")

    def _on_map_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not hasattr(self, "aprs_map_canvas"):
            return
        c = self.aprs_map_canvas
        w = max(10, int(c.winfo_width() or c.cget("width")))
        h = max(10, int(c.winfo_height() or c.cget("height")))
        pivot_x = float(event.x)
        pivot_y = float(event.y)
        lat0, lon0 = self._map_xy_to_latlon(pivot_x, pivot_y, w, h)
        factor = 1.15 if event.delta > 0 else (1.0 / 1.15)
        self._map_zoom = max(1.0, min(8.0, self._map_zoom * factor))
        nx, ny = self._latlon_to_map_xy(lat0, lon0, w, h)
        self._map_pan_x += (nx - pivot_x)
        self._map_pan_y += (ny - pivot_y)
        self._draw_aprs_map_base()

    def _add_aprs_map_point(self, lat: float, lon: float, label: str) -> None:
        self._map_points.append((lat, lon, label))
        if len(self._map_points) > 200:
            self._map_points = self._map_points[-120:]
        if len(self._map_points) == 1 and hasattr(self, "aprs_map_canvas"):
            w = max(10, int(self.aprs_map_canvas.winfo_width() or self.aprs_map_canvas.cget("width")))
            h = max(10, int(self.aprs_map_canvas.winfo_height() or self.aprs_map_canvas.cget("height")))
            world_w = w * self._map_zoom
            world_h = h * self._map_zoom
            world_x = ((max(-180.0, min(180.0, lon)) + 180.0) / 360.0) * world_w
            world_y = ((90.0 - max(-90.0, min(90.0, lat))) / 180.0) * world_h
            self._map_pan_x = world_x - (w / 2.0)
            self._map_pan_y = world_y - (h / 2.0)
        self._last_aprs_position = (lat, lon, label)
        self._draw_aprs_map_base()

    def clear_aprs_map(self) -> None:
        self._map_points.clear()
        self._last_aprs_position = None
        self._map_zoom = 1.0
        self._map_pan_x = 0.0
        self._map_pan_y = 0.0
        self._draw_aprs_map_base()
        self._aprs_log("Map cleared")

    def open_last_position_in_browser(self) -> None:
        if not self._last_aprs_position:
            messagebox.showinfo("Map", "No APRS position plotted yet.")
            return
        lat, lon, _ = self._last_aprs_position
        url = f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=13/{lat:.6f}/{lon:.6f}"
        webbrowser.open(url, new=2)

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
                elif kind == "set_input_device":
                    in_idx = int(a)
                    self.refresh_input_devices()
                    self._set_input_device_by_index(in_idx)
                    self._update_audio_hints_from_selection()
                    self.log(f"Applied input device: {in_idx}")
                elif kind == "map_point":
                    lat = float(a)
                    payload = (b or "").split("|", 1)
                    lon = float(payload[0]) if payload and payload[0] else 0.0
                    label = payload[1] if len(payload) > 1 else "APRS"
                    self._add_aprs_map_point(lat, lon, label)
                elif kind == "meter_in":
                    self.input_level_var.set(max(0.0, min(1.0, float(a))))
                elif kind == "meter_out":
                    self.output_level_var.set(max(0.0, min(1.0, float(a))))
                elif kind == "rx_clip":
                    self.aprs_rx_clip_var.set(a)
                elif kind == "wf_row":
                    self._push_waterfall_row(a)
                elif kind == "heard_station":
                    self._note_heard_station(a)
                elif kind == "auto_contact":
                    self._ensure_contact(a)
                elif kind == "chat_msg":
                    try:
                        data = json.loads(b or "{}")
                    except Exception:
                        data = {}
                    src = str(data.get("src", ""))
                    dst = str(data.get("dst", ""))
                    text = str(data.get("text", ""))
                    mid = str(data.get("id", ""))
                    thread = str(data.get("thread", ""))
                    group = str(data.get("group", ""))
                    remote_copy = str(data.get("remote_copy", ""))
                    if src and dst:
                        self._append_chat_message(a, src, dst, text, mid, thread=thread, group=group, remote_copy=remote_copy)
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

    def _queue_map_point(self, lat: float, lon: float, label: str) -> None:
        self._ui_queue.put(("map_point", f"{lat:.6f}", f"{lon:.6f}|{label}"))

    def _queue_input_level(self, level: float) -> None:
        self._ui_queue.put(("meter_in", f"{level:.4f}", None))

    def _queue_output_level(self, level: float) -> None:
        self._ui_queue.put(("meter_out", f"{level:.4f}", None))

    def _queue_waterfall_row(self, row: str) -> None:
        self._ui_queue.put(("wf_row", row, None))

    def _queue_rx_clip(self, clip_percent: float) -> None:
        self._ui_queue.put(("rx_clip", f"{max(0.0, clip_percent):.1f}%", None))

    def _queue_heard_station(self, call: str) -> None:
        self._ui_queue.put(("heard_station", call, None))

    def _queue_auto_contact(self, call: str) -> None:
        self._ui_queue.put(("auto_contact", call, None))

    def _queue_chat_message(
        self,
        direction: str,
        src: str,
        dst: str,
        text: str,
        mid: str = "",
        thread: str = "",
        group: str = "",
        remote_copy: str = "",
    ) -> None:
        data = {
            "src": src,
            "dst": dst,
            "text": text,
            "id": mid,
            "thread": thread,
            "group": group,
            "remote_copy": remote_copy,
        }
        self._ui_queue.put(("chat_msg", direction, json.dumps(data)))

    @staticmethod
    def _wf_color(v: int) -> str:
        x = max(0, min(255, int(v)))
        if x < 64:
            r, g, b = 0, 0, 30 + (x * 2)
        elif x < 128:
            t = x - 64
            r, g, b = 0, t * 3, 160 + (t // 2)
        elif x < 192:
            t = x - 128
            r, g, b = t * 3, 180 + t, 255 - t * 3
        else:
            t = x - 192
            r, g, b = 200 + t * 2, 255 - t, 60 - min(60, t * 2)
        return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"

    def _push_waterfall_row(self, row: str) -> None:
        if self._waterfall_photo is None:
            return
        tokens = row.split(",")
        if len(tokens) < self._waterfall_width:
            return
        arr = np.array([int(t) for t in tokens[: self._waterfall_width]], dtype=np.uint8)
        self._waterfall_buffer[:-1, :] = self._waterfall_buffer[1:, :]
        self._waterfall_buffer[-1, :] = arr
        h = self._waterfall_height
        rows = []
        for y in range(h):
            line = "{" + " ".join(self._wf_color(v) for v in self._waterfall_buffer[y, :]) + "}"
            rows.append(line)
        self._waterfall_photo.put(" ".join(rows), to=(0, 0, self._waterfall_width, h))

    @staticmethod
    def _level_from_samples(mono: np.ndarray) -> float:
        if len(mono) == 0:
            return 0.0
        x = np.asarray(mono, dtype=np.float32).reshape(-1)
        return float(np.sqrt(np.mean(x * x)))

    @staticmethod
    def _clip_percent(mono: np.ndarray) -> float:
        x = np.asarray(mono, dtype=np.float32).reshape(-1)
        if len(x) == 0:
            return 0.0
        return float(np.mean(np.abs(x) >= 0.98) * 100.0)

    def _rx_trimmed_samples(self, mono: np.ndarray) -> np.ndarray:
        x = np.asarray(mono, dtype=np.float32).reshape(-1)
        try:
            db = float(self.aprs_rx_trim_db_var.get())
        except Exception:
            db = -12.0
        db = min(0.0, max(-30.0, db))
        gain = float(10.0 ** (db / 20.0))
        y = np.clip(x * gain, -1.0, 1.0)
        return y.astype(np.float32, copy=False)

    def apply_os_rx_level(self) -> None:
        if platform.system().lower() != "windows":
            messagebox.showerror("OS Mic Level", "OS-level mic control is available on Windows only")
            return
        if not HAS_PYCAW:
            messagebox.showerror(
                "OS Mic Level",
                "Missing backend: install with `python -m pip install pycaw comtypes`.",
            )
            return
        selected = self.aprs_rx_input_var.get().strip()
        if not selected or selected == "Default":
            messagebox.showerror("OS Mic Level", "Select an APRS Audio Input first")
            return
        level = max(1, min(100, int(self.aprs_rx_os_level_var.get())))
        target_name = self._entry_name(selected)
        target_norm = self._normalize_audio_name(target_name)
        target_token = self._usb_audio_token(target_name)
        try:
            enum = AudioUtilities.GetDeviceEnumerator()
            coll = enum.EnumAudioEndpoints(EDataFlow.eCapture.value, DEVICE_STATE.ACTIVE.value)
            count = coll.GetCount()
            best = None
            for i in range(count):
                dev = coll.Item(i)
                ad = AudioUtilities.CreateDevice(dev)
                friendly = str(ad.FriendlyName)
                fn = self._normalize_audio_name(friendly)
                tok = self._usb_audio_token(friendly)
                score = 0
                if fn == target_norm:
                    score += 10
                if target_token and tok == target_token:
                    score += 6
                if target_token and target_token in fn:
                    score += 3
                if "usb audio device" in fn and "usb audio device" in target_norm:
                    score += 1
                if best is None or score > best[0]:
                    best = (score, dev, friendly)
            if best is None or best[0] <= 0:
                raise RuntimeError(f"No matching OS capture endpoint for '{target_name}'")
            _, dev, friendly = best
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
            vol.SetMute(0, None)
            vol.SetMasterVolumeLevelScalar(float(level) / 100.0, None)
            self._aprs_log(f"OS mic level set to {level}% on '{friendly}'")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("OS Mic Level", str(exc))

    def _spectrum_row_from_samples(self, rate: int, mono: np.ndarray) -> str:
        x = np.asarray(mono, dtype=np.float32).reshape(-1)
        if len(x) < 256:
            return ",".join(["0"] * self._waterfall_width)
        x = x - float(np.mean(x))
        nfft = 1024
        if len(x) < nfft:
            pad = np.zeros(nfft, dtype=np.float32)
            pad[: len(x)] = x
            xw = pad
        else:
            xw = x[-nfft:]
        xw = xw * np.hanning(len(xw))
        spec = np.fft.rfft(xw)
        mag = np.abs(spec)
        freqs = np.fft.rfftfreq(len(xw), d=(1.0 / float(rate)))
        mask = (freqs >= 0.0) & (freqs <= 3000.0)
        mag = mag[mask]
        if len(mag) < 8:
            return ",".join(["0"] * self._waterfall_width)
        tgt_x = np.linspace(0, len(mag) - 1, self._waterfall_width)
        vals = np.interp(tgt_x, np.arange(len(mag)), mag)
        vals = np.log10(1.0 + vals)
        vmax = float(np.max(vals))
        if vmax > 1e-9:
            vals = vals / vmax
        bins = np.clip((vals * 255.0).astype(np.int32), 0, 255)
        return ",".join(str(int(v)) for v in bins.tolist())

    def _start_audio_visualizer(self) -> None:
        if self._visualizer_running:
            return
        self._visualizer_running = True
        self._visualizer_error_logged = False

        def worker() -> None:
            out_level = 0.0
            poll_s = 0.28 if platform.system().lower() == "windows" else 0.12
            while self._visualizer_running:
                try:
                    if self._tx_active:
                        out_level = max(out_level, self._tx_level_hold)
                    else:
                        out_level *= 0.86
                    self._queue_output_level(out_level)

                    # On Windows, background capture uses a subprocess path. Let RX monitor own
                    # input capture to avoid lock contention and packet loss during APRS monitoring.
                    if self._rx_monitor_running:
                        sleep(poll_s)
                        continue

                    if self._audio_lock.acquire(timeout=0.02):
                        try:
                            dev = self._selected_input_device()
                            rate, mono = self._capture_samples_compatible(seconds=poll_s, device_index=dev)
                        finally:
                            self._audio_lock.release()
                        in_level = min(1.0, self._level_from_samples(mono) * 8.0)
                        self._queue_input_level(in_level)
                        self._queue_waterfall_row(self._spectrum_row_from_samples(rate, mono))
                    sleep(poll_s)
                except Exception as exc:
                    if not self._visualizer_error_logged:
                        self._queue_log(f"Visualizer capture fallback error: {exc}")
                        self._visualizer_error_logged = True
                    sleep(0.2)

        self._visualizer_thread = threading.Thread(target=worker, daemon=True)
        self._visualizer_thread.start()

    def _stop_audio_visualizer(self) -> None:
        self._visualizer_running = False

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
        self._queue_heard_station(pkt_source)
        pos = parse_aprs_position_info(pkt_info)
        if pos:
            lat, lon, comment = pos
            label = pkt_source
            if comment:
                label = f"{pkt_source} {comment[:16]}"
            self._queue_map_point(lat, lon, label)
            self._aprs_log(f"RX position {pkt_source}: {lat:.5f}, {lon:.5f}")

        parsed = parse_aprs_message_info(pkt_info)
        if not parsed:
            return
        addressee, msg_text, msg_id = parsed
        local_calls = self._call_variants(self.aprs_source_var.get())
        intro = parse_intro_wire_text(msg_text)
        if intro:
            intro_call, lat_i, lon_i, note_i = intro
            # Prefer on-air packet source as ground truth for contact identity.
            src_call = self._norm_call(pkt_source) or intro_call
            key = f"{src_call}|{lat_i:.5f}|{lon_i:.5f}|{note_i}"
            if key not in self._intro_seen:
                self._intro_seen.add(key)
                self._queue_auto_contact(src_call)
                label = f"{src_call} INTRO"
                if note_i:
                    label = f"{src_call} {note_i[:14]}"
                self._queue_map_point(lat_i, lon_i, label)
                note_suffix = f" - {note_i}" if note_i else ""
                self._queue_chat_message(
                    "SYS",
                    src_call,
                    "QST",
                    f"Intro from {src_call} @ {lat_i:.5f},{lon_i:.5f}{note_suffix}",
                    "",
                    thread="SYSTEM",
                )
        if msg_text.lower().startswith("ack"):
            ack_id = msg_text[3:].strip()[:5]
            if ack_id:
                self._note_ack(ack_id)
                self._aprs_log(f"ACK received from {pkt_source} for {ack_id}")
            return

        group_wire = parse_group_wire_text(msg_text)
        thread = self._infer_thread_key(pkt_source, addressee, msg_text)
        display_text = msg_text
        group_name = ""
        if group_wire:
            group_name, body, part, total = group_wire
            if part and total:
                display_text = f"[{part}/{total}] {body}"
            else:
                display_text = body
            thread = f"GROUP:{group_name}"

        self._queue_chat_message(
            "RX",
            pkt_source,
            addressee,
            display_text,
            msg_id or "",
            thread=thread,
            group=group_name,
        )

        if addressee not in local_calls:
            return
        self._last_direct_sender = pkt_source

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
            trailing_flags=16,
        )
        self._transmit_aprs_wav_worker(wav_path, cfg, f"APRS {tag}")

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
        # Keep TX modulation path flat for APRS tones.
        try:
            self.client.set_filters(True, True, True)
        except Exception as exc:  # noqa: BLE001
            self._queue_log(f"Filter set warning before TX: {exc}")
        self.client.set_volume(max(1, min(8, vol)))

        self._queue_log(f"Starting {label}: {wav_path} [out_dev={out_dev}]")
        with self._audio_lock:
            self.client.set_ptt(True, line=ptt_line, active_high=ptt_active_high)
            try:
                sleep(max(0.0, pre_ms / 1000.0))
                self._tx_level_hold = self._estimate_wav_level(wav_path)
                self._tx_active = True
                self._play_wav_on_device_compatible(wav_path, out_dev)
            finally:
                self._tx_active = False
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
                                    self._record_wav_compatible(rx_wav, seconds=rec_sec, device_index=in_idx)
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
                                    self._tx_level_hold = self._estimate_wav_level(tx_wav)
                                    self._tx_active = True
                                    self._play_wav_on_device_compatible(tx_wav, out_idx)
                                finally:
                                    self._tx_active = False
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

    @staticmethod
    def _voice_activity_score(samples: np.ndarray) -> float:
        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if len(x) < 32:
            return 0.0
        x = x - float(np.mean(x))
        rms = float(np.sqrt(np.mean(x * x)))
        p95 = float(np.percentile(np.abs(x), 95))
        return (0.7 * rms) + (0.3 * p95)

    def _synthesize_speech_wav(self, text: str, out_path: Path) -> None:
        msg = text.replace("'", "''")
        wav = str(out_path).replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Rate=0; $s.Volume=100; "
            f"$s.SetOutputToWaveFile('{wav}'); "
            f"$s.Speak('{msg}'); "
            "$s.Dispose()"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0 or not out_path.exists():
            detail = (proc.stderr or proc.stdout or "speech synthesis failed").strip()
            raise RuntimeError(detail)

    @staticmethod
    def _play_wav_on_device_compatible(path: Path, device_index: int) -> None:
        # Known Windows quirk: some WASAPI devices fail when opened from a worker thread.
        # Run playback in a dedicated child process first, then fallback in-process.
        script = APP_DIR / "scripts" / "play_wav_worker.py"
        if script.exists():
            proc = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--wav",
                    str(path),
                    "--output-device",
                    str(int(device_index)),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                return
            detail = (proc.stderr or proc.stdout or "").strip()
            if detail:
                raise RuntimeError(detail)
            raise RuntimeError(f"Playback worker failed with code {proc.returncode}")
        play_wav_blocking_compatible(path, device_index=device_index)

    def tx_channel_announce_sweep(self) -> None:
        if platform.system().lower() != "windows":
            messagebox.showerror("TX Sweep", "TX channel announce is currently implemented for Windows only")
            return
        if not self.client.connected:
            messagebox.showerror("TX Sweep", "Connect to SA818 first")
            return
        if self._audio_worker and self._audio_worker.is_alive():
            messagebox.showwarning("TX Sweep", "Audio worker is busy; stop current playback/capture first")
            return
        # Read tkinter state on UI thread before entering worker thread.
        pre_s, post_s = self._ptt_timings_sec()
        ptt_line = self.ptt_line_var.get().strip().upper()
        ptt_active_high = bool(self.ptt_active_high_var.get())

        def worker() -> None:
            try:
                outputs = list_output_devices()
                usb_outputs = [(idx, name) for idx, name in outputs if "usb audio device" in name.lower()]
                if usb_outputs:
                    outputs = usb_outputs
                if not outputs:
                    raise RuntimeError("No audio output devices found")

                self._queue_log(
                    "TX announce sweep started. Listen on handheld for spoken 'channel N' and note matching N."
                )
                for out_idx, out_name in outputs:
                    wav_path = AUDIO_DIR / f"announce_ch_{out_idx}.wav"
                    wav_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        self._synthesize_speech_wav(
                            f"This is channel {out_idx}. This is channel {out_idx}.",
                            wav_path,
                        )
                        with self._audio_lock:
                            self.client.set_ptt(True, line=ptt_line, active_high=ptt_active_high)
                            try:
                                if pre_s > 0:
                                    sleep(pre_s)
                                self._tx_level_hold = self._estimate_wav_level(wav_path)
                                self._tx_active = True
                                self._play_wav_on_device_compatible(wav_path, out_idx)
                                if post_s > 0:
                                    sleep(post_s)
                            finally:
                                self._tx_active = False
                                self.client.set_ptt(False, line=ptt_line, active_high=ptt_active_high)
                        self._queue_log(f"Announced TX channel {out_idx}: {out_name}")
                    except Exception as exc:  # noqa: BLE001
                        self._queue_log(f"TX announce skipped channel {out_idx}: {exc}")
                    sleep(1.2)
                self._queue_log("TX announce sweep complete. Select heard channel in Audio Output.")
            except Exception as exc:  # noqa: BLE001
                self._queue_error("TX Sweep Error", str(exc))

        self._audio_worker = threading.Thread(target=worker, daemon=True)
        self._audio_worker.start()

    def auto_detect_input_by_voice(self) -> None:
        if platform.system().lower() != "windows":
            messagebox.showerror("RX Detect", "RX input detection is currently implemented for Windows only")
            return
        if self._audio_worker and self._audio_worker.is_alive():
            messagebox.showwarning("RX Detect", "Audio worker is busy; stop current playback/capture first")
            return

        def worker() -> None:
            try:
                inputs = list_input_devices()
                usb_inputs = [(idx, name) for idx, name in inputs if "usb audio device" in name.lower()]
                if usb_inputs:
                    inputs = usb_inputs
                if not inputs:
                    raise RuntimeError("No audio input devices found")

                capture_s = 2.2
                total_s = capture_s * len(inputs)
                self._queue_log(
                    f"RX voice detect started. Hold handheld PTT and repeat '1 2 3 4' continuously for ~{total_s:.0f}s."
                )
                scored: list[tuple[float, int, str]] = []
                failed_inputs: list[tuple[int, str, str]] = []
                for in_idx, in_name in inputs:
                    try:
                        script = APP_DIR / "scripts" / "rx_score_worker.py"
                        if not script.exists():
                            raise RuntimeError(f"Missing script: {script}")
                        proc = subprocess.run(
                            [
                                sys.executable,
                                str(script),
                                "--seconds",
                                f"{capture_s:.3f}",
                                "--input-device",
                                str(int(in_idx)),
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        if proc.returncode != 0:
                            detail = (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()
                            raise RuntimeError(detail)
                        score = float((proc.stdout or "0").strip().splitlines()[-1])
                        scored.append((score, in_idx, in_name))
                        self._queue_log(f"RX score input {in_idx}: {score:.4f} ({in_name})")
                    except Exception as exc:  # noqa: BLE001
                        failed_inputs.append((in_idx, in_name, str(exc)))
                        self._queue_log(f"RX input {in_idx} skipped: {exc}")

                if not scored:
                    if failed_inputs:
                        raise RuntimeError(
                            "No usable RX inputs. Audio backend could not open candidate devices. "
                            "Try switching USB audio endpoint/API and retry."
                        )
                    raise RuntimeError("No candidate RX inputs produced audio data.")

                scored.sort(key=lambda x: x[0], reverse=True)
                best_score, best_idx, best_name = scored[0]
                second_score = scored[1][0] if len(scored) > 1 else 0.0
                if best_score < 0.004:
                    self._queue_log(
                        "RX detect warning: weak signal seen on all inputs. Selecting strongest candidate anyway."
                    )
                if second_score > 0 and (best_score / max(second_score, 1e-9)) < 1.25:
                    self._queue_log(
                        "RX detect warning: top two inputs are close in score. Selecting strongest candidate."
                    )
                self._ui_queue.put(("set_input_device", str(best_idx), None))
                self._queue_log(f"RX input auto-selected: {best_idx} ({best_name})")
            except Exception as exc:  # noqa: BLE001
                self._queue_error("RX Detect Error", str(exc))

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
            self._add_aprs_map_point(lat, lon, f"TX {self.aprs_source_var.get().strip().upper()}")
        except Exception as exc:  # noqa: BLE001
            self._aprs_log(f"Send APRS position failed: {exc}")
            messagebox.showerror("APRS TX Error", str(exc))

    def apply_callsign_preset(self, source: str, peer: str) -> None:
        self.aprs_source_var.set(source.strip().upper())
        if self.aprs_msg_to_var.get().strip().upper() in {"", "N0CALL", "N0CALL-9", "VA7AYG-00", "VA7AYG-01"}:
            self.aprs_msg_to_var.set(peer.strip().upper())
        self.log(f"Callsign preset applied: source={self.aprs_source_var.get()} peer={self.aprs_msg_to_var.get()}")

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
                    self._record_wav_compatible(wav_path, seconds=secs, device_index=dev)
                with wave.open(str(wav_path), "rb") as wavf:
                    rate = int(wavf.getframerate())
                    channels = int(wavf.getnchannels())
                    frames = wavf.readframes(wavf.getnframes())
                mono = np.frombuffer(frames, dtype=np.int16)
                if channels > 1:
                    mono = mono.reshape(-1, channels)[:, 0]
                mono_f = mono.astype(np.float32) / 32768.0
                self._queue_rx_clip(self._clip_percent(mono_f))
                packets = decode_ax25_from_samples(rate, self._rx_trimmed_samples(mono_f))
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
        self._prepare_radio_for_rx_monitor()
        self._rx_monitor_running = True
        self._rx_overlap_samples = None
        self._rx_monitor_thread = threading.Thread(target=self._rx_monitor_loop, daemon=True)
        self._rx_monitor_thread.start()
        self._aprs_log("RX monitor started")

    def stop_rx_monitor(self) -> None:
        self._rx_monitor_running = False
        self._rx_overlap_samples = None
        self._restore_radio_after_rx_monitor()
        self._aprs_log("RX monitor stop requested")

    def _on_auto_rx_toggle(self) -> None:
        if self.aprs_rx_auto_var.get():
            self.start_rx_monitor()
        else:
            self.stop_rx_monitor()

    def _prepare_radio_for_rx_monitor(self) -> None:
        if not self.client.connected:
            return
        try:
            if self._rx_saved_squelch is None:
                self._rx_saved_squelch = self.squelch_var.get().strip()
            freq = float(self.frequency_var.get().strip())
            bw = 1 if self.bandwidth_var.get() == "Wide" else 0
            self.client.set_radio(
                RadioConfig(
                    frequency=freq,
                    offset=0.0,
                    bandwidth=bw,
                    squelch=0,
                    ctcss_tx=None,
                    ctcss_rx=None,
                    dcs_tx=None,
                    dcs_rx=None,
                )
            )
            try:
                self.client.set_filters(True, True, True)
            except Exception:
                pass
            self._aprs_log("RX monitor prep: SA818 squelch forced to 0 with flat filters")
        except Exception as exc:  # noqa: BLE001
            self._aprs_log(f"RX monitor prep warning: {exc}")

    def _restore_radio_after_rx_monitor(self) -> None:
        if not self.client.connected:
            self._rx_saved_squelch = None
            return
        try:
            if self._rx_saved_squelch is None:
                return
            sq = int(self._rx_saved_squelch)
            freq = float(self.frequency_var.get().strip())
            bw = 1 if self.bandwidth_var.get() == "Wide" else 0
            self.client.set_radio(
                RadioConfig(
                    frequency=freq,
                    offset=0.0,
                    bandwidth=bw,
                    squelch=max(0, min(8, sq)),
                    ctcss_tx=None,
                    ctcss_rx=None,
                    dcs_tx=None,
                    dcs_rx=None,
                )
            )
            self._aprs_log(f"RX monitor stop: restored squelch to {max(0, min(8, sq))}")
        except Exception as exc:  # noqa: BLE001
            self._aprs_log(f"RX monitor restore warning: {exc}")
        finally:
            self._rx_saved_squelch = None

    def _rx_monitor_loop(self) -> None:
        while self._rx_monitor_running:
            try:
                chunk = float(self.aprs_rx_chunk_var.get().strip())
                if chunk <= 0:
                    chunk = 2.0
                if platform.system().lower() == "windows" and chunk < 8.0:
                    # Worker-based capture has non-trivial process startup overhead on Windows.
                    # Use a larger chunk to reduce dead-time between captures and improve RX hit rate.
                    chunk = 8.0
                    if not self._rx_chunk_floor_logged:
                        self._rx_chunk_floor_logged = True
                        self._aprs_log("RX monitor: Windows minimum chunk forced to 8.0s for reliability")
                dev = self._selected_input_device()
                if not self._audio_lock.acquire(timeout=0.15):
                    sleep(0.05)
                    continue
                try:
                    rate, mono = self._capture_samples_compatible(seconds=chunk, device_index=dev)
                finally:
                    self._audio_lock.release()
                self._queue_rx_clip(self._clip_percent(mono))
                mono = self._rx_trimmed_samples(mono)
                # Keep spectrum/meter live from the same captured block used for decode.
                in_level = min(1.0, self._level_from_samples(mono) * 8.0)
                self._queue_input_level(in_level)
                self._queue_waterfall_row(self._spectrum_row_from_samples(rate, mono))
                overlap = self._rx_overlap_samples
                if overlap is not None and len(overlap) > 0:
                    decode_samples = np.concatenate((overlap, mono))
                else:
                    decode_samples = mono
                keep = max(1, int(rate * 1.2))
                self._rx_overlap_samples = decode_samples[-keep:].copy()

                packets = decode_ax25_from_samples(rate, decode_samples)
                dedupe_window_s = max(2.0, chunk + 1.0)
                for pkt in packets:
                    now_ts = datetime.now().timestamp()
                    last_seen = self._recent_rx_times.get(pkt.text)
                    # Suppress duplicate decodes from overlap/repeated digipeat echoes in short window.
                    if last_seen is not None and (now_ts - last_seen) < dedupe_window_s:
                        continue
                    self._recent_rx_times[pkt.text] = now_ts
                    # Keep memory bounded during long monitor runs.
                    if len(self._recent_rx_times) > 600:
                        cutoff = now_ts - max(30.0, dedupe_window_s * 2.0)
                        self._recent_rx_times = {
                            text: ts for text, ts in self._recent_rx_times.items() if ts >= cutoff
                        }
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
            "aprs_rx_trim_db": float(self.aprs_rx_trim_db_var.get()),
            "aprs_rx_os_level": int(self.aprs_rx_os_level_var.get()),
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
            "chat_contacts": self._chat_contacts,
            "chat_groups": self._chat_groups,
            "chat_intro_note": self.chat_intro_note_var.get(),
        }
        PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.log(f"Profile saved: {PROFILE_PATH}")

    def load_profile(self, silent: bool = False) -> None:
        if not PROFILE_PATH.exists():
            if not silent:
                messagebox.showinfo("Info", "No saved profile found")
            return
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8-sig"))
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
        self.volume_var.set(int(data.get("volume", 8)))
        self.test_tone_freq_var.set(data.get("test_tone_freq", "1200"))
        self.test_tone_duration_var.set(data.get("test_tone_duration", "2.0"))
        self.aprs_source_var.set(data.get("aprs_source", "VA7AYG-00"))
        self.aprs_dest_var.set(data.get("aprs_dest", "APRS"))
        self.aprs_path_var.set(data.get("aprs_path", "WIDE1-1"))
        self.aprs_message_var.set(data.get("aprs_message", "uConsole HAM HAT test"))
        self.aprs_msg_to_var.set(data.get("aprs_msg_to", "VA7AYG-01"))
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
        self.aprs_rx_chunk_var.set(data.get("aprs_rx_chunk", "8.0"))
        try:
            self.aprs_rx_trim_db_var.set(float(data.get("aprs_rx_trim_db", -12.0)))
        except Exception:
            self.aprs_rx_trim_db_var.set(-12.0)
        try:
            self.aprs_rx_os_level_var.set(int(data.get("aprs_rx_os_level", 35)))
        except Exception:
            self.aprs_rx_os_level_var.set(35)
        self.aprs_rx_auto_var.set(bool(data.get("aprs_rx_auto", False)))
        self.aprs_tx_gain_var.set(data.get("aprs_tx_gain", "0.34"))
        self.aprs_preamble_flags_var.set(data.get("aprs_preamble_flags", "240"))
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
        self._chat_contacts = [self._norm_call(x) for x in data.get("chat_contacts", []) if self._norm_call(x)]
        raw_groups = data.get("chat_groups", {})
        if isinstance(raw_groups, dict):
            self._chat_groups = {
                self._norm_call(k): [self._norm_call(x) for x in v if self._norm_call(x)]
                for k, v in raw_groups.items()
                if self._norm_call(k)
            }
        self.chat_intro_note_var.set(data.get("chat_intro_note", "uConsole HAM HAT online"))
        self._refresh_contacts_ui()
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
        self._stop_audio_visualizer()
        self._tx_active = False
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

