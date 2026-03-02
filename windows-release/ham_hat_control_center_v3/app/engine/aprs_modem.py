#!/usr/bin/env python3
"""APRS payload helpers and AX.25/AFSK modem.

v2 improvements over v1:
- AFSK encoder fully vectorized with numpy (no per-sample Python loop).
- Test tone generation fully vectorized.
- _crc16_x25 defined once here; audio_tools imports from this module.
- Group wire wire-text length properly validates against APRS body limit
  after prefix overhead is deducted.
- Message text splitting accounts for group prefix length.
- APRS position comment capped at 40 chars (APRS spec recommendation).
- Decoder unchanged (already robust); brute-force spp/tone/inversion
  search retained for maximum interoperability.
"""

from __future__ import annotations

import functools
import math
import re
import wave
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .models import DecodedPacket

# Use scipy fftconvolve when available (significantly faster for large FIR kernels)
try:
    from scipy.signal import fftconvolve as _fftconvolve
    def _convolve(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return _fftconvolve(a, b, mode="same")
except ImportError:
    def _convolve(a: np.ndarray, b: np.ndarray) -> np.ndarray:  # type: ignore[misc]
        return np.convolve(a, b, mode="same")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APRS_MESSAGE_BODY_MAX = 67          # APRS spec: max message text+id field
APRS_MESSAGE_TEXT_MAX = 67          # no ID variant: same limit
APRS_POSITION_COMMENT_MAX = 40      # recommended by APRS spec

FLAG_BITS: list[int] = [0, 1, 1, 1, 1, 1, 1, 0]  # 0x7E LSB-first

GROUP_WIRE_RE = re.compile(
    r"^@GRP/([A-Z0-9_-]{1,16})(?:/([0-9]{1,2})/([0-9]{1,2}))?:(.*)$",
    flags=re.IGNORECASE,
)
INTRO_WIRE_RE = re.compile(
    r"^@INTRO/([A-Z0-9]{1,6}(?:-[0-9]{1,2})?)"
    r"/(-?[0-9]{1,2}(?:\.[0-9]+)?)"
    r"/(-?[0-9]{1,3}(?:\.[0-9]+)?):?(.*)$",
    flags=re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# AX.25 frame builder (TX path)
# ---------------------------------------------------------------------------

def build_ax25_ui_frame(source: str, destination: str, path_via: str, info: str) -> bytes:
    addrs = [
        _encode_ax25_addr(destination, is_last=False),
        _encode_ax25_addr(source, is_last=False),
    ]
    vias = [v.strip() for v in path_via.split(",") if v.strip()]
    for via in vias:
        addrs.append(_encode_ax25_addr(via, is_last=False))
    # Set extension bit on last address
    last = bytearray(addrs[-1])
    last[-1] |= 0x01
    addrs[-1] = bytes(last)
    payload = b"".join(addrs) + bytes([0x03, 0xF0]) + info.encode("ascii", errors="replace")
    fcs = crc16_x25(payload)
    return payload + fcs.to_bytes(2, byteorder="little")


# ---------------------------------------------------------------------------
# AFSK encoder (vectorized)
# ---------------------------------------------------------------------------

def frame_to_bitstream(frame: bytes, preamble_flags: int = 120, trailing_flags: int = 12) -> list[int]:
    bits: list[int] = []
    for _ in range(max(8, preamble_flags)):
        bits.extend(_byte_lsb(0x7E))
    ones = 0
    for byte in frame:
        for bit in _byte_lsb(byte):
            bits.append(bit)
            if bit == 1:
                ones += 1
                if ones == 5:
                    bits.append(0)   # bit-stuffing
                    ones = 0
            else:
                ones = 0
    for _ in range(max(2, trailing_flags)):
        bits.extend(_byte_lsb(0x7E))
    return bits


def nrzi_encode(bits: list[int]) -> list[int]:
    level = 1
    out: list[int] = []
    for bit in bits:
        if bit == 0:
            level ^= 1
        out.append(level)
    return out


def afsk_from_nrzi(nrzi: list[int], sample_rate: int = 48000, tx_gain: float = 0.6) -> bytes:
    """Fully vectorized AFSK encoder (single np.sin call). Returns 16-bit PCM mono bytes."""
    if not nrzi:
        return b""

    MARK = 1200.0
    SPACE = 2200.0
    BAUD = 1200.0
    amp = float(np.clip(tx_gain, 0.05, 0.95)) * 32767.0
    sps = float(sample_rate) / BAUD
    two_pi = 2.0 * math.pi

    nrzi_arr = np.asarray(nrzi, dtype=np.int32)
    nbits = len(nrzi_arr)

    # Sample boundaries — same rounding as original for bit-accurate output
    bit_idx_f = np.arange(nbits, dtype=np.float64)
    bit_starts = np.round(bit_idx_f * sps).astype(np.int64)
    bit_ends = np.round((bit_idx_f + 1.0) * sps).astype(np.int64)
    sample_counts = np.maximum(1, bit_ends - bit_starts)   # samples per bit
    total_samples = int(bit_ends[-1])

    # Frequency per bit (MARK=1, SPACE=0)
    freqs = np.where(nrzi_arr == 1, MARK, SPACE)           # (nbits,)

    # Cumulative phase at the start of each bit (phase continuity)
    phase_advance = two_pi * freqs * sample_counts / sample_rate  # rad per bit
    initial_phases = np.empty(nbits, dtype=np.float64)
    initial_phases[0] = 0.0
    np.cumsum(phase_advance[:-1], out=initial_phases[1:])

    # Expand per-bit values to per-sample via np.repeat
    sample_initial_phases = np.repeat(initial_phases, sample_counts)  # (total_samples,)
    sample_freqs = np.repeat(freqs, sample_counts)                    # (total_samples,)
    bit_start_per_sample = np.repeat(bit_starts, sample_counts)       # (total_samples,)

    # Within-bit sample position [0, 1, ..., n-1] for each bit block
    within_bit = np.arange(total_samples, dtype=np.float64) - bit_start_per_sample

    # Single sin call over all samples
    phases = sample_initial_phases + two_pi * sample_freqs * within_bit / sample_rate
    out = np.sin(phases).astype(np.float32)

    # Envelope shaping (1 ms attack/release)
    attack = max(1, int(0.001 * sample_rate))
    release = attack
    if attack < total_samples:
        out[:attack] *= np.linspace(0.0, 1.0, attack, dtype=np.float32)
    if release < total_samples:
        out[-release:] *= np.linspace(1.0, 0.0, release, dtype=np.float32)

    pcm = np.clip(out * amp, -32767.0, 32767.0).astype(np.int16)
    return pcm.tobytes()


def write_aprs_wav(
    path,
    source: str,
    destination: str,
    message: str,
    path_via: str = "WIDE1-1",
    sample_rate: int = 48000,
    tx_gain: float = 0.6,
    preamble_flags: int = 120,
    trailing_flags: int = 12,
) -> None:
    from pathlib import Path
    p = Path(path)
    frame = build_ax25_ui_frame(source=source, destination=destination, path_via=path_via, info=message)
    bits = frame_to_bitstream(frame, preamble_flags=preamble_flags, trailing_flags=trailing_flags)
    nrzi = nrzi_encode(bits)
    pcm = afsk_from_nrzi(nrzi, sample_rate=sample_rate, tx_gain=tx_gain)
    _write_pcm16_mono(p, sample_rate, pcm)


def write_test_tone_wav(path, frequency_hz: float = 1200.0, seconds: float = 2.0, sample_rate: int = 48000) -> None:
    """Vectorized test tone generator."""
    from pathlib import Path
    p = Path(path)
    t = np.arange(int(sample_rate * seconds), dtype=np.float64)
    samples = (0.55 * 32767.0 * np.sin(2.0 * math.pi * frequency_hz * t / sample_rate))
    pcm = np.clip(samples, -32767.0, 32767.0).astype(np.int16)
    _write_pcm16_mono(p, sample_rate, pcm.tobytes())


# ---------------------------------------------------------------------------
# APRS payload builders
# ---------------------------------------------------------------------------

def build_aprs_message_payload(addressee: str, text: str, message_id: str = "") -> str:
    to_field = addressee.strip().upper()[:9].ljust(9)
    msg = text.strip()[:APRS_MESSAGE_TEXT_MAX]
    mid = message_id.strip()[:5]
    suffix = f"{{{mid}" if mid else ""
    return f":{to_field}:{msg}{suffix}"


def build_aprs_ack_payload(addressee: str, message_id: str) -> str:
    to_field = addressee.strip().upper()[:9].ljust(9)
    mid = message_id.strip()[:5]
    if not mid:
        raise ValueError("ACK message_id is required")
    return f":{to_field}:ack{mid}"


def build_aprs_position_payload(
    lat_deg: float,
    lon_deg: float,
    comment: str = "",
    symbol_table: str = "/",
    symbol: str = ">",
) -> str:
    if not -90.0 <= lat_deg <= 90.0:
        raise ValueError(f"Latitude out of range: {lat_deg}")
    if not -180.0 <= lon_deg <= 180.0:
        raise ValueError(f"Longitude out of range: {lon_deg}")
    lat = _format_lat(lat_deg)
    lon = _format_lon(lon_deg)
    cmt = comment.strip()[:APRS_POSITION_COMMENT_MAX]
    return f"!{lat}{symbol_table}{lon}{symbol}{cmt}"


def build_group_wire_text(group: str, body: str, part: Optional[int] = None, total: Optional[int] = None) -> str:
    g = group.strip().upper()
    if not g or len(g) > 16 or not re.fullmatch(r"[A-Z0-9_-]+", g):
        raise ValueError("Group name must match [A-Z0-9_-]{1,16}")
    # Calculate prefix overhead so body fits inside the APRS message body limit
    if part is None or total is None:
        prefix = f"@GRP/{g}:"
        max_body = APRS_MESSAGE_BODY_MAX - len(prefix)
        payload = body.strip()[:max(1, max_body)]
        return f"{prefix}{payload}"
    if part < 1 or total < 1 or part > total or total > 99:
        raise ValueError("Invalid group chunk numbering")
    prefix = f"@GRP/{g}/{part}/{total}:"
    max_body = APRS_MESSAGE_BODY_MAX - len(prefix)
    payload = body.strip()[:max(1, max_body)]
    return f"{prefix}{payload}"


def build_intro_wire_text(callsign: str, lat: float, lon: float, note: str = "") -> str:
    call = callsign.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,6}(?:-[0-9]{1,2})?", call):
        raise ValueError("Intro callsign must match AX.25 callsign format")
    if not -90.0 <= lat <= 90.0:
        raise ValueError("Latitude out of range")
    if not -180.0 <= lon <= 180.0:
        raise ValueError("Longitude out of range")
    return f"@INTRO/{call}/{lat:.5f}/{lon:.5f}:{note.strip()}"


# ---------------------------------------------------------------------------
# Group / intro text chunker (accounts for prefix overhead)
# ---------------------------------------------------------------------------

def split_text_for_group(text: str, group: str) -> list[str]:
    """Split text into chunks that fit inside group wire payloads."""
    g = group.strip().upper()
    # Worst-case prefix for a chunked multi-part message: @GRP/GGGGGGGGGGGGGGGG/99/99:
    prefix_max = len(f"@GRP/{g}/99/99:")
    chunk_size = max(1, APRS_MESSAGE_BODY_MAX - prefix_max)
    return _split_chunks(text.strip(), chunk_size)


def split_aprs_text_chunks(text: str, max_len: int = APRS_MESSAGE_TEXT_MAX) -> list[str]:
    """Split plain text into chunks for direct messaging."""
    return _split_chunks(text.strip(), max(1, int(max_len)))


def _split_chunks(body: str, limit: int) -> list[str]:
    if not body:
        return []
    if len(body) <= limit:
        return [body]
    chunks: list[str] = []
    remaining = body
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind(" ", 0, limit + 1)
        if cut < max(8, int(limit * 0.45)):
            cut = limit
        chunk = remaining[:cut].rstrip() or remaining[:limit]
        chunks.append(chunk)
        remaining = remaining[len(chunk):].lstrip()
    return chunks


# ---------------------------------------------------------------------------
# APRS payload parsers
# ---------------------------------------------------------------------------

def parse_aprs_message_info(info: str) -> Optional[tuple[str, str, Optional[str]]]:
    """Return (addressee, text, msg_id_or_None) or None."""
    if not info.startswith(":") or len(info) < 12:
        return None
    try:
        addressee = info[1:10].strip().upper()
        if info[10] != ":":
            return None
        body = info[11:]
        msg_id: Optional[str] = None
        if "{" in body:
            text, tail = body.rsplit("{", 1)
            msg_id = tail.strip()[:5] or None
        else:
            text = body
        return addressee, text.strip(), msg_id
    except Exception:
        return None


def parse_aprs_position_info(
    info: str, destination: str = ""
) -> Optional[tuple[float, float, str]]:
    """Return (lat, lon, comment) for uncompressed, compressed, and Mic-E APRS positions."""
    if not info:
        return None
    dti = info[0]

    # --- Uncompressed (existing format: DDMMssH/DDDMMssH) ---
    if dti in ("!", "=", "/", "@"):
        payload = info[8:] if dti in ("/", "@") else info[1:]
        if len(payload) >= 19:
            lat = _parse_aprs_lat(payload[0:8])
            lon = _parse_aprs_lon(payload[9:18])
            if lat is not None and lon is not None:
                comment = payload[19:] if len(payload) > 19 else ""
                return lat, lon, comment

        # --- Compressed (base-91, 13 chars after DTI) ---
        if len(payload) >= 10:
            result = _parse_compressed_position(payload)
            if result is not None:
                return result

    # --- Mic-E (DTI is ` or ') ---
    if dti in ("`", "'") and destination:
        return _parse_mice_position(destination, info)

    return None


def _parse_compressed_position(payload: str) -> Optional[tuple[float, float, str]]:
    """Parse base-91 compressed APRS position from the payload (after DTI/timestamp)."""
    if len(payload) < 10:
        return None
    # Validate: chars 1-8 must be printable base-91 (ASCII 33-123)
    for ch in payload[1:9]:
        if not (33 <= ord(ch) <= 123):
            return None
    try:
        # payload[0] = symbol table, [1:5] = lat (4 b91 chars), [5:9] = lon, [9] = symbol
        lat_v = sum((ord(payload[i + 1]) - 33) * (91 ** (3 - i)) for i in range(4))
        lon_v = sum((ord(payload[i + 5]) - 33) * (91 ** (3 - i)) for i in range(4))
        lat = 90.0 - lat_v / 380926.0
        lon = -180.0 + lon_v / 190463.0
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            return None
        comment = payload[10:] if len(payload) > 10 else ""
        return lat, lon, comment
    except Exception:
        return None


def _mic_e_digit_flag(c: str) -> tuple[int, bool]:
    """Return (digit, flag) for a Mic-E destination character."""
    v = ord(c)
    if 48 <= v <= 57: return v - 48, False   # '0'-'9'
    if 65 <= v <= 74: return v - 65, False   # 'A'-'J' (deprecated)
    if 80 <= v <= 89: return v - 80, True    # 'P'-'Y' (flag bit set)
    return 0, False                           # 'K','L','Z', other


def _parse_mice_position(dest: str, info: str) -> Optional[tuple[float, float, str]]:
    """Decode Mic-E position from destination address + info field."""
    if len(dest) < 6 or len(info) < 8:
        return None
    try:
        d = dest[:6]
        d1, _ = _mic_e_digit_flag(d[0])
        d2, _ = _mic_e_digit_flag(d[1])
        d3, _ = _mic_e_digit_flag(d[2])
        d4, south = _mic_e_digit_flag(d[3])
        d5, lon_offset = _mic_e_digit_flag(d[4])
        d6, west = _mic_e_digit_flag(d[5])

        lat_deg = d1 * 10 + d2
        lat_min = d3 * 10 + d4 + (d5 * 10 + d6) / 100.0
        lat = lat_deg + lat_min / 60.0
        if south:
            lat = -lat

        lon_d = ord(info[1]) - 28
        lon_m = ord(info[2]) - 28
        lon_h = ord(info[3]) - 28
        if lon_offset:
            lon_d += 100
        if 180 <= lon_d <= 189:
            lon_d -= 80
        if lon_m >= 60:
            lon_m -= 60
        lon = lon_d + lon_m / 60.0 + lon_h / 6000.0
        if west:
            lon = -lon

        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            return None
        comment = info[8:].strip() if len(info) > 8 else ""
        return lat, lon, comment
    except Exception:
        return None


def parse_group_wire_text(text: str) -> Optional[tuple[str, str, Optional[int], Optional[int]]]:
    m = GROUP_WIRE_RE.match(text.strip())
    if not m:
        return None
    group = m.group(1).upper()
    part = int(m.group(2)) if m.group(2) else None
    total = int(m.group(3)) if m.group(3) else None
    body = m.group(4).strip()
    return group, body, part, total


def parse_intro_wire_text(text: str) -> Optional[tuple[str, float, float, str]]:
    m = INTRO_WIRE_RE.match(text.strip())
    if not m:
        return None
    call = m.group(1).upper()
    lat = float(m.group(2))
    lon = float(m.group(3))
    note = m.group(4).strip()
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    return call, lat, lon, note


# ---------------------------------------------------------------------------
# AX.25 decoder
# ---------------------------------------------------------------------------

def decode_ax25_from_wav(path: str) -> list[DecodedPacket]:
    rate, mono = _read_wav_mono(path)
    return decode_ax25_from_samples(rate, mono)


def decode_ax25_from_samples(rate: int, mono: np.ndarray) -> list[DecodedPacket]:
    if len(mono) < 200:
        return []

    cleaned = _preprocess_samples(mono, rate)
    sps_nom = rate / 1200.0
    # Timing drift candidates (±3.6% in 1.2% steps)
    sps_candidates = [sps_nom * (1.0 + d) for d in (-0.036, -0.024, -0.012, 0.0, 0.012, 0.024, 0.036)]

    # Primary Bell 202 + interoperability fallbacks
    tone_pairs = (
        (1200.0, 2200.0),   # Standard Bell 202 APRS
        (1600.0, 1800.0),   # narrow-separation fallback
        (1200.0, 2400.0),   # wider-separation fallback
    )

    merged: dict[str, DecodedPacket] = {}
    for mark_hz, space_hz in tone_pairs:
        demod = _afsk_discriminator(cleaned, rate, mark_hz=mark_hz, space_hz=space_hz)
        if len(demod) < 200:
            continue
        for invert in (False, True):
            for sps in sps_candidates:
                max_off = max(1, int(round(sps)))
                for offset in range(max_off):
                    levels = _extract_nrzi_levels(demod, sps, offset, invert_tones=invert)
                    if len(levels) < 32:
                        continue
                    bits = _nrzi_to_bits(levels)
                    for frame in _extract_hdlc_frames(bits):
                        pkt = _decode_ax25_frame(frame)
                        if pkt and pkt.text not in merged:
                            merged[pkt.text] = pkt
    return list(merged.values())


# ---------------------------------------------------------------------------
# CRC (single definition — audio_tools imports from here)
# ---------------------------------------------------------------------------

def _build_crc16_table() -> tuple:
    table = []
    for i in range(256):
        v = i
        for _ in range(8):
            if v & 1:
                v = (v >> 1) ^ 0x8408
            else:
                v >>= 1
        table.append(v)
    return tuple(table)


_CRC16_TABLE: tuple = _build_crc16_table()


def crc16_x25(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc = (crc >> 8) ^ _CRC16_TABLE[(crc ^ byte) & 0xFF]
    return (~crc) & 0xFFFF


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_pcm16_mono(path, sample_rate: int, data: bytes) -> None:
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(data)


def _read_wav_mono(path: str) -> tuple[int, np.ndarray]:
    with wave.open(path, "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("Only 16-bit PCM WAV is supported")
    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels)[:, 0]
    return rate, data


def _byte_lsb(value: int) -> list[int]:
    return [(value >> i) & 1 for i in range(8)]


def _encode_ax25_addr(value: str, is_last: bool) -> bytes:
    token = value.upper().strip()
    if "-" in token:
        call, ssid_raw = token.split("-", 1)
        ssid = int(ssid_raw)
    else:
        call, ssid = token, 0
    call = (call[:6]).ljust(6)
    out = bytearray((ord(ch) << 1) & 0xFE for ch in call)
    ssid_byte = 0x60 | ((ssid & 0x0F) << 1)
    if is_last:
        ssid_byte |= 0x01
    out.append(ssid_byte)
    return bytes(out)


def _decode_addr(adr: bytes) -> str:
    call = "".join(chr((b >> 1) & 0x7F) for b in adr[:6]).strip()
    ssid = (adr[6] >> 1) & 0x0F
    return f"{call}-{ssid}" if ssid else call


def _format_lat(lat: float) -> str:
    hemi = "N" if lat >= 0 else "S"
    a = abs(lat)
    deg = int(a)
    mins = (a - deg) * 60.0
    return f"{deg:02d}{mins:05.2f}{hemi}"


def _format_lon(lon: float) -> str:
    hemi = "E" if lon >= 0 else "W"
    a = abs(lon)
    deg = int(a)
    mins = (a - deg) * 60.0
    return f"{deg:03d}{mins:05.2f}{hemi}"


def _parse_aprs_lat(token: str) -> Optional[float]:
    if len(token) != 8:
        return None
    try:
        deg = int(token[0:2])
        mins = float(token[2:7])
        hemi = token[7].upper()
        if hemi not in ("N", "S"):
            return None
        val = float(deg) + (mins / 60.0)
        return val if hemi == "N" else -val
    except Exception:
        return None


def _parse_aprs_lon(token: str) -> Optional[float]:
    if len(token) != 9:
        return None
    try:
        deg = int(token[0:3])
        mins = float(token[3:8])
        hemi = token[8].upper()
        if hemi not in ("E", "W"):
            return None
        val = float(deg) + (mins / 60.0)
        return val if hemi == "E" else -val
    except Exception:
        return None


# --- DSP helpers ---

@functools.lru_cache(maxsize=16)
def _lowpass_kernel(rate: int, cutoff_hz: float, taps: int = 81) -> np.ndarray:
    if taps % 2 == 0:
        taps += 1
    fc = float(cutoff_hz) / float(rate)
    n = np.arange(taps, dtype=np.float64) - (taps - 1) / 2.0
    h = 2.0 * fc * np.sinc(2.0 * fc * n)
    h *= np.hamming(taps)
    s = float(np.sum(h))
    if abs(s) < 1e-12:
        return h.astype(np.float32)
    return (h / s).astype(np.float32)


def _preprocess_samples(samples: np.ndarray, rate: int) -> np.ndarray:
    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(x) == 0:
        return x
    x = x - float(np.mean(x))
    if len(x) >= 256:
        lp_lo = _convolve(x, _lowpass_kernel(rate, 700.0, 101))
        x = x - lp_lo.astype(np.float32, copy=False)
        x = _convolve(x, _lowpass_kernel(rate, 2600.0, 101)).astype(np.float32, copy=False)
    # RMS AGC: normalize to -12 dBFS target (0.25 linear), then clip impulsive noise
    rms = float(np.sqrt(np.mean(x * x)))
    if rms > 1e-6:
        x = np.clip(x * (0.25 / rms), -1.0, 1.0)
    x = np.tanh(2.2 * x) / math.tanh(2.2)
    return x.astype(np.float32, copy=False)


def _afsk_discriminator(samples: np.ndarray, rate: int, mark_hz: float = 1200.0, space_hz: float = 2200.0) -> np.ndarray:
    if len(samples) < 128:
        return np.array([], dtype=np.float32)
    n = np.arange(len(samples), dtype=np.float64)
    w_mark = 2.0 * math.pi * mark_hz / rate
    w_space = 2.0 * math.pi * space_hz / rate
    s64 = samples.astype(np.float64)
    mark_mix = s64 * np.exp(-1j * w_mark * n)
    space_mix = s64 * np.exp(-1j * w_space * n)
    lpf = _lowpass_kernel(rate, 800.0, 81).astype(np.float64)
    mark_bb = _convolve(mark_mix, lpf)
    space_bb = _convolve(space_mix, lpf)
    demod = (np.abs(mark_bb) ** 2) - (np.abs(space_bb) ** 2)
    demod -= np.mean(demod)
    std = float(np.std(demod))
    if std > 1e-9:
        demod /= std
    return demod.astype(np.float32, copy=False)


def _extract_nrzi_levels(demod: np.ndarray, spb: float, offset: int, invert_tones: bool = False) -> list[int]:
    count = int((len(demod) - offset - 1) / spb)
    if count <= 0:
        return []
    idx = np.rint(offset + np.arange(count, dtype=np.float64) * spb).astype(np.int64)
    idx = idx[(idx >= 0) & (idx < len(demod))]
    levels = (demod[idx] >= 0.0).astype(np.int8)
    if invert_tones:
        levels = 1 - levels
    return levels.tolist()


def _nrzi_to_bits(levels: list[int]) -> list[int]:
    if not levels:
        return []
    arr = np.asarray(levels, dtype=np.int8)
    bits = np.empty(len(arr), dtype=np.int8)
    bits[0] = 1
    bits[1:] = (arr[1:] == arr[:-1]).astype(np.int8)
    return bits.tolist()


_FLAG_ARR = np.array(FLAG_BITS, dtype=np.int8)


def _extract_hdlc_frames(bits: list[int]) -> list[bytes]:
    frames: list[bytes] = []
    if len(bits) < 24:
        return frames
    arr = np.asarray(bits, dtype=np.int8)
    # Vectorized sliding-window flag search (numpy >= 1.20)
    windows = np.lib.stride_tricks.sliding_window_view(arr, 8)
    flag_positions: list[int] = np.where(np.all(windows == _FLAG_ARR, axis=1))[0].tolist()
    if len(flag_positions) < 2:
        return frames
    for i in range(len(flag_positions) - 1):
        start = flag_positions[i] + 8
        end = flag_positions[i + 1]
        if end - start < 136:  # 17 bytes minimum → skip preamble runs & undersized segments
            continue
        frame_bits = _remove_bit_stuffing(bits[start:end])
        if frame_bits is None:
            continue
        frame = _bits_to_bytes_lsb(frame_bits)
        if len(frame) >= 17:
            frames.append(frame)
    return frames


def _remove_bit_stuffing(bits: list[int]) -> Optional[list[int]]:
    out: list[int] = []
    ones = 0
    i = 0
    while i < len(bits):
        b = bits[i]
        if b == 1:
            ones += 1
            if ones >= 6:
                return None
            out.append(1)
        else:
            if ones == 5:
                ones = 0
                i += 1
                continue
            ones = 0
            out.append(0)
        i += 1
    return out


_LSB_WEIGHTS = np.array([1, 2, 4, 8, 16, 32, 64, 128], dtype=np.uint16)


def _bits_to_bytes_lsb(bits: list[int]) -> bytes:
    n = len(bits) - (len(bits) % 8)
    if n == 0:
        return b""
    arr = np.asarray(bits[:n], dtype=np.uint16).reshape(-1, 8)
    return (arr @ _LSB_WEIGHTS).astype(np.uint8).tobytes()


def _decode_ax25_frame(frame: bytes) -> Optional[DecodedPacket]:
    if len(frame) < 17:
        return None
    body = frame[:-2]
    rx_fcs = int.from_bytes(frame[-2:], byteorder="little")
    if crc16_x25(body) != rx_fcs:
        return None
    idx = 0
    addrs: list[str] = []
    while True:
        if idx + 7 > len(body):
            return None
        adr = body[idx:idx + 7]
        addrs.append(_decode_addr(adr))
        idx += 7
        if adr[6] & 0x01:
            break
    if len(addrs) < 2 or idx + 2 > len(body):
        return None
    ctrl = body[idx]
    pid = body[idx + 1]
    if ctrl != 0x03 or pid != 0xF0:
        return None
    info = body[idx + 2:].decode("ascii", errors="replace")
    src = addrs[1]
    dst = addrs[0]
    path = addrs[2:] if len(addrs) > 2 else []
    path_part = f",{','.join(path)}" if path else ""
    text = f"{src}>{dst}{path_part}:{info}"
    return DecodedPacket(source=src, destination=dst, path=path, info=info, text=text)
