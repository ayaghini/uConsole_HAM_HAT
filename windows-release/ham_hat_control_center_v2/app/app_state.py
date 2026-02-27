#!/usr/bin/env python3
"""AppState — shared application state (tk.Var containers + engine instances)."""

from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path

from .engine.aprs_engine import AprsEngine
from .engine.audio_router import AudioRouter
from .engine.comms_mgr import CommsManager
from .engine.profile import ProfileManager
from .engine.radio_ctrl import RadioController


class AppState:
    """A container for shared application state."""

    def __init__(self, app_dir: Path) -> None:
        self.app_dir = app_dir
        self.audio_dir = app_dir / "audio_out"
        self.profile_path = app_dir / "profiles" / "last_profile.json"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        # --- Engine components ---
        self.radio = RadioController()
        self.audio = AudioRouter(app_dir)
        self.aprs = AprsEngine(self.radio, self.audio, self.audio_dir)
        self.comms = CommsManager()
        self.prof = ProfileManager(self.profile_path)

        # --- Thread-safe event queue ---
        self.evq: queue.Queue = queue.Queue()

        # --- Tk vars ---
        self.port_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.frequency_var = tk.StringVar(value="145.070")
        self.offset_var = tk.StringVar(value="0.600")
        self.squelch_var = tk.StringVar(value="4")
        self.bandwidth_var = tk.StringVar(value="Wide")
        self.audio_out_var = tk.StringVar()
        self.audio_in_var = tk.StringVar()
        self.auto_audio_var = tk.BooleanVar(value=True)
        self.ptt_enabled_var = tk.BooleanVar(value=True)
        self.ptt_line_var = tk.StringVar(value="RTS")
        self.ptt_active_high_var = tk.BooleanVar(value=True)
        self.ptt_pre_ms_var = tk.StringVar(value="400")
        self.ptt_post_ms_var = tk.StringVar(value="120")
        self.aprs_source_var = tk.StringVar(value="N0CALL-0")
        self.aprs_dest_var = tk.StringVar(value="APRS")
        self.aprs_path_var = tk.StringVar(value="WIDE1-1")
        self.aprs_tx_gain_var = tk.StringVar(value="0.34")
        self.aprs_preamble_var = tk.StringVar(value="60")
        self.aprs_repeats_var = tk.StringVar(value="1")
        self.aprs_reinit_var = tk.BooleanVar(value=True)
        self.aprs_symbol_table_var = tk.StringVar(value="/")
        self.aprs_symbol_var = tk.StringVar(value=">")
        self.aprs_msg_to_var = tk.StringVar(value="N0CALL-1")
        self.aprs_msg_text_var = tk.StringVar()
        self.aprs_msg_id_var = tk.StringVar()
        self.aprs_reliable_var = tk.BooleanVar(value=False)
        self.aprs_ack_timeout_var = tk.StringVar(value="8.0")
        self.aprs_ack_retries_var = tk.StringVar(value="4")
        self.aprs_auto_ack_var = tk.BooleanVar(value=True)
        self.aprs_lat_var = tk.StringVar(value="49.2827")
        self.aprs_lon_var = tk.StringVar(value="-123.1207")
        self.aprs_comment_var = tk.StringVar(value="uConsole HAM HAT")
        self.aprs_rx_dur_var = tk.StringVar(value="10.0")
        self.aprs_rx_chunk_var = tk.StringVar(value="8.0")
        self.aprs_rx_trim_var = tk.DoubleVar(value=-12.0)
        self.rx_clip_var = tk.StringVar(value="—")
        self.aprs_rx_level_var = tk.StringVar(value="—")   # input level (separate from clip)
        self.aprs_rx_os_level_var = tk.IntVar(value=35)
        self.aprs_rx_auto_var = tk.BooleanVar(value=False)
