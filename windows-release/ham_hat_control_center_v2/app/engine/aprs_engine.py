#!/usr/bin/env python3
"""AprsEngine: manages APRS TX, RX monitor, and reliable messaging.

v2 improvements over v1:
- All tkinter vars are captured as plain Python values before thread launch.
- TX changes radio config and RESTORES it afterwards (push/pop).
- Reliable messaging uses thread-safe monotonic MSG_ID_COUNTER.
- _seen_message_ids uses a time-ordered dict instead of a set, so pruning
  keeps the most-recent entries.
- RX monitor stop() joins the thread with a timeout to prevent orphaned processes.
- Auto-ACK is dispatched on a separate short-lived thread so it never blocks
  the RX capture lock.
- RX chunk floor on Windows enforced here, not in the UI.
"""

from __future__ import annotations

import threading
import wave
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Callable, Optional

import numpy as np

from .aprs_modem import (
    build_aprs_ack_payload,
    build_aprs_message_payload,
    build_aprs_position_payload,
    decode_ax25_from_samples,
    parse_aprs_message_info,
    parse_aprs_position_info,
    parse_group_wire_text,
    parse_intro_wire_text,
    write_aprs_wav,
    write_test_tone_wav,
)
from .audio_router import AudioRouter
from .models import (
    AprsConfig,
    AudioConfig,
    DecodedPacket,
    MSG_ID_COUNTER,
    PttConfig,
    RadioConfig,
)
from .radio_ctrl import RadioController
from .sa818_client import SA818Error


# ---------------------------------------------------------------------------
# TX configuration snapshot (plain Python values — safe to pass to threads)
# ---------------------------------------------------------------------------

class _TxSnapshot:
    __slots__ = (
        "source", "destination", "path", "gain", "preamble_flags",
        "trailing_flags", "repeats", "out_dev", "ptt", "radio",
        "volume", "reinit", "port",
    )

    def __init__(
        self,
        source: str,
        destination: str,
        path: str,
        gain: float,
        preamble_flags: int,
        trailing_flags: int,
        repeats: int,
        out_dev: int,
        ptt: PttConfig,
        radio: RadioConfig,
        volume: int,
        reinit: bool,
        port: str,
    ) -> None:
        self.source = source
        self.destination = destination
        self.path = path
        self.gain = gain
        self.preamble_flags = preamble_flags
        self.trailing_flags = trailing_flags
        self.repeats = repeats
        self.out_dev = out_dev
        self.ptt = ptt
        self.radio = radio
        self.volume = volume
        self.reinit = reinit
        self.port = port


class AprsEngine:
    """Encapsulates all APRS TX/RX workflow logic."""

    # Minimum chunk size on Windows to avoid subprocess overhead swamping RX
    _WIN_MIN_CHUNK_S = 8.0

    def __init__(self, radio: RadioController, audio: AudioRouter, audio_dir: Path) -> None:
        self._radio = radio
        self._audio = audio
        self._audio_dir = audio_dir
        self._audio_lock = threading.Lock()

        # RX monitor state
        self._rx_running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._rx_overlap: Optional[np.ndarray] = None
        self._rx_chunk_floor_logged = False

        # ACK tracking (reliable messaging)
        self._ack_condition = threading.Condition()
        self._acked_ids: set[str] = set()

        # Duplicate suppression: OrderedDict keyed by hash(pkt.text) → timestamp
        self._seen_lock = threading.Lock()
        self._seen_msgs: "OrderedDict[int, float]" = OrderedDict()
        self._seen_direct_ids: "OrderedDict[str, float]" = OrderedDict()

        # Callbacks (called from worker threads → UI must marshal via after())
        self._on_log: Optional[Callable[[str], None]] = None
        self._on_aprs_log: Optional[Callable[[str], None]] = None
        self._on_error: Optional[Callable[[str, str], None]] = None
        self._on_packet: Optional[Callable[[DecodedPacket], None]] = None
        self._on_ack_tx: Optional[Callable[[str, str], None]] = None  # addressee, msg_id
        self._on_output_level: Optional[Callable[[float], None]] = None
        self._on_input_level: Optional[Callable[[float], None]] = None
        self._on_waterfall: Optional[Callable[["np.ndarray", int], None]] = None
        self._on_rx_clip: Optional[Callable[[float], None]] = None

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_log(self, cb: Callable[[str], None]) -> None:
        self._on_log = cb

    def on_aprs_log(self, cb: Callable[[str], None]) -> None:
        self._on_aprs_log = cb

    def on_error(self, cb: Callable[[str, str], None]) -> None:
        self._on_error = cb

    def on_packet(self, cb: Callable[[DecodedPacket], None]) -> None:
        self._on_packet = cb

    def on_ack_tx(self, cb: Callable[[str, str], None]) -> None:
        self._on_ack_tx = cb

    def on_output_level(self, cb: Callable[[float], None]) -> None:
        self._on_output_level = cb

    def on_input_level(self, cb: Callable[[float], None]) -> None:
        self._on_input_level = cb

    def on_waterfall(self, cb: Callable[["np.ndarray", int], None]) -> None:
        self._on_waterfall = cb

    def on_rx_clip(self, cb: Callable[[float], None]) -> None:
        self._on_rx_clip = cb

    # ------------------------------------------------------------------
    # TX
    # ------------------------------------------------------------------

    def send_payload(self, payload: str, snap: _TxSnapshot) -> None:
        """Fire-and-forget: launches a worker thread for TX."""
        t = threading.Thread(target=self._tx_worker, args=(payload, snap), daemon=True)
        t.start()

    def send_payload_blocking(self, payload: str, snap: _TxSnapshot) -> None:
        """Blocking TX — call only from a worker thread."""
        self._do_tx(payload, snap)

    def _tx_worker(self, payload: str, snap: _TxSnapshot) -> None:
        try:
            self._log(
                f"TX config: out={snap.out_dev} gain={snap.gain:.2f} "
                f"preamble={snap.preamble_flags} repeats={snap.repeats}"
            )
            for i in range(snap.repeats):
                self._do_tx(payload, snap, attempt=i + 1)
            self._aprs_log(f"TX {snap.source}>{snap.destination},{snap.path}:{payload}")
        except Exception as exc:
            self._aprs_log(f"TX worker failed: {exc}")

    def _do_tx(self, payload: str, snap: _TxSnapshot, attempt: int = 1) -> None:
        """Prepare radio, play APRS WAV, restore radio config."""
        if not self._radio.connected:
            if snap.reinit and snap.port:
                self._radio.connect(snap.port)
            else:
                raise SA818Error("Radio not connected for APRS TX")

        # Build TX radio config (APRS always uses flat filters, no tones, squelch=4)
        aprs_radio = RadioConfig(
            frequency=snap.radio.frequency,
            offset=0.0,
            bandwidth=snap.radio.bandwidth,
            squelch=4,
            ctcss_tx=None,
            ctcss_rx=None,
            dcs_tx=None,
            dcs_rx=None,
        )

        # push_config saves current config (may be RX monitor config if nested) then applies APRS TX config
        self._radio.push_config(aprs_radio)
        wav_path = None
        try:
            try:
                self._radio.set_filters(True, True, True)
            except Exception as exc:
                self._log(f"Filter set warning before TX: {exc}")
            self._radio.set_volume(max(1, min(8, snap.volume)))

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            wav_path = self._audio_dir / f"aprs_tx_{attempt}_{ts}.wav"
            self._audio_dir.mkdir(parents=True, exist_ok=True)

            write_aprs_wav(
                wav_path,
                source=snap.source,
                destination=snap.destination,
                path_via=snap.path,
                message=payload,
                tx_gain=snap.gain,
                preamble_flags=snap.preamble_flags,
                trailing_flags=snap.trailing_flags,
            )

            def ptt_cb(state: bool) -> None:
                try:
                    self._radio.set_ptt(state, line=snap.ptt.line, active_high=snap.ptt.active_high)
                except Exception as exc:
                    self._log(f"PTT error: {exc}")

            with self._audio_lock:
                self._audio.play_with_ptt_blocking(wav_path, snap.out_dev, snap.ptt, ptt_cb)
        finally:
            # Always restore user radio config
            try:
                restored = self._radio.pop_config()
                if restored:
                    self._log("Radio config restored after TX")
            except Exception as exc:
                self._log(f"Radio restore warning after TX: {exc}")
            # Remove temporary TX WAV to prevent unbounded audio_out/ growth
            if wav_path is not None:
                try:
                    wav_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Reliable TX (ACK/retry)
    # ------------------------------------------------------------------

    def send_reliable(
        self,
        addressee: str,
        text: str,
        snap: _TxSnapshot,
        message_id: str,
        timeout_s: float,
        retries: int,
    ) -> None:
        """Fire-and-forget reliable TX with ACK wait."""
        t = threading.Thread(
            target=self._reliable_worker,
            args=(addressee, text, snap, message_id, timeout_s, retries),
            daemon=True,
        )
        t.start()

    def _reliable_worker(
        self,
        addressee: str,
        text: str,
        snap: _TxSnapshot,
        message_id: str,
        timeout_s: float,
        retries: int,
    ) -> None:
        payload = build_aprs_message_payload(addressee, text, message_id)
        self._aprs_log(f"Reliable TX: id={message_id} retries={retries} timeout={timeout_s:.1f}s")
        for attempt in range(1, retries + 1):
            try:
                self._do_tx(payload, snap, attempt=attempt)
            except Exception as exc:
                self._aprs_log(f"Reliable TX attempt {attempt} failed: {exc}")
                continue
            if self._wait_ack(message_id, timeout_s):
                self._aprs_log(f"Reliable TX delivered: ack {message_id} on attempt {attempt}")
                return
            self._aprs_log(f"Reliable TX attempt {attempt}: ACK timeout for {message_id}")
        self._aprs_log(f"Reliable TX failed: no ACK for {message_id} after {retries} attempts")

    def note_ack(self, message_id: str) -> None:
        mid = message_id.strip()[:5]
        if not mid:
            return
        with self._ack_condition:
            self._acked_ids.add(mid)
            self._ack_condition.notify_all()

    def _wait_ack(self, message_id: str, timeout_s: float) -> bool:
        mid = message_id.strip()[:5]
        if not mid:
            return False
        import time
        deadline = time.monotonic() + max(0.1, timeout_s)
        with self._ack_condition:
            while True:
                if mid in self._acked_ids:
                    self._acked_ids.discard(mid)
                    return True
                remain = deadline - time.monotonic()
                if remain <= 0:
                    return False
                self._ack_condition.wait(timeout=remain)

    @staticmethod
    def new_message_id() -> str:
        return MSG_ID_COUNTER.next()

    # ------------------------------------------------------------------
    # Test tone / test packet
    # ------------------------------------------------------------------

    def play_test_tone(self, freq_hz: float, duration_s: float, out_dev: int, ptt: PttConfig,
                       ptt_cb: Optional[Callable[[bool], None]] = None) -> None:
        def worker() -> None:
            effective_cb = ptt_cb
            if effective_cb is None and ptt.enabled:
                def effective_cb(state: bool) -> None:
                    try:
                        self._radio.set_ptt(state, line=ptt.line, active_high=ptt.active_high)
                    except Exception as exc:
                        self._log(f"PTT error: {exc}")
            try:
                wav_path = self._audio_dir / f"test_tone_{int(freq_hz)}hz.wav"
                self._audio_dir.mkdir(parents=True, exist_ok=True)
                write_test_tone_wav(wav_path, frequency_hz=freq_hz, seconds=duration_s)
                with self._audio_lock:
                    self._audio.play_with_ptt_blocking(wav_path, out_dev, ptt, effective_cb)
            except Exception as exc:
                self._aprs_log(f"Test tone failed: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # RX monitor
    # ------------------------------------------------------------------

    @property
    def rx_running(self) -> bool:
        return self._rx_running

    def start_rx_monitor(
        self,
        in_dev: Optional[int],
        chunk_s: float,
        trim_db: float,
        aprs_radio: RadioConfig,
    ) -> None:
        if self._rx_running:
            self._aprs_log("RX monitor already running")
            return
        self._rx_running = True
        self._rx_overlap = None
        self._rx_chunk_floor_logged = False
        self._radio.push_config(aprs_radio)
        try:
            self._radio.set_filters(True, True, True)
        except Exception:
            pass
        self._aprs_log("RX monitor: SA818 squelch=0 flat filters applied")
        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            args=(in_dev, chunk_s, trim_db),
            daemon=True,
        )
        self._rx_thread.start()
        self._aprs_log("RX monitor started")

    def stop_rx_monitor(self) -> None:
        if not self._rx_running:
            return
        self._rx_running = False
        self._rx_overlap = None
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=12.0)   # wait for current chunk to finish
            self._rx_thread = None
        # Restore user radio config
        try:
            restored = self._radio.pop_config()
            if restored:
                self._aprs_log("RX monitor stopped: radio config restored")
        except Exception as exc:
            self._aprs_log(f"RX monitor restore warning: {exc}")

    def _rx_loop(self, in_dev: Optional[int], chunk_s: float, trim_db: float) -> None:
        import platform
        on_windows = platform.system().lower() == "windows"

        while self._rx_running:
            try:
                effective_chunk = chunk_s
                if on_windows and effective_chunk < self._WIN_MIN_CHUNK_S:
                    effective_chunk = self._WIN_MIN_CHUNK_S
                    if not self._rx_chunk_floor_logged:
                        self._rx_chunk_floor_logged = True
                        self._aprs_log("RX monitor: Windows minimum chunk enforced to 8.0s")

                if not self._audio_lock.acquire(timeout=0.2):
                    sleep(0.05)
                    continue
                try:
                    rate, mono = self._audio.capture_compatible(effective_chunk, in_dev)
                finally:
                    self._audio_lock.release()

                # Signal levels / waterfall
                clip_pct = float(np.mean(np.abs(mono) >= 0.98) * 100.0)
                if self._on_rx_clip:
                    self._on_rx_clip(clip_pct)

                mono_trimmed = _apply_trim_db(mono, trim_db)
                rms = float(np.sqrt(np.mean(mono_trimmed * mono_trimmed)))
                in_level = min(1.0, rms * 8.0)
                if self._on_input_level:
                    self._on_input_level(in_level)
                if self._on_waterfall:
                    self._on_waterfall(mono_trimmed, rate)

                # Energy gate: skip DSP on silent chunks (RMS < -60 dBFS)
                if rms < 0.001:
                    continue

                # Decode with overlap from previous chunk
                overlap = self._rx_overlap
                decode_buf = np.concatenate((overlap, mono_trimmed)) if overlap is not None and len(overlap) > 0 else mono_trimmed
                keep = max(1, int(rate * 1.2))
                self._rx_overlap = decode_buf[-keep:].copy()

                packets = decode_ax25_from_samples(rate, decode_buf)
                now_ts = datetime.now().timestamp()
                dedupe_window = max(2.0, effective_chunk + 1.0)

                for pkt in packets:
                    pkt_key = hash(pkt.text)
                    with self._seen_lock:
                        last_seen = self._seen_msgs.get(pkt_key)
                        if last_seen is not None and (now_ts - last_seen) < dedupe_window:
                            continue
                        # Update dedup dict (time-ordered; prune old entries)
                        self._seen_msgs[pkt_key] = now_ts
                        self._seen_msgs.move_to_end(pkt_key)
                        if len(self._seen_msgs) > 600:
                            cutoff = now_ts - max(30.0, dedupe_window * 2.0)
                            keys_to_del = [k for k, ts in self._seen_msgs.items() if ts < cutoff]
                            for k in keys_to_del:
                                del self._seen_msgs[k]

                    self._aprs_log(f"RX {pkt.text}")
                    if self._on_packet:
                        self._on_packet(pkt)

            except Exception as exc:
                self._aprs_log(f"RX monitor error: {exc}")
                sleep(1.0)

    # ------------------------------------------------------------------
    # One-shot RX decode
    # ------------------------------------------------------------------

    def one_shot_decode(self, in_dev: Optional[int], duration_s: float, trim_db: float) -> None:
        def worker() -> None:
            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                wav_path = self._audio_dir / f"aprs_rx_{ts}.wav"
                self._aprs_log(f"One-shot RX ({duration_s:.1f}s)…")
                with self._audio_lock:
                    self._audio.record_compatible(wav_path, duration_s, in_dev)
                with wave.open(str(wav_path), "rb") as wf:
                    rate = int(wf.getframerate())
                    channels = int(wf.getnchannels())
                    frames = wf.readframes(wf.getnframes())
                mono = np.frombuffer(frames, dtype=np.int16)
                if channels > 1:
                    mono = mono.reshape(-1, channels)[:, 0]
                mono_f = mono.astype(np.float32) / 32768.0
                clip_pct = float(np.mean(np.abs(mono_f) >= 0.98) * 100.0)
                if self._on_rx_clip:
                    self._on_rx_clip(clip_pct)
                mono_trimmed = _apply_trim_db(mono_f, trim_db)
                packets = decode_ax25_from_samples(rate, mono_trimmed)
                if not packets:
                    self._aprs_log("One-shot RX: no packets found")
                    return
                self._aprs_log(f"One-shot RX: {len(packets)} packet(s)")
                for pkt in packets:
                    self._aprs_log(f"RX {pkt.text}")
                    if self._on_packet:
                        self._on_packet(pkt)
            except Exception as exc:
                self._aprs_log(f"One-shot RX failed: {exc}")
                if self._on_error:
                    self._on_error("APRS RX Error", str(exc))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Packet handling (called when a packet is received)
    # ------------------------------------------------------------------

    def handle_received_packet(
        self,
        pkt: DecodedPacket,
        local_calls: set[str],
        auto_ack: bool,
        snap: Optional[_TxSnapshot],
    ) -> Optional[dict]:
        """Process a received packet. Returns a dict of parsed fields for UI,
        or None. Also triggers auto-ACK if needed.

        Returns a dict with keys: position, message, ack_id, group, intro
        """
        result: dict = {}

        # Position (pass destination for Mic-E decoding)
        pos = parse_aprs_position_info(pkt.info, destination=pkt.destination)
        if pos:
            result["position"] = pos  # (lat, lon, comment)

        # Message
        parsed = parse_aprs_message_info(pkt.info)
        if not parsed:
            return result
        addressee, msg_text, msg_id = parsed
        result["message"] = (addressee, msg_text, msg_id)

        # Intro
        intro = parse_intro_wire_text(msg_text)
        if intro:
            result["intro"] = intro

        # ACK
        if msg_text.lower().startswith("ack"):
            ack_id = msg_text[3:].strip()[:5]
            if ack_id:
                self.note_ack(ack_id)
                result["ack_id"] = ack_id
            return result

        # Group
        group_wire = parse_group_wire_text(msg_text)
        if group_wire:
            result["group"] = group_wire

        # Direct message dedup + auto-ACK
        if addressee in local_calls and msg_id:
            dedupe_key = f"{pkt.source}|{msg_id}"
            now_ts = datetime.now().timestamp()
            with self._seen_lock:
                last_seen = self._seen_direct_ids.get(dedupe_key)
                if last_seen is not None and (now_ts - last_seen) < 60.0:
                    result["duplicate"] = True
                    return result
                self._seen_direct_ids[dedupe_key] = now_ts
                self._seen_direct_ids.move_to_end(dedupe_key)
                if len(self._seen_direct_ids) > 400:
                    # Prune oldest 200
                    for _ in range(200):
                        self._seen_direct_ids.popitem(last=False)

            if auto_ack and snap is not None:
                self._dispatch_auto_ack(pkt.source, msg_id, snap)

        return result

    def _dispatch_auto_ack(self, addressee: str, msg_id: str, snap: _TxSnapshot) -> None:
        """Send ACK in a short-lived thread so it doesn't block RX capture."""
        def ack_worker() -> None:
            try:
                ack_payload = build_aprs_ack_payload(addressee=addressee, message_id=msg_id)
                self._do_tx(ack_payload, snap)
                self._aprs_log(f"Auto-ACK sent to {addressee} for {msg_id}")
                if self._on_ack_tx:
                    self._on_ack_tx(addressee, msg_id)
            except Exception as exc:
                self._aprs_log(f"Auto-ACK failed: {exc}")

        threading.Thread(target=ack_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Internal logging
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        if self._on_log:
            self._on_log(msg)

    def _aprs_log(self, msg: str) -> None:
        if self._on_aprs_log:
            self._on_aprs_log(msg)


# ---------------------------------------------------------------------------
# DSP helper
# ---------------------------------------------------------------------------

def _apply_trim_db(mono: np.ndarray, trim_db: float) -> np.ndarray:
    db = min(0.0, max(-30.0, float(trim_db)))
    gain = float(10.0 ** (db / 20.0))
    return np.clip(mono.astype(np.float32) * gain, -1.0, 1.0)
