#!/usr/bin/env python3
"""SA818 serial control backend used by the UI."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

import serial


CTCSS = (
    "None",
    "67.0", "71.9", "74.4", "77.0", "79.7", "82.5", "85.4", "88.5", "91.5", "94.8",
    "97.4", "100.0", "103.5", "107.2", "110.9", "114.8", "118.8", "123.0", "127.3", "131.8",
    "136.5", "141.3", "146.2", "151.4", "156.7", "162.2", "167.9", "173.8", "179.9", "186.2",
    "192.8", "203.5", "210.7", "218.1", "225.7", "233.6", "241.8", "250.3",
)

DCS_CODES = {
    "023", "025", "026", "031", "032", "036", "043", "047", "051", "053", "054", "065", "071",
    "072", "073", "074", "114", "115", "116", "125", "131", "132", "134", "143", "152", "155",
    "156", "162", "165", "172", "174", "205", "223", "226", "243", "244", "245", "251", "261",
    "263", "265", "271", "306", "311", "315", "331", "343", "346", "351", "364", "365", "371",
    "411", "412", "413", "423", "431", "432", "445", "464", "465", "466", "503", "506", "516",
    "532", "546", "565", "606", "612", "624", "627", "631", "632", "654", "662", "664", "703",
    "712", "723", "731", "732", "734", "743", "754",
}


class SA818Error(Exception):
    pass


@dataclass
class RadioConfig:
    frequency: float
    offset: float = 0.0
    bandwidth: int = 1  # 0 narrow, 1 wide
    squelch: int = 4
    ctcss_tx: str | None = None
    ctcss_rx: str | None = None
    dcs_tx: str | None = None
    dcs_rx: str | None = None


class SA818Client:
    EOL = "\r\n"

    def __init__(self) -> None:
        self.ser: serial.Serial | None = None
        self._io_lock = threading.RLock()

    @property
    def connected(self) -> bool:
        return bool(self.ser and self.ser.is_open)

    def connect(self, port: str, baud: int = 9600, timeout: float = 2.0) -> None:
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
            self._set_safe_control_lines()
            self._clear_rx_buffer()
            reply = self.command("AT+DMOCONNECT", pause=0.5)
            if reply != "+DMOCONNECT:0":
                self.disconnect()
                raise SA818Error(f"Unexpected connect reply: {reply}")

    @classmethod
    def probe_sa818(cls, port: str, baud: int = 9600, timeout: float = 0.8) -> tuple[bool, str]:
        """Probe a serial port and return whether it appears to be an SA818."""
        client = cls()
        try:
            client.connect(port=port, baud=baud, timeout=timeout)
            try:
                version = client.version()
                return True, version
            except Exception:  # noqa: BLE001
                # Some firmware variants respond differently to version query.
                return True, "+DMOCONNECT:0"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            client.disconnect()

    def disconnect(self) -> None:
        with self._io_lock:
            if self.ser:
                try:
                    self.set_ptt(False)
                    self.ser.close()
                finally:
                    self.ser = None

    def command(self, cmd: str, pause: float = 0.8) -> str:
        with self._io_lock:
            if not self.connected:
                raise SA818Error("Serial port not connected")
            assert self.ser is not None
            # Keep modem control lines deasserted to avoid accidental PTT keying.
            self._set_safe_control_lines()
            self._clear_rx_buffer()
            self.ser.write((cmd + self.EOL).encode("ascii"))
            self.ser.flush()
            if pause > 0:
                time.sleep(pause)

            raw = ""
            timeout = float(self.ser.timeout or 1.0)
            deadline = time.monotonic() + max(1.2, timeout + 0.4)
            while time.monotonic() < deadline:
                line = self.ser.readline().decode("ascii", errors="replace").strip()
                if line:
                    raw = line
                    break

            self._set_safe_control_lines()
            if not raw:
                raise SA818Error(f"No reply for command: {cmd}")
            return raw

    def version(self) -> str:
        reply = self.command("AT+VERSION", pause=0.5)
        return reply

    def set_volume(self, level: int) -> str:
        if level < 1 or level > 8:
            raise SA818Error("Volume must be 1..8")
        reply = self.command(f"AT+DMOSETVOLUME={level}")
        if reply != "+DMOSETVOLUME:0":
            raise SA818Error(f"Volume failed: {reply}")
        return reply

    def set_filters(self, disable_emphasis: bool, disable_highpass: bool, disable_lowpass: bool) -> str:
        e = int(disable_emphasis)
        h = int(disable_highpass)
        l = int(disable_lowpass)
        reply = self.command(f"AT+SETFILTER={e},{h},{l}")
        if reply != "+DMOSETFILTER:0":
            raise SA818Error(f"Filter config failed: {reply}")
        return reply

    def set_tail(self, open_tail: bool) -> str:
        v = 1 if open_tail else 0
        reply = self.command(f"AT+SETTAIL={v}")
        if reply != "+DMOSETTAIL:0":
            raise SA818Error(f"Tail config failed: {reply}")
        return reply

    def set_radio(self, cfg: RadioConfig) -> str:
        self._validate_frequency(cfg.frequency)
        if cfg.squelch < 0 or cfg.squelch > 8:
            raise SA818Error("Squelch must be 0..8")
        if cfg.bandwidth not in (0, 1):
            raise SA818Error("Bandwidth must be 0 (narrow) or 1 (wide)")

        tx_freq = cfg.frequency + cfg.offset
        rx_freq = cfg.frequency

        tx_tone, rx_tone = self._encode_tones(cfg)
        cmd = f"AT+DMOSETGROUP={cfg.bandwidth},{tx_freq:.4f},{rx_freq:.4f},{tx_tone},{cfg.squelch},{rx_tone}"
        reply = self.command(cmd)
        if reply != "+DMOSETGROUP:0":
            raise SA818Error(f"Radio config failed: {reply}")
        return reply

    def _encode_tones(self, cfg: RadioConfig) -> tuple[str, str]:
        if cfg.ctcss_tx or cfg.ctcss_rx:
            tx = cfg.ctcss_tx or "None"
            rx = cfg.ctcss_rx or tx
            return self._encode_ctcss(tx), self._encode_ctcss(rx)

        if cfg.dcs_tx or cfg.dcs_rx:
            tx = cfg.dcs_tx or "0000"
            rx = cfg.dcs_rx or tx
            return self._encode_dcs(tx), self._encode_dcs(rx)

        return "0000", "0000"

    @staticmethod
    def _validate_frequency(freq: float) -> None:
        vhf_ok = 136.0 <= freq <= 174.0
        uhf_ok = 400.0 <= freq <= 470.0
        if not (vhf_ok or uhf_ok):
            raise SA818Error("Frequency must be in 136-174 MHz or 400-470 MHz")

    @staticmethod
    def _encode_ctcss(value: str) -> str:
        norm = value.strip()
        if norm.lower() == "none":
            return "0000"
        try:
            n = str(float(norm))
        except ValueError as exc:
            raise SA818Error(f"Invalid CTCSS: {value}") from exc
        if n not in CTCSS:
            raise SA818Error(f"Unsupported CTCSS: {value}")
        return f"{CTCSS.index(n):04d}"

    @staticmethod
    def _encode_dcs(value: str) -> str:
        norm = value.strip().upper()
        if norm in ("NONE", "0000"):
            return "0000"
        if not re.match(r"^\d{3}[NI]$", norm):
            raise SA818Error(f"DCS must be like 047N or 047I, got: {value}")
        code = norm[:3]
        if code not in DCS_CODES:
            raise SA818Error(f"Unsupported DCS code: {value}")
        return norm

    def _set_safe_control_lines(self) -> None:
        """Force DTR/RTS low so USB-UART control lines cannot hold PTT active."""
        if not self.ser:
            return
        try:
            self.ser.dtr = False
            self.ser.rts = False
        except Exception:
            # Some adapters may not expose both lines; ignore safely.
            pass

    def _clear_rx_buffer(self) -> None:
        if not self.ser:
            return
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass

    def set_ptt(self, enabled: bool, line: str = "RTS", active_high: bool = True) -> None:
        """
        Control PTT by driving selected modem control line.

        Args:
            enabled: desired PTT state
            line: 'RTS' or 'DTR'
            active_high: if True, asserted line means TX
        """
        with self._io_lock:
            if not self.connected or not self.ser:
                raise SA818Error("Cannot set PTT when serial is not connected")

            drive = enabled if active_high else (not enabled)
            line_name = line.strip().upper()
            try:
                if line_name == "RTS":
                    self.ser.rts = drive
                elif line_name == "DTR":
                    self.ser.dtr = drive
                else:
                    raise SA818Error(f"Unsupported PTT line: {line}")
            except SA818Error:
                raise
            except Exception as exc:  # noqa: BLE001
                raise SA818Error(f"Failed to set PTT on {line_name}: {exc}") from exc
