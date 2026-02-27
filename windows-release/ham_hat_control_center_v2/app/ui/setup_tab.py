#!/usr/bin/env python3
"""SetupTab — Advanced Radio, Audio Tools, Profile, Bootstrap.

Sections:
  Left  : Advanced radio settings (filters, volume, CTCSS/DCS detail)
          PTT configuration
          APRS TX advanced options
  Right : Audio tools (test tone, manual APRS packet)
          Profile management
          Bootstrap / diagnostics
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from ..engine.sa818_client import CTCSS
from .widgets import add_row, scrollable_frame

if TYPE_CHECKING:
    from ..app import HamHatApp


class SetupTab(ttk.Frame):
    """Advanced setup and tools tab."""

    def __init__(self, parent: ttk.Notebook, app: "HamHatApp") -> None:
        super().__init__(parent)
        self._app = app
        self._build()

    # ------------------------------------------------------------------
    # Build layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.grid(row=0, column=0, columnspan=2, sticky="nsew")

        left_host = ttk.Frame(pane)
        right_host = ttk.Frame(pane)
        pane.add(left_host, weight=1)
        pane.add(right_host, weight=1)

        self._build_left(left_host)
        self._build_right(right_host)

    def _build_left(self, parent: ttk.Frame) -> None:
        _canvas, _vsb, inner = scrollable_frame(parent)
        inner.columnconfigure(1, weight=1)

        row = 0

        # ---- Advanced Radio: Filters ----
        ff = ttk.LabelFrame(inner, text="Audio Filters (SA818)", padding=8)
        ff.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ff.columnconfigure(0, weight=1)
        row += 1

        self._filter_emphasis_var = tk.BooleanVar(value=True)
        self._filter_highpass_var = tk.BooleanVar(value=True)
        self._filter_lowpass_var  = tk.BooleanVar(value=True)

        ttk.Checkbutton(ff, text="Disable Pre/De-emphasis",
                        variable=self._filter_emphasis_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(ff, text="Disable High-pass Filter",
                        variable=self._filter_highpass_var).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(ff, text="Disable Low-pass Filter",
                        variable=self._filter_lowpass_var).grid(row=2, column=0, sticky="w")
        ttk.Button(ff, text="Apply Filters", command=self._apply_filters).grid(
            row=3, column=0, sticky="w", pady=(6, 0))

        # ---- Volume ----
        vf = ttk.LabelFrame(inner, text="Volume", padding=8)
        vf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        vf.columnconfigure(1, weight=1)
        row += 1

        self._volume_var = tk.IntVar(value=8)
        vol_scale = ttk.Scale(vf, from_=1, to=8, orient="horizontal",
                              variable=self._volume_var, length=160)
        vol_scale.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(vf, text="1 (min)").grid(row=1, column=0, sticky="w")
        ttk.Label(vf, text="8 (max)").grid(row=1, column=1, sticky="e")
        ttk.Button(vf, text="Set Volume", command=self._set_volume).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # ---- CTCSS / DCS ----
        tf = ttk.LabelFrame(inner, text="CTCSS / DCS Tones", padding=8)
        tf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        tf.columnconfigure(1, weight=1)
        row += 1

        ctcss_opts = list(CTCSS)

        self._ctcss_tx_var = tk.StringVar(value="None")
        self._ctcss_rx_var = tk.StringVar(value="None")
        self._dcs_tx_var   = tk.StringVar(value="None")
        self._dcs_rx_var   = tk.StringVar(value="None")

        add_row(tf, "CTCSS TX:",
                ttk.Combobox(tf, textvariable=self._ctcss_tx_var,
                             values=ctcss_opts, state="readonly", width=10), row=0)
        add_row(tf, "CTCSS RX:",
                ttk.Combobox(tf, textvariable=self._ctcss_rx_var,
                             values=ctcss_opts, state="readonly", width=10), row=1)
        ttk.Separator(tf, orient="horizontal").grid(row=2, column=0, columnspan=2,
                                                     sticky="ew", pady=4)
        add_row(tf, "DCS TX:",
                ttk.Entry(tf, textvariable=self._dcs_tx_var, width=10), row=3)
        ttk.Label(tf, text="(e.g. 047N or 047I)", foreground="#9cc4dd",
                  font=("TkDefaultFont", 8)).grid(row=3, column=2, sticky="w", padx=(4, 0))
        add_row(tf, "DCS RX:",
                ttk.Entry(tf, textvariable=self._dcs_rx_var, width=10), row=4)
        ttk.Label(tf, text="(None to disable)", foreground="#9cc4dd",
                  font=("TkDefaultFont", 8)).grid(row=5, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # ---- Squelch tail ----
        sf = ttk.LabelFrame(inner, text="Squelch Tail", padding=8)
        sf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        row += 1
        self._open_tail_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sf, text="Open squelch tail (AT+SETTAIL=1)",
                        variable=self._open_tail_var).pack(anchor="w")
        ttk.Button(sf, text="Apply Tail", command=self._apply_tail).pack(anchor="w", pady=(4, 0))

        # ---- PTT ----
        # Bind directly to shared vars defined in app.py (same as main_tab.py)
        # This avoids a collect_profile conflict where two tabs write the same AppProfile fields.
        pf = ttk.LabelFrame(inner, text="PTT Configuration", padding=8)
        pf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        pf.columnconfigure(1, weight=1)
        row += 1

        ttk.Checkbutton(pf, text="PTT Enabled",
                        variable=self._app.ptt_enabled_var).grid(
            row=0, column=0, columnspan=2, sticky="w")
        add_row(pf, "Line:", ttk.Combobox(pf, textvariable=self._app.ptt_line_var,
                values=["RTS", "DTR"], state="readonly", width=8), row=1)
        ttk.Checkbutton(pf, text="Active High (normal polarity)",
                        variable=self._app.ptt_active_high_var).grid(
            row=2, column=0, columnspan=2, sticky="w")
        add_row(pf, "Pre-delay (ms):",
                ttk.Spinbox(pf, textvariable=self._app.ptt_pre_ms_var,
                            from_=0, to=2000, width=8), row=3)
        add_row(pf, "Post-delay (ms):",
                ttk.Spinbox(pf, textvariable=self._app.ptt_post_ms_var,
                            from_=0, to=2000, width=8), row=4)

        # ---- APRS TX advanced ----
        # Bind to shared vars (same as aprs_tab.py) to avoid collect_profile conflicts.
        af = ttk.LabelFrame(inner, text="APRS TX Advanced", padding=8)
        af.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        af.columnconfigure(1, weight=1)
        row += 1

        ttk.Checkbutton(af, text="Re-program radio before each TX",
                        variable=self._app.aprs_reinit_var).grid(
            row=0, column=0, columnspan=2, sticky="w")
        add_row(af, "Preamble flags:",
                ttk.Spinbox(af, textvariable=self._app.aprs_preamble_var,
                            from_=10, to=500, width=8), row=1)
        add_row(af, "TX repeats:",
                ttk.Spinbox(af, textvariable=self._app.aprs_repeats_var,
                            from_=1, to=5, width=8), row=2)
        add_row(af, "TX gain (0.01-1.0):",
                ttk.Spinbox(af, textvariable=self._app.aprs_tx_gain_var,
                            from_=0.01, to=1.0, increment=0.01, format="%.2f", width=8), row=3)

        # ---- RX Monitor advanced ----
        # Bind to shared vars (same as aprs_tab.py) to avoid collect_profile conflicts.
        rf = ttk.LabelFrame(inner, text="APRS RX Advanced", padding=8)
        rf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        rf.columnconfigure(1, weight=1)
        row += 1

        add_row(rf, "Monitor duration (s):",
                ttk.Spinbox(rf, textvariable=self._app.aprs_rx_dur_var,
                            from_=2.0, to=120.0, increment=1.0, width=8), row=0)
        add_row(rf, "Chunk size (s):",
                ttk.Spinbox(rf, textvariable=self._app.aprs_rx_chunk_var,
                            from_=1.0, to=30.0, increment=0.5, width=8), row=1)
        add_row(rf, "Trim threshold (dB):",
                ttk.Spinbox(rf, textvariable=self._app.aprs_rx_trim_var,
                            from_=-40.0, to=0.0, increment=1.0, width=8), row=2)
        add_row(rf, "OS mic level (0-100):",
                ttk.Spinbox(rf, textvariable=self._app.aprs_rx_os_level_var,
                            from_=0, to=100, width=8), row=3)

    def _build_right(self, parent: ttk.Frame) -> None:
        _canvas, _vsb, inner = scrollable_frame(parent)
        inner.columnconfigure(1, weight=1)

        row = 0

        # ---- Test tone ----
        tf = ttk.LabelFrame(inner, text="Audio Tools — Test Tone", padding=8)
        tf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        tf.columnconfigure(1, weight=1)
        row += 1

        self._tone_freq_var     = tk.DoubleVar(value=1200.0)
        self._tone_duration_var = tk.DoubleVar(value=2.0)

        add_row(tf, "Frequency (Hz):",
                ttk.Spinbox(tf, textvariable=self._tone_freq_var,
                            from_=100.0, to=3000.0, increment=100.0, format="%.0f", width=10), row=0)
        add_row(tf, "Duration (s):",
                ttk.Spinbox(tf, textvariable=self._tone_duration_var,
                            from_=0.5, to=30.0, increment=0.5, format="%.1f", width=10), row=1)

        btn_row = ttk.Frame(tf)
        btn_row.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(btn_row, text="▶ Play Test Tone",
                   command=self._play_test_tone).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="■ Stop Audio",
                   command=self._stop_audio).pack(side="left")

        # ---- Manual APRS packet ----
        mf = ttk.LabelFrame(inner, text="Audio Tools — Manual APRS Packet", padding=8)
        mf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        mf.columnconfigure(1, weight=1)
        row += 1

        self._manual_aprs_var = tk.StringVar(value="uConsole HAM HAT test")
        add_row(mf, "Packet text:", ttk.Entry(mf, textvariable=self._manual_aprs_var), row=0)

        ttk.Button(mf, text="▶ Encode & Play (no PTT)",
                   command=self._play_manual_aprs).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # ---- Tone sweep / channel detection ----
        sf = ttk.LabelFrame(inner, text="TX Tone Sweep (channel detection)", padding=8)
        sf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        sf.columnconfigure(1, weight=1)
        row += 1

        ttk.Label(sf, text="Sweeps 1200–2200 Hz to detect RX channel.\nListens for echo on input device.",
                  foreground="#9cc4dd", font=("TkDefaultFont", 8)).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Button(sf, text="Run TX Channel Sweep",
                   command=self._tx_channel_sweep).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ---- Auto RX detect ----
        arf = ttk.LabelFrame(inner, text="Auto-detect RX Level", padding=8)
        arf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        row += 1

        ttk.Label(arf, text="Captures audio and suggests OS microphone level\nfor best APRS decode SNR.",
                  foreground="#9cc4dd", font=("TkDefaultFont", 8)).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Button(arf, text="Auto-detect RX Level",
                   command=self._auto_detect_rx).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ---- Profile management ----
        pf = ttk.LabelFrame(inner, text="Profile Management", padding=8)
        pf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        row += 1

        p_row = ttk.Frame(pf)
        p_row.pack(fill="x")
        ttk.Button(p_row, text="Save Profile…",    command=self._save_profile).pack(side="left", padx=(0, 4))
        ttk.Button(p_row, text="Load Profile…",    command=self._load_profile).pack(side="left", padx=4)
        ttk.Button(p_row, text="Reset Defaults",   command=self._reset_defaults).pack(side="left", padx=4)

        # ---- Bootstrap ----
        bf = ttk.LabelFrame(inner, text="Bootstrap / Diagnostics", padding=8)
        bf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        row += 1

        ttk.Button(bf, text="Install / Update Dependencies",
                   command=self._bootstrap).grid(row=0, column=0, sticky="w")
        ttk.Button(bf, text="Run Two-Radio Diagnostic",
                   command=self._two_radio_diagnostic).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ---- TTS / Speech (optional) ----
        tsf = ttk.LabelFrame(inner, text="Text-to-Speech (optional, Windows only)", padding=8)
        tsf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        row += 1

        self._tts_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tsf, text="Announce received APRS messages via TTS",
                        variable=self._tts_enabled_var).pack(anchor="w")
        ttk.Label(tsf,
                  text="Uses Windows PowerShell SpeechSynthesizer.\nRequires no additional dependencies.",
                  foreground="#9cc4dd", font=("TkDefaultFont", 8)).pack(anchor="w", pady=(4, 0))

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _apply_filters(self) -> None:
        self._app.apply_filters(
            self._filter_emphasis_var.get(),
            self._filter_highpass_var.get(),
            self._filter_lowpass_var.get(),
        )

    def _set_volume(self) -> None:
        self._app.set_volume(int(self._volume_var.get()))

    def _apply_tail(self) -> None:
        self._app.apply_tail(self._open_tail_var.get())

    def _play_test_tone(self) -> None:
        self._app.play_test_tone(
            freq=float(self._tone_freq_var.get()),
            duration=float(self._tone_duration_var.get()),
        )

    def _stop_audio(self) -> None:
        self._app.stop_audio()

    def _play_manual_aprs(self) -> None:
        self._app.play_manual_aprs_packet(self._manual_aprs_var.get())

    def _tx_channel_sweep(self) -> None:
        self._app.tx_channel_sweep()

    def _auto_detect_rx(self) -> None:
        self._app.auto_detect_rx()

    def _save_profile(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Profile",
            defaultextension=".json",
            filetypes=[("JSON Profile", "*.json"), ("All Files", "*.*")],
        )
        if path:
            self._app.save_profile(path)

    def _load_profile(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Load Profile",
            filetypes=[("JSON Profile", "*.json"), ("All Files", "*.*")],
        )
        if path:
            self._app.load_profile(path)

    def _reset_defaults(self) -> None:
        if messagebox.askyesno("Reset Defaults", "Reset all settings to factory defaults?",
                               parent=self):
            self._app.reset_defaults()

    def _bootstrap(self) -> None:
        self._app.run_bootstrap()

    def _two_radio_diagnostic(self) -> None:
        self._app.run_two_radio_diagnostic()

    # ------------------------------------------------------------------
    # Profile integration
    # ------------------------------------------------------------------

    def apply_profile(self, p) -> None:
        """Load profile values into setup tab widgets.

        Note: PTT, APRS TX advanced, and APRS RX advanced fields are NOT loaded
        here — they use shared vars (self._app.*_var) populated by main_tab and
        aprs_tab respectively, so they're already correct before this runs.
        """
        self._filter_emphasis_var.set(getattr(p, "disable_emphasis", True))
        self._filter_highpass_var.set(getattr(p, "disable_highpass", True))
        self._filter_lowpass_var.set(getattr(p, "disable_lowpass", True))
        self._volume_var.set(int(getattr(p, "volume", 8)))

        self._ctcss_tx_var.set(getattr(p, "ctcss_tx", "") or "None")
        self._ctcss_rx_var.set(getattr(p, "ctcss_rx", "") or "None")
        self._dcs_tx_var.set(getattr(p, "dcs_tx", "") or "None")
        self._dcs_rx_var.set(getattr(p, "dcs_rx", "") or "None")

        self._open_tail_var.set(False)  # not persisted separately

        self._tone_freq_var.set(float(getattr(p, "test_tone_freq", 1200.0)))
        self._tone_duration_var.set(float(getattr(p, "test_tone_duration", 2.0)))
        self._manual_aprs_var.set(getattr(p, "manual_aprs_text", "uConsole HAM HAT test"))

    def collect_profile(self, p) -> None:
        """Write setup tab widget values back into profile object.

        PTT, APRS TX advanced, and APRS RX advanced fields are NOT written here —
        they are owned by main_tab and aprs_tab (shared vars) and already saved by
        those tabs' collect_profile calls earlier in the collection chain.
        """
        p.disable_emphasis = self._filter_emphasis_var.get()
        p.disable_highpass = self._filter_highpass_var.get()
        p.disable_lowpass  = self._filter_lowpass_var.get()
        p.volume           = int(self._volume_var.get())

        ctcss_tx = self._ctcss_tx_var.get()
        ctcss_rx = self._ctcss_rx_var.get()
        p.ctcss_tx = "" if ctcss_tx == "None" else ctcss_tx
        p.ctcss_rx = "" if ctcss_rx == "None" else ctcss_rx
        p.dcs_tx   = "" if self._dcs_tx_var.get() in ("None", "") else self._dcs_tx_var.get()
        p.dcs_rx   = "" if self._dcs_rx_var.get() in ("None", "") else self._dcs_rx_var.get()

        p.test_tone_freq     = float(self._tone_freq_var.get())
        p.test_tone_duration = float(self._tone_duration_var.get())
        p.manual_aprs_text   = self._manual_aprs_var.get()

    @property
    def tts_enabled(self) -> bool:
        return self._tts_enabled_var.get()
