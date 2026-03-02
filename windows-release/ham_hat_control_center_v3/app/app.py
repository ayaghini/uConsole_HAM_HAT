#!/usr/bin/env python3
"""HamHatApp — main application window.

Architecture:
  - One tk.Tk root window with 4 tab pages.
  - Engine components run in daemon worker threads; they NEVER touch Tkinter.
  - Worker threads push events into a thread.Queue; the main thread drains
    it every 40 ms via after() and dispatches to tab widgets.
  - All action methods are called by tab widgets on the main thread; they
    capture the needed state as plain Python values, then hand off to engine.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import messagebox, ttk
import sv_ttk

from .app_state import AppState
from .engine.aprs_engine import AprsEngine, _TxSnapshot
from .engine.aprs_modem import (
    build_aprs_message_payload,
    build_aprs_position_payload,
    write_aprs_wav,
    write_test_tone_wav,
)
from .engine.audio_router import AudioRouter
from .engine.audio_tools import list_input_devices, list_output_devices
from .engine.comms_mgr import CommsManager
from .engine.models import (
    AppProfile,
    AprsConfig,
    AudioConfig,
    ChatMessage,
    DecodedPacket,
    MSG_ID_COUNTER,
    PttConfig,
    RadioConfig,
    ReliableConfig,
)
from .engine.profile import ProfileManager
from .engine.radio_ctrl import RadioController
from .engine.sa818_client import SA818Error
from .ui.aprs_tab import AprsTab
from .ui.comms_tab import CommsTab
from .ui.main_tab import MainTab
from .ui.setup_tab import SetupTab

_log = logging.getLogger(__name__)

_VERSION_FILE = Path(__file__).parent.parent / "VERSION"


def _read_version() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return "dev"


# ---------------------------------------------------------------------------
# Thread-safe event types (pushed from worker threads, consumed on main thread)
# ---------------------------------------------------------------------------

@dataclass
class _LogEvt:         msg: str
@dataclass
class _AprsLogEvt:     msg: str
@dataclass
class _ErrorEvt:       title: str; msg: str
@dataclass
class _ConnectEvt:     port: str
@dataclass
class _DisconnectEvt:  pass
@dataclass
class _PacketEvt:      pkt: "DecodedPacket"
@dataclass
class _AudioPairEvt:   out_idx: int; out_name: str; in_idx: int; in_name: str
@dataclass
class _InputLevelEvt:  level: float
@dataclass
class _OutputLevelEvt: level: float
@dataclass
class _WaterfallEvt:   mono: object; rate: int
@dataclass
class _RxClipEvt:      pct: float
@dataclass
class _HeardEvt:       call: str
@dataclass
class _ChatMsgEvt:     msg: "ChatMessage"
@dataclass
class _ContactsEvt:    pass
@dataclass
class _StatusEvt:      text: str
@dataclass
class _SuggestRxOsLevelEvt: level: int


class HamHatApp(tk.Tk):
    """Main application window — thin coordinator between engine and tabs."""

    POLL_MS = 40            # UI queue drain interval
    VIS_MS  = 120           # level visualiser update interval
    AUTOSAVE_MS = 30_000    # profile auto-save interval

    def __init__(self, app_dir: Path) -> None:
        super().__init__()
        self.state = AppState(app_dir)
        self._app_dir = app_dir

        self._version = _read_version()
        self.title(f"HAM HAT Control Center  ({self._version})")
        self.minsize(860, 600)

        # Set the theme
        sv_ttk.set_theme("dark")

        # Pass references from state to self for convenience
        self.radio = self.state.radio
        self.audio = self.state.audio
        self.aprs = self.state.aprs
        self.comms = self.state.comms
        self._prof = self.state.prof
        self._evq = self.state.evq
        self.port_var = self.state.port_var
        self.status_var = self.state.status_var
        self.frequency_var = self.state.frequency_var
        self.offset_var = self.state.offset_var
        self.squelch_var = self.state.squelch_var
        self.bandwidth_var = self.state.bandwidth_var
        self.audio_out_var = self.state.audio_out_var
        self.audio_in_var = self.state.audio_in_var
        self.auto_audio_var = self.state.auto_audio_var
        self.ptt_enabled_var = self.state.ptt_enabled_var
        self.ptt_line_var = self.state.ptt_line_var
        self.ptt_active_high_var = self.state.ptt_active_high_var
        self.ptt_pre_ms_var = self.state.ptt_pre_ms_var
        self.ptt_post_ms_var = self.state.ptt_post_ms_var
        self.aprs_source_var = self.state.aprs_source_var
        self.aprs_dest_var = self.state.aprs_dest_var
        self.aprs_path_var = self.state.aprs_path_var
        self.aprs_tx_gain_var = self.state.aprs_tx_gain_var
        self.aprs_preamble_var = self.state.aprs_preamble_var
        self.aprs_repeats_var = self.state.aprs_repeats_var
        self.aprs_reinit_var = self.state.aprs_reinit_var
        self.aprs_symbol_table_var = self.state.aprs_symbol_table_var
        self.aprs_symbol_var = self.state.aprs_symbol_var
        self.aprs_msg_to_var = self.state.aprs_msg_to_var
        self.aprs_msg_text_var = self.state.aprs_msg_text_var
        self.aprs_msg_id_var = self.state.aprs_msg_id_var
        self.aprs_reliable_var = self.state.aprs_reliable_var
        self.aprs_ack_timeout_var = self.state.aprs_ack_timeout_var
        self.aprs_ack_retries_var = self.state.aprs_ack_retries_var
        self.aprs_auto_ack_var = self.state.aprs_auto_ack_var
        self.aprs_lat_var = self.state.aprs_lat_var
        self.aprs_lon_var = self.state.aprs_lon_var
        self.aprs_comment_var = self.state.aprs_comment_var
        self.aprs_rx_dur_var = self.state.aprs_rx_dur_var
        self.aprs_rx_chunk_var = self.state.aprs_rx_chunk_var
        self.aprs_rx_trim_var = self.state.aprs_rx_trim_var
        self.rx_clip_var = self.state.rx_clip_var
        self.aprs_rx_level_var = self.state.aprs_rx_level_var
        self.aprs_rx_os_level_var = self.state.aprs_rx_os_level_var
        self.aprs_rx_auto_var = self.state.aprs_rx_auto_var

        # --- Build UI ---
        self._build_ui()

        # --- Wire engine callbacks → queue ---
        self._wire_callbacks()

        # --- Wire comms manager callbacks ---
        self._wire_comms()

        # --- Load profile (populates tabs) ---
        self._load_and_apply_profile()

        # --- Start periodic jobs ---
        self.after(self.POLL_MS, self._drain_queue)
        self.after(self.VIS_MS,  self._vis_tick)
        self.after(self.AUTOSAVE_MS, self._autosave)

        # --- Window close ---
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- Status bar startup ---
        self._set_status("Ready. Select COM port and click Connect.")

        # --- Auto-find audio and auto-connect ---
        self.after(200, self._startup_auto_tasks)

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        self._notebook = ttk.Notebook(self)
        self._notebook.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        self._main_tab  = MainTab(self._notebook, self)
        self._aprs_tab  = AprsTab(self._notebook, self)
        self._comms_tab = CommsTab(self._notebook, self)
        self._setup_tab = SetupTab(self._notebook, self)

        self._notebook.add(self._main_tab,  text="  Control  ")
        self._notebook.add(self._aprs_tab,  text="  APRS  ")
        self._notebook.add(self._comms_tab, text="  Comms  ")
        self._notebook.add(self._setup_tab, text="  Setup  ")

        # Status bar
        self._status_var = tk.StringVar(value="")
        sb = ttk.Frame(self, relief="sunken")
        sb.grid(row=1, column=0, sticky="ew")
        sb.columnconfigure(0, weight=1)

        self._status_lbl = ttk.Label(sb, textvariable=self._status_var,
                                      anchor="w", padding=(6, 2))
        self._status_lbl.grid(row=0, column=0, sticky="ew")

        self._conn_lbl = ttk.Label(sb, text="⚫ Disconnected",
                                    foreground="#e07070", padding=(6, 2))
        self._conn_lbl.grid(row=0, column=1, sticky="e")

        self._rx_lbl = ttk.Label(sb, text="RX: —", padding=(4, 2))
        self._rx_lbl.grid(row=0, column=2, sticky="e")

        self._tx_lbl = ttk.Label(sb, text="TX: —", padding=(4, 2))
        self._tx_lbl.grid(row=0, column=3, sticky="e", padx=(0, 6))

    # -----------------------------------------------------------------------
    # Callback wiring
    # -----------------------------------------------------------------------

    def _wire_callbacks(self) -> None:
        def _post(evt): self._evq.put_nowait(evt)

        self.radio.set_on_connect(lambda port: _post(_ConnectEvt(port)))
        self.radio.set_on_disconnect(lambda: _post(_DisconnectEvt()))

        self.audio.set_log_cb(lambda msg: _post(_LogEvt(msg)))

        self.aprs.on_log(lambda msg: _post(_LogEvt(msg)))
        self.aprs.on_aprs_log(lambda msg: _post(_AprsLogEvt(msg)))
        self.aprs.on_error(lambda t, m: _post(_ErrorEvt(t, m)))
        self.aprs.on_packet(lambda pkt: _post(_PacketEvt(pkt)))
        self.aprs.on_input_level(lambda lv: _post(_InputLevelEvt(lv)))
        self.aprs.on_output_level(lambda lv: _post(_OutputLevelEvt(lv)))
        self.aprs.on_waterfall(lambda mono, rate: _post(_WaterfallEvt(mono, rate)))
        self.aprs.on_rx_clip(lambda pct: _post(_RxClipEvt(pct)))

    def _wire_comms(self) -> None:
        def _post(evt): self._evq.put_nowait(evt)

        self.comms.on_contacts_changed(lambda: _post(_ContactsEvt()))
        self.comms.on_message_added(lambda msg: _post(_ChatMsgEvt(msg)))
        self.comms.on_heard_changed(lambda: self.after_idle(self._comms_tab.refresh_heard))

    # -----------------------------------------------------------------------
    # Queue drain (runs on main thread every POLL_MS)
    # -----------------------------------------------------------------------

    def _drain_queue(self) -> None:
        limit = 80  # max events to process per tick
        for _ in range(limit):
            try:
                evt = self._evq.get_nowait()
            except queue.Empty:
                break
            self._dispatch(evt)
        self.after(self.POLL_MS, self._drain_queue)

    def _dispatch(self, evt) -> None:
        if isinstance(evt, _LogEvt):
            self._main_tab.append_log(evt.msg)

        elif isinstance(evt, _AprsLogEvt):
            self._aprs_tab.append_log(evt.msg)
            self._main_tab.append_log(f"[APRS] {evt.msg}")

        elif isinstance(evt, _ErrorEvt):
            messagebox.showerror(evt.title, evt.msg, parent=self)

        elif isinstance(evt, _ConnectEvt):
            self._conn_lbl.configure(text=f"🟢 {evt.port}", foreground="#70c070")
            self._main_tab.on_connect(evt.port)
            self._set_status(f"Connected: {evt.port}")
            # Keep port_var in sync so manual reconnect after disconnect uses the right port
            self.port_var.set(evt.port)

        elif isinstance(evt, _DisconnectEvt):
            self._conn_lbl.configure(text="⚫ Disconnected", foreground="#e07070")
            self._main_tab.on_disconnect()
            self._set_status("Disconnected")

        elif isinstance(evt, _PacketEvt):
            self._handle_packet(evt.pkt)

        elif isinstance(evt, _AudioPairEvt):
            self._main_tab.on_audio_pair(evt.out_idx, evt.out_name, evt.in_idx, evt.in_name)
            self._set_status(f"Audio: {evt.out_name} / {evt.in_name}")

        elif isinstance(evt, _InputLevelEvt):
            self._aprs_tab.set_input_level(evt.level)
            pct = int(min(100, max(0, evt.level * 100.0)))
            self._rx_lbl.configure(text=f"RX: {pct:3d}%")

        elif isinstance(evt, _OutputLevelEvt):
            self._aprs_tab.set_output_level(evt.level)

        elif isinstance(evt, _WaterfallEvt):
            self._aprs_tab.push_waterfall(evt.mono, evt.rate)

        elif isinstance(evt, _RxClipEvt):
            self._aprs_tab.set_rx_clip(evt.pct)

        elif isinstance(evt, _HeardEvt):
            self.comms.note_heard(evt.call)

        elif isinstance(evt, _ChatMsgEvt):
            self._comms_tab.on_message(evt.msg)

        elif isinstance(evt, _ContactsEvt):
            self._comms_tab.refresh_contacts()

        elif isinstance(evt, _StatusEvt):
            self._set_status(evt.text)

        elif isinstance(evt, _SuggestRxOsLevelEvt):
            self.aprs_rx_os_level_var.set(evt.level)

    # -----------------------------------------------------------------------
    # Visualiser tick (TX/RX level bars, updated on main thread)
    # -----------------------------------------------------------------------

    def _vis_tick(self) -> None:
        if self.audio.tx_active:
            pct = int(min(100, self.audio.tx_level_hold * 100.0))
            self._tx_lbl.configure(text=f"TX: {pct:3d}%")
        else:
            self._tx_lbl.configure(text="TX: —")
        rx_active = self.aprs.rx_running
        if not rx_active:
            self._rx_lbl.configure(text="RX: —")
            self.aprs_rx_level_var.set("—")
        self._aprs_tab.set_monitor_active(rx_active)
        self.after(self.VIS_MS, self._vis_tick)

    # -----------------------------------------------------------------------
    # Startup tasks (deferred by 200ms so window is visible first)
    # -----------------------------------------------------------------------

    def _startup_auto_tasks(self) -> None:
        # Populate serial port list (FR-02: app shall list available serial ports)
        self.refresh_ports()
        # Refresh audio device lists in main tab
        self._main_tab.refresh_audio_devices()
        # Try auto-select USB audio
        self._auto_find_audio_background()

    def _auto_find_audio_background(self) -> None:
        p = self._get_current_profile()
        out_hint = p.output_device_name
        in_hint  = p.input_device_name
        if not p.auto_audio_select:
            return

        def worker():
            try:
                result = self.audio.auto_select_usb_pair(out_hint, in_hint)
                if result:
                    out_idx, in_idx = result
                    outs = dict(list_output_devices())
                    ins  = dict(list_input_devices())
                    out_name = outs.get(out_idx, f"Device {out_idx}")
                    in_name  = ins.get(in_idx, f"Device {in_idx}")
                    self._evq.put_nowait(_AudioPairEvt(out_idx, out_name, in_idx, in_name))
            except Exception as exc:
                _log.debug("Auto-audio select error: %s", exc)

        threading.Thread(target=worker, daemon=True).start()

    # -----------------------------------------------------------------------
    # Connection actions
    # -----------------------------------------------------------------------

    def connect(self, port: str = "") -> None:
        """Connect to SA818 on given port (called from main thread)."""
        port = (port or self.port_var.get()).strip()
        if not port:
            self._set_status("Select a COM port first")
            return

        def worker():
            try:
                self.radio.connect(port)
                # Apply radio settings from profile
                self.after_idle(self._apply_radio_after_connect)
            except SA818Error as exc:
                self._evq.put_nowait(_ErrorEvt("Connection Failed", str(exc)))
            except Exception as exc:
                self._evq.put_nowait(_ErrorEvt("Connection Error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_radio_after_connect(self) -> None:
        p = self._get_current_profile()
        self._apply_radio_config(p)

    def disconnect(self) -> None:
        def worker():
            try:
                self.aprs.stop_rx_monitor()
                self.radio.disconnect()
            except Exception as exc:
                _log.warning("Disconnect error: %s", exc)

        threading.Thread(target=worker, daemon=True).start()

    def scan_ports(self) -> list[str]:
        """Return list of available serial port names (called on main thread)."""
        try:
            import serial.tools.list_ports
            return [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            return []

    def auto_identify_and_connect(self) -> None:
        """Probe all COM ports in background thread; connect to first SA818 found."""
        def worker():
            ports = self.scan_ports()
            if not ports:
                self._evq.put_nowait(_StatusEvt("No COM ports found"))
                return
            for port in ports:
                ok, detail = self.radio.probe_and_connect(port)
                if ok:
                    self._evq.put_nowait(_StatusEvt(f"Auto-connected: {port} ({detail})"))
                    self.after_idle(self._apply_radio_after_connect)
                    return
            self._evq.put_nowait(_StatusEvt("Auto-identify: no SA818 found on any port"))

        threading.Thread(target=worker, daemon=True).start()

    # -----------------------------------------------------------------------
    # Radio config actions
    # -----------------------------------------------------------------------

    def apply_radio(self) -> None:
        """Read radio params from main tab and apply to SA818."""
        if not self.radio.connected:
            self._set_status("Radio not connected")
            return
        p = self._collect_profile_snapshot()
        self._apply_radio_config(p)

    def _apply_radio_config(self, p: AppProfile) -> None:
        def worker():
            try:
                bw = 1 if p.bandwidth.lower().startswith("w") else 0
                ctcss_tx = p.ctcss_tx or None
                ctcss_rx = p.ctcss_rx or None
                dcs_tx   = p.dcs_tx or None
                dcs_rx   = p.dcs_rx or None
                cfg = RadioConfig(
                    frequency=p.frequency,
                    offset=p.offset,
                    bandwidth=bw,
                    squelch=p.squelch,
                    ctcss_tx=ctcss_tx,
                    ctcss_rx=ctcss_rx,
                    dcs_tx=dcs_tx,
                    dcs_rx=dcs_rx,
                )
                self.radio.apply_config(cfg)
                self.radio.set_filters(p.disable_emphasis, p.disable_highpass, p.disable_lowpass)
                self.radio.set_volume(p.volume)
                self._evq.put_nowait(_StatusEvt(
                    f"Radio applied: {p.frequency:.4f} MHz  squelch={p.squelch}  vol={p.volume}"))
            except SA818Error as exc:
                self._evq.put_nowait(_ErrorEvt("Radio Error", str(exc)))
            except Exception as exc:
                self._evq.put_nowait(_ErrorEvt("Radio Error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def apply_filters(self, emphasis: bool, highpass: bool, lowpass: bool) -> None:
        if not self.radio.connected:
            self._set_status("Not connected"); return

        def worker():
            try:
                self.radio.set_filters(emphasis, highpass, lowpass)
                self._evq.put_nowait(_StatusEvt("Filters applied"))
            except Exception as exc:
                self._evq.put_nowait(_ErrorEvt("Filter Error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def set_volume(self, level: int) -> None:
        if not self.radio.connected:
            self._set_status("Not connected"); return

        def worker():
            try:
                self.radio.set_volume(max(1, min(8, level)))
                self._evq.put_nowait(_StatusEvt(f"Volume set to {level}"))
            except Exception as exc:
                self._evq.put_nowait(_ErrorEvt("Volume Error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def apply_tail(self, open_tail: bool) -> None:
        if not self.radio.connected:
            self._set_status("Not connected"); return

        def worker():
            try:
                self.radio.set_tail(open_tail)
                self._evq.put_nowait(_StatusEvt(f"Squelch tail: {'open' if open_tail else 'closed'}"))
            except Exception as exc:
                self._evq.put_nowait(_ErrorEvt("Tail Error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    # -----------------------------------------------------------------------
    # Audio device actions
    # -----------------------------------------------------------------------

    def refresh_audio_devices(self) -> None:
        """Called from MainTab to refresh device lists."""
        outs = self.audio.refresh_output_devices()
        ins  = self.audio.refresh_input_devices()
        self._main_tab.populate_audio_devices(outs, ins)

    def auto_find_audio_pair(self) -> None:
        self._auto_find_audio_background()

    def stop_audio(self) -> None:
        self.audio.stop_audio()
        self._set_status("Audio stopped")

    def set_output_device(self, idx: Optional[int], name: str) -> None:
        self._output_dev_idx  = idx
        self._output_dev_name = name

    def set_input_device(self, idx: Optional[int], name: str) -> None:
        self._input_dev_idx  = idx
        self._input_dev_name = name

    # -----------------------------------------------------------------------
    # APRS helper actions (read from tk vars; called by tab buttons)
    # -----------------------------------------------------------------------

    def apply_callsign_preset(self, src: str, dst: str) -> None:
        self.aprs_source_var.set(src)
        self.aprs_msg_to_var.set(dst)

    def send_aprs_message(self, to: str = "", text: str = "", reliable: bool = False) -> None:
        """Send direct APRS message. When called with no args reads from tab vars."""
        if not to:
            to = self.aprs_msg_to_var.get().strip().upper()
        if not text:
            text = self.aprs_msg_text_var.get().strip()
        if not to or not text:
            self._set_status("Enter To and Message text")
            return
        reliable = reliable or self.aprs_reliable_var.get()
        self._send_aprs_message_impl(to, text, reliable)

    def _send_aprs_message_impl(self, to: str, text: str, reliable: bool) -> None:
        snap = self._make_tx_snapshot()
        if snap is None:
            self._set_status("Cannot TX: check connection / audio device")
            return

        chunks = self.comms.build_direct_chunks(text)
        p = self._get_current_profile()

        for i, chunk in enumerate(chunks):
            # Each chunk gets its own unique message ID so ACK tracking and
            # remote dedup work correctly for multi-part messages.
            msg_id = AprsEngine.new_message_id()
            payload = build_aprs_message_payload(to, chunk, msg_id)
            if reliable:
                self.aprs.send_reliable(
                    addressee=to, text=chunk, snap=snap,
                    message_id=msg_id,
                    timeout_s=p.aprs_ack_timeout,
                    retries=p.aprs_ack_retries,
                )
            else:
                self.aprs.send_payload(payload, snap)

            # Add to comms manager
            msg = ChatMessage(
                direction="TX", src=snap.source, dst=to,
                text=chunk, msg_id=msg_id,
                thread_key=to,
            )
            self.comms.add_message(msg)

    def send_direct_message(self, to: str, text: str, reliable: bool = False) -> None:
        """Alias used by CommsTab."""
        self._send_aprs_message_impl(to, text, reliable)

    def send_aprs_position(self) -> None:
        """Read lat/lon/comment from APRS tab vars and send position."""
        try:
            lat = float(self.aprs_lat_var.get())
            lon = float(self.aprs_lon_var.get())
        except ValueError:
            self._set_status("Invalid lat/lon")
            return
        comment = self.aprs_comment_var.get().strip()
        self.send_position(lat, lon, comment)

    def apply_os_rx_level(self) -> None:
        """Read OS mic level from APRS tab var and apply."""
        level = int(self.aprs_rx_os_level_var.get())
        self._apply_os_rx_level(level)

    def on_rx_auto_toggle(self) -> None:
        """Called when the 'Always-on RX Monitor' checkbox is toggled."""
        if self.aprs_rx_auto_var.get():
            self.start_rx_monitor()
        else:
            self.stop_rx_monitor()

    def rx_one_shot(self) -> None:
        """One-shot RX decode — alias for APRS tab button."""
        self.one_shot_rx()

    def aprs_log(self, msg: str) -> None:
        """Log a message to the APRS monitor (called from tab callbacks)."""
        self._evq.put_nowait(_AprsLogEvt(msg))

    def send_group_message(self, group: str, text: str) -> None:
        snap = self._make_tx_snapshot()
        if snap is None:
            self._set_status("Cannot TX: check connection / audio device")
            return
        chunks = self.comms.build_group_chunks(group, text)
        for i, wire_text in enumerate(chunks):
            msg_id = AprsEngine.new_message_id()
            payload = build_aprs_message_payload(
                group,
                wire_text, msg_id,
            )
            self.aprs.send_payload(payload, snap)
            msg = ChatMessage(
                direction="TX", src=snap.source, dst=group,
                text=text if len(chunks) == 1 else f"[{i+1}/{len(chunks)}] {text}",
                msg_id=msg_id,
                thread_key=f"GROUP:{group}",
            )
            self.comms.add_message(msg)

    def send_position(self, lat: float, lon: float, comment: str) -> None:
        snap = self._make_tx_snapshot()
        if snap is None:
            self._set_status("Cannot TX: check connection / audio device")
            return
        p = self._get_current_profile()
        payload = build_aprs_position_payload(
            lat, lon,
            symbol_table=p.aprs_symbol_table,
            symbol=p.aprs_symbol,
            comment=comment,
        )
        self.aprs.send_payload(payload, snap)
        self._set_status(f"Position TX: {lat:.4f}, {lon:.4f}")

    def send_intro(self, note: str) -> None:
        snap = self._make_tx_snapshot()
        if snap is None:
            self._set_status("Cannot TX: check connection / audio device")
            return
        p = self._get_current_profile()
        payload = self.comms.build_intro_payload(
            snap.source, p.aprs_lat, p.aprs_lon, note)
        self.aprs.send_payload(payload, snap)
        self._set_status(f"Intro TX: {snap.source}")

    # -----------------------------------------------------------------------
    # APRS RX
    # -----------------------------------------------------------------------

    def start_rx_monitor(self) -> None:
        if not self.radio.connected:
            self._set_status("Not connected"); return
        p = self._get_current_profile()
        bw = 1 if p.bandwidth.lower().startswith("w") else 0
        aprs_radio = RadioConfig(
            frequency=p.frequency, offset=0.0, bandwidth=bw,
            squelch=0, ctcss_tx=None, ctcss_rx=None, dcs_tx=None, dcs_rx=None)
        in_dev = getattr(self, "_input_dev_idx", None)
        self.aprs.start_rx_monitor(
            in_dev=in_dev,
            chunk_s=p.aprs_rx_chunk,
            trim_db=p.aprs_rx_trim_db,
            aprs_radio=aprs_radio,
        )
        self._set_status("RX monitor started")
        self._apply_os_rx_level(p.aprs_rx_os_level)

    def stop_rx_monitor(self) -> None:
        def worker():
            self.aprs.stop_rx_monitor()
            self._evq.put_nowait(_StatusEvt("RX monitor stopped"))
        threading.Thread(target=worker, daemon=True).start()

    def one_shot_rx(self) -> None:
        if not self.radio.connected:
            self._set_status("Not connected"); return
        p = self._get_current_profile()
        in_dev = getattr(self, "_input_dev_idx", None)
        self.aprs.one_shot_decode(in_dev, p.aprs_rx_duration, p.aprs_rx_trim_db)

    # -----------------------------------------------------------------------
    # Audio tools
    # -----------------------------------------------------------------------

    def play_test_tone(self, freq: float = 1200.0, duration: float = 2.0) -> None:
        out_dev = getattr(self, "_output_dev_idx", None) or 0
        ptt = self._make_ptt_config()
        self.aprs.play_test_tone(freq, duration, out_dev, ptt)
        self._set_status(f"Test tone: {freq:.0f} Hz  {duration:.1f}s")

    def play_manual_aprs_packet(self, text: str) -> None:
        snap = self._make_tx_snapshot()
        if snap is None:
            self._set_status("Cannot TX: check audio device")
            return
        def worker():
            try:
                wav_path = self._audio_dir / "manual_aprs.wav"
                self._audio_dir.mkdir(parents=True, exist_ok=True)
                write_aprs_wav(
                    wav_path,
                    source=snap.source,
                    destination=snap.destination,
                    path_via=snap.path,
                    message=text,
                    tx_gain=snap.gain,
                    preamble_flags=snap.preamble_flags,
                    trailing_flags=snap.trailing_flags,
                )
                # No PTT — dry run only
                no_ptt = PttConfig(enabled=False)
                self.audio.play_with_ptt_blocking(wav_path, snap.out_dev, no_ptt, None)
                self._evq.put_nowait(_StatusEvt("Manual APRS packet played (no PTT)"))
            except Exception as exc:
                self._evq.put_nowait(_ErrorEvt("Manual APRS Error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def tx_channel_sweep(self) -> None:
        """Run TX channel sweep to help find the correct audio routing."""
        out_dev = getattr(self, "_output_dev_idx", None) or 0
        ptt = self._make_ptt_config()
        sweep_freqs = [1200, 1500, 1800, 2200]

        def ptt_cb(state: bool) -> None:
            try:
                self.radio.set_ptt(state, line=ptt.line, active_high=ptt.active_high)
            except Exception:
                pass

        def worker():
            for f in sweep_freqs:
                try:
                    wav_path = self._audio_dir / f"sweep_{f}.wav"
                    write_test_tone_wav(wav_path, frequency_hz=float(f), seconds=0.4)
                    self.audio.play_with_ptt_blocking(wav_path, out_dev, ptt, ptt_cb)
                except Exception:
                    pass
            self._evq.put_nowait(_StatusEvt("TX channel sweep complete"))

        threading.Thread(target=worker, daemon=True).start()
        self._set_status("Running TX sweep…")

    def auto_detect_rx(self) -> None:
        """Capture a short audio sample and suggest OS mic level."""
        import platform
        if platform.system().lower() != "windows":
            self._set_status("Auto-detect RX level: Windows only")
            return
        in_dev = getattr(self, "_input_dev_idx", None)

        def worker():
            try:
                import numpy as np
                rate, mono = self.audio.capture_compatible(3.0, in_dev)
                rms = float(np.sqrt(np.mean(mono.astype(np.float32) ** 2)))
                # Target: ~-20 dB RMS (0.1 linear) → suggest scaling OS level proportionally
                target = 0.10
                current_level_guess = getattr(self, "_current_os_rx_level", 35)
                if rms > 1e-6:
                    ratio = target / rms
                    suggested = int(max(5, min(100, current_level_guess * ratio)))
                    msg = f"Auto-detect: RMS={rms:.4f}  Suggested OS level={suggested}%"
                    self._evq.put_nowait(_SuggestRxOsLevelEvt(suggested))
                else:
                    suggested = 35
                    msg = "Auto-detect: silence detected — check mic connection"
                self._evq.put_nowait(_StatusEvt(msg))
                self._evq.put_nowait(_AprsLogEvt(msg))
            except Exception as exc:
                self._evq.put_nowait(_StatusEvt(f"Auto-detect error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()
        self._set_status("Capturing 3s for auto-detect…")

    # -----------------------------------------------------------------------
    # Packet handling
    # -----------------------------------------------------------------------

    def _handle_packet(self, pkt: "DecodedPacket") -> None:
        """Process a received APRS packet on the main thread."""
        p = self._get_current_profile()
        local_calls = {p.aprs_source.upper()}
        snap = self._make_tx_snapshot()

        result = self.aprs.handle_received_packet(
            pkt=pkt,
            local_calls=local_calls,
            auto_ack=p.aprs_auto_ack,
            snap=snap,
        )
        if result is None:
            return
        if result.get("duplicate"):
            return

        # Heard station
        src = pkt.source.split("*")[0].strip()
        self.comms.note_heard(src)

        # Map position
        pos = result.get("position")
        if pos:
            lat, lon, comment = pos
            self._aprs_tab.add_map_point(lat, lon, pkt.source)

        # ACK received
        if "ack_id" in result:
            self._aprs_tab.append_log(f"ACK received: id={result['ack_id']} from {pkt.source}")
            return

        # Intro
        intro = result.get("intro")
        if intro:
            call, lat, lon, note = intro
            if self.comms.should_process_intro(call, lat, lon, note):
                self.comms.ensure_contact(call)
                self._aprs_tab.add_map_point(lat, lon, call)
                msg = ChatMessage(direction="RX", src=call, dst=p.aprs_source,
                                   text=f"[Intro] Lat={lat:.4f} Lon={lon:.4f} '{note}'",
                                   thread_key=call)
                self.comms.add_message(msg)
            return

        # Chat message
        msg_fields = result.get("message")
        if msg_fields:
            addressee, msg_text, msg_id = msg_fields

            # Group
            group_fields = result.get("group")
            if group_fields:
                group_name, body, part, total = group_fields
                thread_key = f"GROUP:{group_name}"
                chat_msg = ChatMessage(
                    direction="RX", src=pkt.source, dst=group_name,
                    text=body if (part is None or total is None or total == 1) else f"[{part}/{total}] {body}",
                    thread_key=thread_key, group=group_name,
                )
            else:
                thread_key = self.comms.infer_thread_key(pkt.source, addressee, msg_text, local_calls)
                chat_msg = ChatMessage(
                    direction="RX", src=pkt.source, dst=addressee,
                    text=msg_text, msg_id=msg_id, thread_key=thread_key,
                )

            self.comms.add_message(chat_msg)
            self.comms.set_last_direct_sender(pkt.source)

        # TTS announce
        if hasattr(self, "_setup_tab") and self._setup_tab.tts_enabled:
            self._tts_announce(pkt.source, msg_text if msg_fields else pkt.info)

    # -----------------------------------------------------------------------
    # Comms actions (called by CommsTab)
    # -----------------------------------------------------------------------

    def add_contact(self, call: str) -> None:
        self.comms.add_contact(call)

    def remove_contact(self, call: str) -> None:
        self.comms.remove_contact(call)

    def import_heard_to_contacts(self) -> None:
        self.comms.add_heard_to_contacts()

    def clear_heard(self) -> None:
        self.comms.clear_heard()
        self._comms_tab.refresh_heard()

    def set_group(self, name: str, members: list[str]) -> None:
        self.comms.set_group(name, members)

    def delete_group(self, name: str) -> None:
        self.comms.delete_group(name)

    # -----------------------------------------------------------------------
    # Profile management
    # -----------------------------------------------------------------------

    def save_profile(self, path: Optional[str] = None) -> None:
        """Collect profile from all tabs and save."""
        p = self._collect_profile_snapshot()
        # Add comms data
        comms_data = self.comms.to_dict()
        p.chat_contacts = comms_data["contacts"]
        p.chat_groups   = comms_data["groups"]
        target = ProfileManager(Path(path)) if path else self._prof
        try:
            target.save(p)
            self._set_status(f"Profile saved: {target.path.name}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc), parent=self)

    def load_profile(self, path: Optional[str] = None) -> None:
        src = ProfileManager(Path(path)) if path else self._prof
        p = src.load()
        if p is None:
            messagebox.showinfo("Load Profile", "Profile not found or invalid", parent=self)
            return
        self._apply_profile_to_tabs(p)
        self._set_status(f"Profile loaded: {src.path.name}")

    def import_profile(self) -> None:
        """Open a file dialog and apply the chosen profile (called from MainTab button)."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Import Profile",
            filetypes=(("JSON", "*.json"), ("All files", "*.*")),
            parent=self,
        )
        if not path:
            return
        self.load_profile(path)

    def export_profile(self) -> None:
        """Collect current profile and save it to a user-chosen file (called from MainTab button)."""
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Export Profile",
            filetypes=(("JSON", "*.json"), ("All files", "*.*")),
            defaultextension=".json",
            parent=self,
        )
        if not path:
            return
        self.save_profile(path)

    def reset_defaults(self) -> None:
        self._apply_profile_to_tabs(AppProfile())
        self._set_status("Settings reset to defaults")

    def _load_and_apply_profile(self) -> None:
        p = self._prof.load() or AppProfile()
        self._apply_profile_to_tabs(p)

    def _apply_profile_to_tabs(self, p: AppProfile) -> None:
        self._main_tab.apply_profile(p)
        self._aprs_tab.apply_profile(p)
        self._comms_tab.apply_profile(p)
        self._setup_tab.apply_profile(p)
        # Restore comms contacts/groups
        self.comms.from_dict({"contacts": p.chat_contacts, "groups": p.chat_groups})
        self._comms_tab.refresh_contacts()
        # Cache device indices from names (best-effort)
        self._restore_audio_from_profile(p)

    def _restore_audio_from_profile(self, p: AppProfile) -> None:
        if not p.output_device_name and not p.input_device_name:
            return
        try:
            outs = {n: i for i, n in list_output_devices()}
            ins  = {n: i for i, n in list_input_devices()}
            if p.output_device_name in outs:
                self._output_dev_idx  = outs[p.output_device_name]
                self._output_dev_name = p.output_device_name
            if p.input_device_name in ins:
                self._input_dev_idx  = ins[p.input_device_name]
                self._input_dev_name = p.input_device_name
        except Exception:
            pass

    def _collect_profile_snapshot(self) -> AppProfile:
        p = AppProfile()
        self._main_tab.collect_profile(p)
        self._aprs_tab.collect_profile(p)
        self._comms_tab.collect_profile(p)
        self._setup_tab.collect_profile(p)
        # Store audio device names for future restore
        p.output_device_name = getattr(self, "_output_dev_name", "")
        p.input_device_name  = getattr(self, "_input_dev_name", "")
        return p

    def _get_current_profile(self) -> AppProfile:
        """Collect a lightweight snapshot for engine calls."""
        try:
            return self._collect_profile_snapshot()
        except Exception:
            return AppProfile()

    def _autosave(self) -> None:
        try:
            self.save_profile()
        except Exception:
            pass
        self.after(self.AUTOSAVE_MS, self._autosave)

    # -----------------------------------------------------------------------
    # TX snapshot builder (captures all values needed by engine threads)
    # -----------------------------------------------------------------------

    def _make_tx_snapshot(self) -> Optional[_TxSnapshot]:
        p = self._get_current_profile()
        out_dev = getattr(self, "_output_dev_idx", None)
        if out_dev is None:
            out_dev = 0   # system default
        bw = 1 if p.bandwidth.lower().startswith("w") else 0
        radio = RadioConfig(
            frequency=p.frequency,
            offset=p.offset,
            bandwidth=bw,
            squelch=p.squelch,
            ctcss_tx=p.ctcss_tx or None,
            ctcss_rx=p.ctcss_rx or None,
            dcs_tx=p.dcs_tx or None,
            dcs_rx=p.dcs_rx or None,
        )
        ptt = PttConfig(
            enabled=p.ptt_enabled,
            line=p.ptt_line,
            active_high=p.ptt_active_high,
            pre_ms=p.ptt_pre_ms,
            post_ms=p.ptt_post_ms,
        )
        # Derive port from RadioController client
        port = ""
        try:
            if self.radio.connected and self.radio.client.ser:
                port = str(self.radio.client.ser.port)
        except Exception:
            pass

        return _TxSnapshot(
            source=p.aprs_source,
            destination=p.aprs_dest,
            path=p.aprs_path,
            gain=p.aprs_tx_gain,
            preamble_flags=p.aprs_preamble_flags,
            trailing_flags=16,
            repeats=p.aprs_tx_repeats,
            out_dev=int(out_dev),
            ptt=ptt,
            radio=radio,
            volume=p.volume,
            reinit=p.aprs_tx_reinit,
            port=port,
        )

    def _make_ptt_config(self) -> PttConfig:
        p = self._get_current_profile()
        return PttConfig(
            enabled=p.ptt_enabled,
            line=p.ptt_line,
            active_high=p.ptt_active_high,
            pre_ms=p.ptt_pre_ms,
            post_ms=p.ptt_post_ms,
        )

    # -----------------------------------------------------------------------
    # OS mic level control (Windows / pycaw)
    # -----------------------------------------------------------------------

    _current_os_rx_level: int = 35

    def _apply_os_rx_level(self, level: int) -> None:
        self._current_os_rx_level = level
        import platform
        if platform.system().lower() != "windows":
            return

        def worker():
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                from comtypes import CLSCTX_ALL
                device = AudioUtilities.GetMicrophone()
                interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = interface.QueryInterface(IAudioEndpointVolume)
                volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level / 100.0)), None)
                self._evq.put_nowait(_StatusEvt(f"OS mic level set to {level}%"))
            except ImportError:
                pass  # pycaw not installed — graceful fallback
            except Exception as exc:
                _log.debug("OS mic level error: %s", exc)

        threading.Thread(target=worker, daemon=True).start()

    # -----------------------------------------------------------------------
    # TTS (Windows PowerShell — safe, no injection)
    # -----------------------------------------------------------------------

    def _tts_announce(self, source: str, text: str) -> None:
        import platform
        if platform.system().lower() != "windows":
            return
        # Build speech string safely without any shell interpolation
        speech = f"From {source}: {text}"
        # Escape single quotes for PS string literal
        speech_escaped = speech.replace("'", "''")

        def worker():
            try:
                ps_script = (
                    "Add-Type -AssemblyName System.Speech; "
                    f"(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                    f".Speak('{speech_escaped}')"
                )
                subprocess.run(
                    ["powershell", "-WindowStyle", "Hidden", "-NonInteractive",
                     "-Command", ps_script],
                    check=False, capture_output=True, timeout=15,
                )
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    # -----------------------------------------------------------------------
    # Bootstrap / diagnostics
    # -----------------------------------------------------------------------

    def run_bootstrap(self) -> None:
        script = self._app_dir / "scripts" / "bootstrap_third_party.py"
        if not script.exists():
            messagebox.showinfo("Bootstrap", f"Script not found:\n{script}", parent=self)
            return
        try:
            subprocess.Popen([sys.executable, str(script)], creationflags=subprocess.CREATE_NEW_CONSOLE
                              if sys.platform == "win32" else 0)
        except Exception as exc:
            messagebox.showerror("Bootstrap Error", str(exc), parent=self)

    def run_two_radio_diagnostic(self) -> None:
        script = self._app_dir / "scripts" / "two_radio_diagnostic.py"
        if not script.exists():
            messagebox.showinfo("Diagnostic", f"Script not found:\n{script}", parent=self)
            return
        try:
            subprocess.Popen([sys.executable, str(script)], creationflags=subprocess.CREATE_NEW_CONSOLE
                              if sys.platform == "win32" else 0)
        except Exception as exc:
            messagebox.showerror("Diagnostic Error", str(exc), parent=self)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def refresh_ports(self) -> None:
        """Refresh COM port list in the port combobox (main thread)."""
        ports = self.scan_ports()
        self._main_tab.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])
        self._set_status(f"{len(ports)} port(s) found")

    def auto_identify(self) -> None:
        """Auto-identify SA818 — alias matching MainTab button command."""
        self.auto_identify_and_connect()

    def read_version(self) -> None:
        if not self.radio.connected:
            self._set_status("Not connected"); return

        def worker():
            try:
                ver = self.radio.version()
                self._evq.put_nowait(_StatusEvt(f"SA818 version: {ver}"))
                self._evq.put_nowait(_LogEvt(f"SA818 version: {ver}"))
            except Exception as exc:
                self._evq.put_nowait(_StatusEvt(f"Version error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)
        self.status_var.set(text)

    # -----------------------------------------------------------------------
    # Window close
    # -----------------------------------------------------------------------

    def _on_close(self) -> None:
        try:
            self.save_profile()
        except Exception:
            pass
        # Signal RX monitor to stop (non-blocking; daemon thread will exit on its own)
        try:
            self.aprs._rx_running = False
        except Exception:
            pass
        # Disconnect radio (quick serial close)
        try:
            _close_profile = self._get_current_profile()
            self.radio.release_ptt(
                line=_close_profile.ptt_line,
                active_high=_close_profile.ptt_active_high,
            )
        except Exception:
            pass
        try:
            self.radio.disconnect()
        except Exception:
            pass
        self.destroy()
