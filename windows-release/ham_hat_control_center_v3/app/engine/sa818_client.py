#!/usr/bin/env python3
"""SA818 serial control backend.

Improvements over v1:
- All public methods validate connection state explicitly.
- probe_sa818 is a classmethod returning a typed result.
- set_ptt always safe-guards modem lines before/after commands.
- set_tail fix: returns properly.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Optional

import serial

from .models import RadioConfig


# ---------------------------------------------------------------------------
# CTCSS / DCS tables
# ---------------------------------------------------------------------------

CTCSS: tuple[str, ...] = (
    "None",
    "67.0", "71.9", "74.4", "77.0", "79.7", "82.5", "85.4", "88.5", "91.5", "94.8",
    "97.4", "100.0", "103.5", "107.2", "110.9", "114.8", "118.8", "123.0", "127.3", "131.8",
    "136.5", "141.3", "146.2", "151.4", "156.7", "162.2", "167.9", "173.8", "179.9", "186.2",
    "192.8", "203.5", "210.7", "218.1", "225.7", "233.6", "241.8", "250.3",
)

DCS_CODES: frozenset[str] = frozenset({
    "023", "025", "026", "031", "032", "036", "043", "047", "051", "053", "054", "065", "071",
    "072", "073", "074", "114", "115", "116", "125", "131", "132", "134", "143", "152", "155",
    "156", "162", "165", "172", "174", "205", "223", "226", "243", "244", "245", "251", "261",
    "263", "265", "271", "306", "311", "315", "331", "343", "346", "351", "364", "365", "371",
    "411", "412", "413", "423", "431", "432", "445", "464", "465", "466", "503", "506", "516",
    "532", "546", "565", "606", "612", "624", "627", "631", "632", "654", "662", "664", "703",
    "712", "723", "731", "732", "734", "743", "754",
})


class SA818Error(Exception):
    pass


class SA818Client:
    EOL = "\r\n"
    _DEFAULT_BAUD = 9600
    _DEFAULT_TIMEOUT = 2.0

    def __init__(self) -> None:
        self.ser: Optional[serial.Serial] = None
        self._io_lock = threading.RLock()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return bool(self.ser and self.ser.is_open)

    def connect(self, port: str, baud: int = _DEFAULT_BAUD, timeout: float = _DEFAULT_TIMEOUT) -> None:
        with self._io_lock:
            self.disconnect()
            self.ser = serial.Serial(
                port=port,
                baudrate=baud,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=timeout,
                dsrdtr=False,
                rtscts=False,
                xonxoff=False,
            )
            self._safe_modem_lines()
            self._flush_rx()
            reply = self._command("AT+DMOCONNECT", pause=0.5)
            if reply != "+DMOCONNECT:0":
                self.disconnect()
                raise SA818Error(f"Unexpected connect reply: {reply!r}")

    @classmethod
    def probe(cls, port: str, baud: int = _DEFAULT_BAUD, timeout: float = 0.8) -> tuple[bool, str]:
        """Try to connect to port; return (success, version_or_error)."""
        client = cls()
        try:
            client.connect(port=port, baud=baud, timeout=timeout)
            try:
                version = client.version()
                return True, version
            except Exception:
                return True, "+DMOCONNECT:0"
        except Exception as exc:
            return False, str(exc)
        finally:
            client.disconnect()

    def disconnect(self) -> None:
        with self._io_lock:
            if self.ser:
                try:
                    self._release_ptt_safe()
                    self.ser.close()
                finally:
                    self.ser = None

    # ------------------------------------------------------------------
    # Raw command
    # ------------------------------------------------------------------

    def _command(self, cmd: str, pause: float = 0.8) -> str:
        """Send AT command and return stripped reply. Must hold _io_lock."""
        if not self.connected or self.ser is None:
            raise SA818Error("Not connected")
        self._safe_modem_lines()
        self._flush_rx()
        self.ser.write((cmd + self.EOL).encode("ascii"))
        self.ser.flush()
        if pause > 0:
            time.sleep(pause)
        timeout_s = float(self.ser.timeout or 1.0)
        deadline = time.monotonic() + max(1.2, timeout_s + 0.4)
        raw = ""
        while time.monotonic() < deadline:
            line = self.ser.readline().decode("ascii", errors="replace").strip()
            if line:
                raw = line
                break
        self._safe_modem_lines()
        if not raw:
            raise SA818Error(f"No reply for: {cmd!r}")
        return raw

    def command(self, cmd: str, pause: float = 0.8) -> str:
        """Public command interface (thread-safe)."""
        with self._io_lock:
            return self._command(cmd, pause)

    # ------------------------------------------------------------------
    # SA818 commands
    # ------------------------------------------------------------------

    def version(self) -> str:
        return self.command("AT+VERSION", pause=0.5)

    def set_volume(self, level: int) -> str:
        if not 1 <= level <= 8:
            raise SA818Error("Volume must be 1..8")
        reply = self.command(f"AT+DMOSETVOLUME={level}")
        if reply != "+DMOSETVOLUME:0":
            raise SA818Error(f"Volume failed: {reply!r}")
        return reply

    def set_filters(self, disable_emphasis: bool, disable_highpass: bool, disable_lowpass: bool) -> str:
        e, h, lp = int(disable_emphasis), int(disable_highpass), int(disable_lowpass)
        reply = self.command(f"AT+SETFILTER={e},{h},{lp}")
        if reply != "+DMOSETFILTER:0":
            raise SA818Error(f"Filter config failed: {reply!r}")
        return reply

    def set_tail(self, open_tail: bool) -> str:
        reply = self.command(f"AT+SETTAIL={int(open_tail)}")
        if reply != "+DMOSETTAIL:0":
            raise SA818Error(f"Tail config failed: {reply!r}")
        return reply

    def set_radio(self, cfg: RadioConfig) -> str:
        _validate_frequency(cfg.frequency)
        if not 0 <= cfg.squelch <= 8:
            raise SA818Error("Squelch must be 0..8")
        if cfg.bandwidth not in (0, 1):
            raise SA818Error("Bandwidth must be 0 (narrow) or 1 (wide)")

        tx_freq = cfg.frequency + cfg.offset
        rx_freq = cfg.frequency
        tx_tone, rx_tone = _encode_tones(cfg)
        cmd = (
            f"AT+DMOSETGROUP={cfg.bandwidth},"
            f"{tx_freq:.4f},{rx_freq:.4f},"
            f"{tx_tone},{cfg.squelch},{rx_tone}"
        )
        reply = self.command(cmd)
        if reply != "+DMOSETGROUP:0":
            raise SA818Error(f"Radio config failed: {reply!r}")
        return reply

    # ------------------------------------------------------------------
    # PTT
    # ------------------------------------------------------------------

    def set_ptt(self, enabled: bool, line: str = "RTS", active_high: bool = True) -> None:
        with self._io_lock:
            if not self.connected or self.ser is None:
                raise SA818Error("Cannot set PTT: not connected")
            drive = enabled if active_high else (not enabled)
            line_name = line.strip().upper()
            try:
                if line_name == "RTS":
                    self.ser.rts = drive
                elif line_name == "DTR":
                    self.ser.dtr = drive
                else:
                    raise SA818Error(f"Unsupported PTT line: {line!r}")
            except SA818Error:
                raise
            except Exception as exc:
                raise SA818Error(f"PTT set failed on {line_name}: {exc}") from exc

    def _release_ptt_safe(self) -> None:
        """Release PTT without raising. Call before closing port."""
        if not self.ser:
            return
        try:
            self.ser.rts = False
            self.ser.dtr = False
        except Exception:
            pass

    def _safe_modem_lines(self) -> None:
        """Force DTR/RTS low so control lines cannot accidentally key PTT."""
        if not self.ser:
            return
        try:
            self.ser.dtr = False
            self.ser.rts = False
        except Exception:
            pass

    def _flush_rx(self) -> None:
        if not self.ser:
            return
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers (module-level so they can be shared with radio_ctrl)
# ---------------------------------------------------------------------------

def _validate_frequency(freq: float) -> None:
    vhf = 136.0 <= freq <= 174.0
    uhf = 400.0 <= freq <= 470.0
    if not (vhf or uhf):
        raise SA818Error("Frequency must be 136-174 MHz or 400-470 MHz")


def _encode_tones(cfg: RadioConfig) -> tuple[str, str]:
    if cfg.ctcss_tx or cfg.ctcss_rx:
        tx = cfg.ctcss_tx or "None"
        rx = cfg.ctcss_rx or tx
        return _encode_ctcss(tx), _encode_ctcss(rx)
    if cfg.dcs_tx or cfg.dcs_rx:
        tx = cfg.dcs_tx or "0000"
        rx = cfg.dcs_rx or tx
        return _encode_dcs(tx), _encode_dcs(rx)
    return "0000", "0000"


def _encode_ctcss(value: str) -> str:
    norm = value.strip()
    if norm.lower() == "none":
        return "0000"
    try:
        n = str(float(norm))
    except ValueError as exc:
        raise SA818Error(f"Invalid CTCSS: {value!r}") from exc
    if n not in CTCSS:
        raise SA818Error(f"Unsupported CTCSS: {value!r}")
    return f"{CTCSS.index(n):04d}"


def _encode_dcs(value: str) -> str:
    norm = value.strip().upper()
    if norm in ("NONE", "0000"):
        return "0000"
    if not re.match(r"^\d{3}[NI]$", norm):
        raise SA818Error(f"DCS must be like 047N or 047I, got: {value!r}")
    code = norm[:3]
    if code not in DCS_CODES:
        raise SA818Error(f"Unsupported DCS code: {value!r}")
    return norm
