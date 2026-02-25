#!/usr/bin/env python3
"""APRS payload helpers and basic AX.25/APRS AFSK decoder."""

from __future__ import annotations

import math
import re
import wave
from dataclasses import dataclass

import numpy as np


FLAG_BITS = [0, 1, 1, 1, 1, 1, 1, 0]  # 0x7E, LSB-first
APRS_MESSAGE_TEXT_MAX = 67
GROUP_WIRE_RE = re.compile(r"^@GRP/([A-Z0-9_-]{1,16})(?:/([0-9]{1,2})/([0-9]{1,2}))?:(.*)$", flags=re.IGNORECASE)
INTRO_WIRE_RE = re.compile(
    r"^@INTRO/([A-Z0-9]{1,6}(?:-[0-9]{1,2})?)/(-?[0-9]{1,2}(?:\.[0-9]+)?)/(-?[0-9]{1,3}(?:\.[0-9]+)?):?(.*)$",
    flags=re.IGNORECASE,
)


@dataclass
class DecodedPacket:
    source: str
    destination: str
    path: list[str]
    info: str
    text: str


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


def parse_aprs_message_info(info: str) -> tuple[str, str, str | None] | None:
    """
    Parse APRS message payload.

    Returns:
      (addressee, text, message_id_or_none) or None if not message format.
    """
    if not info.startswith(":") or len(info) < 12:
        return None
    try:
        addressee = info[1:10].strip().upper()
        if info[10] != ":":
            return None
        body = info[11:]
        msg_id: str | None = None
        if "{" in body:
            text, tail = body.rsplit("{", 1)
            msg_id = tail.strip()[:5] or None
        else:
            text = body
        return addressee, text.strip(), msg_id
    except Exception:  # noqa: BLE001
        return None


def split_aprs_text_chunks(text: str, max_len: int = APRS_MESSAGE_TEXT_MAX) -> list[str]:
    body = text.strip()
    if not body:
        return []
    limit = max(1, int(max_len))
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
        chunk = remaining[:cut].rstrip()
        if not chunk:
            chunk = remaining[:limit]
        chunks.append(chunk)
        remaining = remaining[len(chunk):].lstrip()
    return chunks


def build_group_wire_text(group: str, body: str, part: int | None = None, total: int | None = None) -> str:
    g = group.strip().upper()
    if not g or len(g) > 16 or not re.fullmatch(r"[A-Z0-9_-]+", g):
        raise ValueError("Group name must match [A-Z0-9_-]{1,16}")
    payload = body.strip()
    if part is None or total is None:
        return f"@GRP/{g}:{payload}"
    if part < 1 or total < 1 or part > total or total > 99:
        raise ValueError("Invalid group chunk numbering")
    return f"@GRP/{g}/{part}/{total}:{payload}"


def parse_group_wire_text(text: str) -> tuple[str, str, int | None, int | None] | None:
    m = GROUP_WIRE_RE.match(text.strip())
    if not m:
        return None
    group = m.group(1).upper()
    part = int(m.group(2)) if m.group(2) else None
    total = int(m.group(3)) if m.group(3) else None
    body = m.group(4).strip()
    return group, body, part, total


def build_intro_wire_text(callsign: str, lat: float, lon: float, note: str = "") -> str:
    call = callsign.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,6}(?:-[0-9]{1,2})?", call):
        raise ValueError("Intro callsign must match AX.25 callsign format")
    if lat < -90.0 or lat > 90.0:
        raise ValueError("Latitude out of range")
    if lon < -180.0 or lon > 180.0:
        raise ValueError("Longitude out of range")
    body = note.strip()
    return f"@INTRO/{call}/{lat:.5f}/{lon:.5f}:{body}"


def parse_intro_wire_text(text: str) -> tuple[str, float, float, str] | None:
    m = INTRO_WIRE_RE.match(text.strip())
    if not m:
        return None
    call = m.group(1).upper()
    lat = float(m.group(2))
    lon = float(m.group(3))
    note = m.group(4).strip()
    if lat < -90.0 or lat > 90.0 or lon < -180.0 or lon > 180.0:
        return None
    return call, lat, lon, note


def parse_aprs_position_info(info: str) -> tuple[float, float, str] | None:
    """
    Parse APRS position payload (common uncompressed variants).

    Supported data types:
      ! or =  : no timestamp
      / or @  : timestamped (DDHHMMz/h or HHMMSSh)

    Returns:
      (lat_deg, lon_deg, comment) or None when parsing is not possible.
    """
    if not info:
        return None
    dti = info[0]
    if dti not in ("!", "=", "/", "@"):
        return None

    payload = info
    if dti in ("/", "@"):
        # Skip timestamp (7 chars after DTI), if present.
        if len(info) < 8:
            return None
        payload = info[8:]
    else:
        payload = info[1:]

    # Uncompressed position: DDMM.hhN/DDDMM.hhW[symbol][comment...]
    # We decode only standard numeric lat/lon packets.
    if len(payload) < 19:
        return None

    lat_s = payload[0:8]
    lon_s = payload[9:18]
    comment = payload[19:] if len(payload) > 19 else ""

    lat = _parse_aprs_lat(lat_s)
    lon = _parse_aprs_lon(lon_s)
    if lat is None or lon is None:
        return None
    return lat, lon, comment


def build_aprs_position_payload(
    lat_deg: float,
    lon_deg: float,
    comment: str = "",
    symbol_table: str = "/",
    symbol: str = ">",
) -> str:
    lat = _format_lat(lat_deg)
    lon = _format_lon(lon_deg)
    return f"!{lat}{symbol_table}{lon}{symbol}{comment[:40]}"


def decode_ax25_from_wav(path: str) -> list[DecodedPacket]:
    rate, mono = _read_wav_mono(path)
    return decode_ax25_from_samples(rate, mono)


def decode_ax25_from_samples(rate: int, mono: np.ndarray) -> list[DecodedPacket]:
    if len(mono) < 200:
        return []

    cleaned = _preprocess_samples(mono, rate)
    samples_per_bit = rate / 1200.0
    # Widen timing drift tolerance for interoperability with radios/modems that
    # run slightly off nominal 1200 baud.
    spp_candidates = [samples_per_bit * (1.0 + d) for d in (-0.036, -0.024, -0.012, 0.0, 0.012, 0.024, 0.036)]
    merged_packets: dict[str, DecodedPacket] = {}
    # Primary Bell 202 plus conservative fallbacks for radios/modems that skew tones.
    tone_pairs = (
        (1200.0, 2200.0),  # Bell 202 APRS
        (1600.0, 1800.0),  # narrow-separation fallback
        (1200.0, 2400.0),  # wider-separation fallback
    )
    for mark_hz, space_hz in tone_pairs:
        demod = _afsk_discriminator(cleaned, rate, mark_hz=mark_hz, space_hz=space_hz)
        if len(demod) < 200:
            continue
        # Try both tone orientations because some audio chains can appear inverted.
        for invert_tones in (False, True):
            for spp in spp_candidates:
                max_off = max(1, int(round(spp)))
                for offset in range(max_off):
                    levels = _extract_nrzi_levels(demod, spp, offset, invert_tones=invert_tones)
                    if len(levels) < 32:
                        continue
                    bits = _nrzi_to_bits(levels)
                    frames = _extract_hdlc_frames(bits)
                    for frame in frames:
                        decoded = _decode_ax25_frame(frame)
                        if not decoded:
                            continue
                        merged_packets[decoded.text] = decoded
    return list(merged_packets.values())


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


def _preprocess_samples(samples: np.ndarray, rate: int) -> np.ndarray:
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim != 1:
        x = x.reshape(-1)
    if len(x) == 0:
        return x
    x = x - float(np.mean(x))
    # Band-limit around Bell 202 AFSK region to reject strong CTCSS hum and HF hiss.
    if len(x) >= 256:
        # Remove low-frequency content (sub-audio/voice rumble) with a simple FIR HP.
        lp_lo = np.convolve(x, _lowpass_kernel(rate, cutoff_hz=700.0, taps=101), mode="same")
        x = x - lp_lo.astype(np.float32, copy=False)
        # Remove out-of-band high-frequency content.
        x = np.convolve(x, _lowpass_kernel(rate, cutoff_hz=2600.0, taps=101), mode="same").astype(np.float32, copy=False)
    peak = float(np.max(np.abs(x)))
    if peak > 1e-6:
        x = x / peak
    # Light soft-limiter helps with soundcard clipping without crushing weaker frames.
    x = np.tanh(2.2 * x) / math.tanh(2.2)
    return x.astype(np.float32, copy=False)


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


def _afsk_discriminator(samples: np.ndarray, rate: int, mark_hz: float = 1200.0, space_hz: float = 2200.0) -> np.ndarray:
    if len(samples) < 128:
        return np.array([], dtype=np.float32)

    n = np.arange(len(samples), dtype=np.float64)
    w_mark = 2.0 * math.pi * float(mark_hz) / float(rate)
    w_space = 2.0 * math.pi * float(space_hz) / float(rate)
    mark_mix = samples.astype(np.float64) * np.exp(-1j * w_mark * n)
    space_mix = samples.astype(np.float64) * np.exp(-1j * w_space * n)

    lpf = _lowpass_kernel(rate, cutoff_hz=800.0, taps=81).astype(np.float64)
    mark_bb = np.convolve(mark_mix, lpf, mode="same")
    space_bb = np.convolve(space_mix, lpf, mode="same")
    demod = (np.abs(mark_bb) ** 2) - (np.abs(space_bb) ** 2)

    demod = demod - np.mean(demod)
    std = float(np.std(demod))
    if std > 1e-9:
        demod = demod / std
    return demod.astype(np.float32, copy=False)


def _extract_nrzi_levels(demod: np.ndarray, spb: float, offset: int, invert_tones: bool = False) -> list[int]:
    count = int((len(demod) - offset - 1) / spb)
    if count <= 0:
        return []
    idx = np.rint(offset + (np.arange(count, dtype=np.float64) * spb)).astype(np.int64)
    idx = idx[(idx >= 0) & (idx < len(demod))]
    levels = (demod[idx] >= 0.0).astype(np.int8)
    if invert_tones:
        levels = 1 - levels
    return levels.tolist()


def _nrzi_to_bits(levels: list[int]) -> list[int]:
    bits: list[int] = []
    if not levels:
        return bits
    prev = levels[0]
    bits.append(1)  # first symbol fallback
    for lv in levels[1:]:
        bits.append(1 if lv == prev else 0)
        prev = lv
    return bits


def _extract_hdlc_frames(bits: list[int]) -> list[bytes]:
    frames: list[bytes] = []
    if len(bits) < 24:
        return frames

    flags: list[int] = []
    for i in range(0, len(bits) - 7):
        if bits[i:i + 8] == FLAG_BITS:
            flags.append(i)
    if len(flags) < 2:
        return frames

    for i in range(len(flags) - 1):
        start = flags[i] + 8
        end = flags[i + 1]
        if end <= start:
            continue
        payload_bits = bits[start:end]
        frame_bits = _remove_bit_stuffing(payload_bits)
        if frame_bits is None:
            continue
        frame = _bits_to_bytes_lsb(frame_bits)
        if len(frame) >= 17:
            frames.append(frame)
    return frames


def _remove_bit_stuffing(bits: list[int]) -> list[int] | None:
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
                # Stuffed zero after five ones; drop it.
                ones = 0
                i += 1
                continue
            ones = 0
            out.append(0)
        i += 1
    return out


def _bits_to_bytes_lsb(bits: list[int]) -> bytes:
    n = len(bits) - (len(bits) % 8)
    out = bytearray()
    for i in range(0, n, 8):
        b = 0
        for j in range(8):
            b |= (bits[i + j] & 1) << j
        out.append(b)
    return bytes(out)


def _decode_ax25_frame(frame: bytes) -> DecodedPacket | None:
    if len(frame) < 17:
        return None
    body = frame[:-2]
    rx_fcs = int.from_bytes(frame[-2:], byteorder="little")
    if _crc16_x25(body) != rx_fcs:
        return None

    idx = 0
    addrs: list[str] = []
    while True:
        if idx + 7 > len(body):
            return None
        adr = body[idx:idx + 7]
        addrs.append(_decode_addr(adr))
        ext = adr[6] & 0x01
        idx += 7
        if ext:
            break
    if len(addrs) < 2:
        return None
    if idx + 2 > len(body):
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


def _decode_addr(adr: bytes) -> str:
    call = "".join(chr((b >> 1) & 0x7F) for b in adr[:6]).strip()
    ssid = (adr[6] >> 1) & 0x0F
    return f"{call}-{ssid}" if ssid else call


def _crc16_x25(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return (~crc) & 0xFFFF


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


def _parse_aprs_lat(token: str) -> float | None:
    # DDMM.hhN
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
    except Exception:  # noqa: BLE001
        return None


def _parse_aprs_lon(token: str) -> float | None:
    # DDDMM.hhE
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
    except Exception:  # noqa: BLE001
        return None
