#!/usr/bin/env python3
"""ProfileManager: validated load/save of AppProfile to JSON.

v2 improvements over v1:
- All fields are typed and validated at load time with safe defaults.
- Numeric fields that fail parsing produce a log warning rather than a
  silent failure or crash later during radio apply.
- Profile is represented as AppProfile dataclass, not a raw dict.
- Backward-compatible: missing keys fall back to AppProfile defaults.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .models import AppProfile

_log = logging.getLogger(__name__)


class ProfileManager:
    def __init__(self, profile_path: Path) -> None:
        self._path = profile_path

    @property
    def path(self) -> Path:
        return self._path

    def save(self, profile: AppProfile) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = _profile_to_dict(profile)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self) -> Optional[AppProfile]:
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8-sig"))
            return _dict_to_profile(raw)
        except Exception as exc:
            _log.warning("Profile load failed (%s); using defaults", exc)
            return None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _profile_to_dict(p: AppProfile) -> dict:
    return {
        "frequency": p.frequency,
        "offset": p.offset,
        "squelch": p.squelch,
        "bandwidth": p.bandwidth,
        "ctcss_tx": p.ctcss_tx,
        "ctcss_rx": p.ctcss_rx,
        "dcs_tx": p.dcs_tx,
        "dcs_rx": p.dcs_rx,
        "disable_emphasis": p.disable_emphasis,
        "disable_highpass": p.disable_highpass,
        "disable_lowpass": p.disable_lowpass,
        "volume": p.volume,
        "aprs_source": p.aprs_source,
        "aprs_dest": p.aprs_dest,
        "aprs_path": p.aprs_path,
        "aprs_tx_gain": p.aprs_tx_gain,
        "aprs_preamble_flags": p.aprs_preamble_flags,
        "aprs_tx_repeats": p.aprs_tx_repeats,
        "aprs_tx_reinit": p.aprs_tx_reinit,
        "aprs_symbol_table": p.aprs_symbol_table,
        "aprs_symbol": p.aprs_symbol,
        "aprs_msg_to": p.aprs_msg_to,
        "aprs_msg_text": p.aprs_msg_text,
        "aprs_reliable": p.aprs_reliable,
        "aprs_ack_timeout": p.aprs_ack_timeout,
        "aprs_ack_retries": p.aprs_ack_retries,
        "aprs_auto_ack": p.aprs_auto_ack,
        "aprs_lat": p.aprs_lat,
        "aprs_lon": p.aprs_lon,
        "aprs_comment": p.aprs_comment,
        "aprs_rx_duration": p.aprs_rx_duration,
        "aprs_rx_chunk": p.aprs_rx_chunk,
        "aprs_rx_trim_db": p.aprs_rx_trim_db,
        "aprs_rx_os_level": p.aprs_rx_os_level,
        "aprs_rx_auto": p.aprs_rx_auto,
        "output_device_name": p.output_device_name,
        "input_device_name": p.input_device_name,
        "auto_audio_select": p.auto_audio_select,
        "ptt_enabled": p.ptt_enabled,
        "ptt_line": p.ptt_line,
        "ptt_active_high": p.ptt_active_high,
        "ptt_pre_ms": p.ptt_pre_ms,
        "ptt_post_ms": p.ptt_post_ms,
        "test_tone_freq": p.test_tone_freq,
        "test_tone_duration": p.test_tone_duration,
        "manual_aprs_text": p.manual_aprs_text,
        "chat_contacts": p.chat_contacts,
        "chat_groups": p.chat_groups,
        "chat_intro_note": p.chat_intro_note,
        "hardware_mode": p.hardware_mode,
        "digirig_port": p.digirig_port,
    }


def _dict_to_profile(d: dict) -> AppProfile:
    p = AppProfile()

    def _float(key: str, default: float, lo: float = -1e9, hi: float = 1e9) -> float:
        try:
            v = float(d.get(key, default))
            return max(lo, min(hi, v))
        except Exception:
            _log.warning("Profile: invalid float for %r, using default %s", key, default)
            return default

    def _int(key: str, default: int, lo: int = -999999, hi: int = 999999) -> int:
        try:
            v = int(d.get(key, default))
            return max(lo, min(hi, v))
        except Exception:
            _log.warning("Profile: invalid int for %r, using default %s", key, default)
            return default

    def _bool(key: str, default: bool) -> bool:
        v = d.get(key, default)
        if isinstance(v, bool):
            return v
        return bool(v)

    def _str(key: str, default: str) -> str:
        return str(d.get(key, default))

    p.frequency = _float("frequency", AppProfile.frequency, 136.0, 470.0)
    p.offset = _float("offset", AppProfile.offset, -10.0, 10.0)
    p.squelch = _int("squelch", AppProfile.squelch, 0, 8)
    p.bandwidth = _str("bandwidth", AppProfile.bandwidth)
    p.ctcss_tx = _str("ctcss_tx", AppProfile.ctcss_tx)
    p.ctcss_rx = _str("ctcss_rx", AppProfile.ctcss_rx)
    p.dcs_tx = _str("dcs_tx", AppProfile.dcs_tx)
    p.dcs_rx = _str("dcs_rx", AppProfile.dcs_rx)
    p.disable_emphasis = _bool("disable_emphasis", AppProfile.disable_emphasis)
    p.disable_highpass = _bool("disable_highpass", AppProfile.disable_highpass)
    p.disable_lowpass = _bool("disable_lowpass", AppProfile.disable_lowpass)
    p.volume = _int("volume", AppProfile.volume, 1, 8)
    p.aprs_source = _str("aprs_source", AppProfile.aprs_source)
    p.aprs_dest = _str("aprs_dest", AppProfile.aprs_dest)
    p.aprs_path = _str("aprs_path", AppProfile.aprs_path)
    p.aprs_tx_gain = _float("aprs_tx_gain", AppProfile.aprs_tx_gain, 0.05, 0.40)
    p.aprs_preamble_flags = _int("aprs_preamble_flags", AppProfile.aprs_preamble_flags, 16, 400)
    p.aprs_tx_repeats = _int("aprs_tx_repeats", AppProfile.aprs_tx_repeats, 1, 5)
    p.aprs_tx_reinit = _bool("aprs_tx_reinit", AppProfile.aprs_tx_reinit)
    p.aprs_symbol_table = _str("aprs_symbol_table", AppProfile.aprs_symbol_table)
    p.aprs_symbol = _str("aprs_symbol", AppProfile.aprs_symbol)
    p.aprs_msg_to = _str("aprs_msg_to", AppProfile.aprs_msg_to)
    p.aprs_msg_text = _str("aprs_msg_text", AppProfile.aprs_msg_text)
    p.aprs_reliable = _bool("aprs_reliable", AppProfile.aprs_reliable)
    p.aprs_ack_timeout = _float("aprs_ack_timeout", AppProfile.aprs_ack_timeout, 1.0, 120.0)
    p.aprs_ack_retries = _int("aprs_ack_retries", AppProfile.aprs_ack_retries, 1, 10)
    p.aprs_auto_ack = _bool("aprs_auto_ack", AppProfile.aprs_auto_ack)
    p.aprs_lat = _float("aprs_lat", AppProfile.aprs_lat, -90.0, 90.0)
    p.aprs_lon = _float("aprs_lon", AppProfile.aprs_lon, -180.0, 180.0)
    p.aprs_comment = _str("aprs_comment", AppProfile.aprs_comment)
    p.aprs_rx_duration = _float("aprs_rx_duration", AppProfile.aprs_rx_duration, 1.0, 300.0)
    p.aprs_rx_chunk = _float("aprs_rx_chunk", AppProfile.aprs_rx_chunk, 1.0, 60.0)
    p.aprs_rx_trim_db = _float("aprs_rx_trim_db", AppProfile.aprs_rx_trim_db, -30.0, 0.0)
    p.aprs_rx_os_level = _int("aprs_rx_os_level", AppProfile.aprs_rx_os_level, 1, 100)
    p.aprs_rx_auto = _bool("aprs_rx_auto", AppProfile.aprs_rx_auto)
    p.output_device_name = _str("output_device_name", AppProfile.output_device_name)
    p.input_device_name = _str("input_device_name", AppProfile.input_device_name)
    p.auto_audio_select = _bool("auto_audio_select", AppProfile.auto_audio_select)
    p.ptt_enabled = _bool("ptt_enabled", AppProfile.ptt_enabled)
    p.ptt_line = _str("ptt_line", AppProfile.ptt_line)
    p.ptt_active_high = _bool("ptt_active_high", AppProfile.ptt_active_high)
    p.ptt_pre_ms = _int("ptt_pre_ms", AppProfile.ptt_pre_ms, 0, 5000)
    p.ptt_post_ms = _int("ptt_post_ms", AppProfile.ptt_post_ms, 0, 5000)
    p.test_tone_freq = _float("test_tone_freq", AppProfile.test_tone_freq, 100.0, 20000.0)
    p.test_tone_duration = _float("test_tone_duration", AppProfile.test_tone_duration, 0.1, 30.0)
    p.manual_aprs_text = _str("manual_aprs_text", AppProfile.manual_aprs_text)

    raw_contacts = d.get("chat_contacts", [])
    p.chat_contacts = [c.strip().upper() for c in raw_contacts if isinstance(c, str) and c.strip()]
    raw_groups = d.get("chat_groups", {})
    if isinstance(raw_groups, dict):
        p.chat_groups = {
            k.strip().upper(): [m.strip().upper() for m in v if isinstance(m, str) and m.strip()]
            for k, v in raw_groups.items()
            if isinstance(k, str) and k.strip()
        }
    p.chat_intro_note = _str("chat_intro_note", AppProfile.chat_intro_note)

    hw = _str("hardware_mode", AppProfile.hardware_mode)
    p.hardware_mode = hw if hw in ("SA818", "DigiRig") else "SA818"
    p.digirig_port = _str("digirig_port", AppProfile.digirig_port)

    return p
