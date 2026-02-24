#!/usr/bin/env python3
"""Audio generation and playback helpers for test tone and APRS AFSK."""

from __future__ import annotations

import math
import wave
from pathlib import Path

try:
    import winsound
except ImportError:  # pragma: no cover - non-Windows fallback
    winsound = None

try:
    import numpy as np
    import sounddevice as sd
except ImportError:  # pragma: no cover - optional dependency
    np = None
    sd = None


def list_output_devices() -> list[tuple[int, str]]:
    """Return available output devices as (index, name)."""
    if sd is None:
        return []
    hostapis = sd.query_hostapis()
    devices = sd.query_devices()
    ranked: list[tuple[int, int, str, str]] = []
    for idx, dev in enumerate(devices):
        if dev.get("max_output_channels", 0) > 0:
            hostapi_idx = int(dev.get("hostapi", 0))
            hostapi_name = str(hostapis[hostapi_idx].get("name", "Unknown")) if hostapi_idx < len(hostapis) else "Unknown"
            # Exclude DirectSound duplicate paths; favor endpoint-style APIs.
            if hostapi_name == "Windows DirectSound":
                continue
            name = str(dev.get("name", f"Device {idx}"))
            if hostapi_name == "Windows WASAPI":
                rank = 0
            elif hostapi_name == "MME":
                rank = 1
            elif "Windows WDM-KS" in hostapi_name:
                rank = 2
            else:
                rank = 3
            ranked.append((rank, idx, name, hostapi_name))
    ranked.sort(key=lambda x: (x[0], x[1]))

    # Keep one entry per device name, preferring WASAPI then MME.
    chosen: dict[str, tuple[int, int, str, str]] = {}
    for item in ranked:
        key = item[2].strip().lower()
        if key not in chosen:
            chosen[key] = item
    out = list(chosen.values())
    if out:
        # Prefer WASAPI first; fallback to MME only when WASAPI is unavailable.
        wasapi = [x for x in out if x[0] == 0]
        if wasapi:
            out = wasapi
        else:
            preferred = [x for x in out if x[0] <= 1]
            if preferred:
                out = preferred
    out = [x for x in out if "sound mapper" not in x[2].strip().lower()]
    out.sort(key=lambda x: x[2].lower())
    return [(idx, name) for _, idx, name, _ in out]


def list_input_devices() -> list[tuple[int, str]]:
    """Return available input devices as (index, name)."""
    if sd is None:
        return []
    hostapis = sd.query_hostapis()
    devices = sd.query_devices()
    ranked: list[tuple[int, int, str, str]] = []
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            hostapi_idx = int(dev.get("hostapi", 0))
            hostapi_name = str(hostapis[hostapi_idx].get("name", "Unknown")) if hostapi_idx < len(hostapis) else "Unknown"
            if hostapi_name == "Windows DirectSound":
                continue
            name = str(dev.get("name", f"Device {idx}"))
            if hostapi_name == "Windows WASAPI":
                rank = 0
            elif hostapi_name == "MME":
                rank = 1
            elif "Windows WDM-KS" in hostapi_name:
                rank = 2
            else:
                rank = 3
            ranked.append((rank, idx, name, hostapi_name))
    ranked.sort(key=lambda x: (x[0], x[1]))

    chosen: dict[str, tuple[int, int, str, str]] = {}
    for item in ranked:
        key = item[2].strip().lower()
        if key not in chosen:
            chosen[key] = item
    out = list(chosen.values())
    if out:
        wasapi = [x for x in out if x[0] == 0]
        if wasapi:
            out = wasapi
        else:
            preferred = [x for x in out if x[0] <= 1]
            if preferred:
                out = preferred
    out = [x for x in out if "sound mapper" not in x[2].strip().lower()]
    out.sort(key=lambda x: x[2].lower())
    return [(idx, name) for _, idx, name, _ in out]


def play_wav(path: Path, device_index: int | None = None) -> None:
    """
    Play WAV via sounddevice when available (supports explicit output device).
    Fallback to winsound default output when sounddevice isn't available.
    """
    if sd is not None and np is not None:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.getnframes()
            raw = wav.readframes(frames)

        if width != 2:
            raise RuntimeError("Only 16-bit PCM WAV is supported")

        data = np.frombuffer(raw, dtype=np.int16)
        if channels > 1:
            data = data.reshape(-1, channels)

        sd.stop()
        sd.play(data, samplerate=rate, device=device_index, blocking=False)
        return

    if winsound is None:
        raise RuntimeError("No audio playback backend available. Install sounddevice or use Windows winsound.")
    flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    winsound.PlaySound(str(path), flags)


def play_wav_blocking(path: Path, device_index: int | None = None) -> None:
    """
    Play WAV and block until playback completes.
    """
    if sd is not None and np is not None:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.getnframes()
            raw = wav.readframes(frames)

        if width != 2:
            raise RuntimeError("Only 16-bit PCM WAV is supported")

        data = np.frombuffer(raw, dtype=np.int16)
        if channels > 1:
            data = data.reshape(-1, channels)

        sd.stop()
        sd.play(data, samplerate=rate, device=device_index, blocking=True)
        return

    if winsound is None:
        raise RuntimeError("No audio playback backend available. Install sounddevice or use Windows winsound.")
    flags = winsound.SND_FILENAME | winsound.SND_SYNC | winsound.SND_NODEFAULT
    winsound.PlaySound(str(path), flags)


def play_wav_blocking_compatible(path: Path, device_index: int) -> None:
    """
    Play WAV on a selected device using a conservative, device-compatible path.
    - Converts source to mono.
    - Resamples to the device default sample rate.
    - Tries mono first, then falls back to multichannel with signal on channel 0.
    """
    if sd is None or np is None:
        raise RuntimeError("sounddevice/numpy are required for compatible playback")
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        src_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise RuntimeError("Only 16-bit PCM WAV is supported")

    mono = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        mono = mono.reshape(-1, channels)[:, 0]
    mono_f = mono.astype(np.float32) / 32768.0

    info = sd.query_devices(device_index)
    dst_rate = int(round(float(info.get("default_samplerate", src_rate))))
    if dst_rate <= 0:
        dst_rate = int(src_rate)
    if dst_rate != src_rate and len(mono_f) > 1:
        src_n = len(mono_f)
        dst_n = max(1, int(round(src_n * (float(dst_rate) / float(src_rate)))))
        xp = np.linspace(0.0, 1.0, src_n, endpoint=False)
        xq = np.linspace(0.0, 1.0, dst_n, endpoint=False)
        mono_f = np.interp(xq, xp, mono_f).astype(np.float32)

    mono_f = np.clip(mono_f, -1.0, 1.0)
    sd.stop()
    try:
        sd.play(mono_f, samplerate=dst_rate, device=device_index, blocking=True)
        return
    except Exception:
        max_ch = int(info.get("max_output_channels", 0) or 0)
        if max_ch < 2:
            raise
        shaped = np.zeros((len(mono_f), max_ch), dtype=np.float32)
        shaped[:, 0] = mono_f
        sd.play(shaped, samplerate=dst_rate, device=device_index, blocking=True)


def stop_playback() -> None:
    if sd is not None:
        sd.stop()
    if winsound is None:
        return
    winsound.PlaySound(None, 0)


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        rate = float(wav.getframerate())
        frames = float(wav.getnframes())
        return frames / rate if rate > 0 else 0.0


def record_wav(path: Path, seconds: float, device_index: int | None = None, sample_rate: int = 48000) -> None:
    """Record mono 16-bit WAV from selected input device."""
    if sd is None or np is None:
        raise RuntimeError("sounddevice/numpy are required for recording")
    if seconds <= 0:
        raise ValueError("Record duration must be > 0")

    frames = int(sample_rate * seconds)
    data = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device_index,
        blocking=True,
    )
    raw = data.reshape(-1).tobytes()
    _write_pcm16_mono(path, sample_rate, raw)


def capture_samples(seconds: float, device_index: int | None = None, sample_rate: int = 48000) -> tuple[int, np.ndarray]:
    """Capture mono int16 samples and return (sample_rate, float32 mono array)."""
    if sd is None or np is None:
        raise RuntimeError("sounddevice/numpy are required for recording")
    if seconds <= 0:
        raise ValueError("Capture duration must be > 0")

    frames = int(sample_rate * seconds)
    data = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device_index,
        blocking=True,
    )
    mono = data.reshape(-1).astype(np.float32) / 32768.0
    return sample_rate, mono


def write_test_tone_wav(path: Path, frequency_hz: float = 1200.0, seconds: float = 2.0, sample_rate: int = 48000) -> None:
    samples = int(sample_rate * seconds)
    amp = 0.55 * 32767.0
    data = bytearray()
    for i in range(samples):
        sample = int(amp * math.sin((2.0 * math.pi * frequency_hz * i) / sample_rate))
        data.extend(sample.to_bytes(2, byteorder="little", signed=True))
    _write_pcm16_mono(path, sample_rate, bytes(data))


def write_aprs_wav(
    path: Path,
    source: str,
    destination: str,
    message: str,
    path_via: str = "WIDE1-1",
    sample_rate: int = 48000,
    tx_gain: float = 0.6,
    preamble_flags: int = 120,
    trailing_flags: int = 12,
) -> None:
    frame = _build_ax25_ui_frame(source=source, destination=destination, path_via=path_via, info=message)
    bits = _frame_to_bitstream(frame, preamble_flags=preamble_flags, trailing_flags=trailing_flags)
    nrzi = _nrzi(bits)
    pcm = _afsk_from_nrzi(nrzi, sample_rate=sample_rate, tx_gain=tx_gain)
    _write_pcm16_mono(path, sample_rate, pcm)


def _write_pcm16_mono(path: Path, sample_rate: int, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(data)


def _build_ax25_ui_frame(source: str, destination: str, path_via: str, info: str) -> bytes:
    addrs = [_encode_ax25_addr(destination, is_last=False), _encode_ax25_addr(source, is_last=False)]
    vias = [v.strip() for v in path_via.split(",") if v.strip()]
    for idx, via in enumerate(vias):
        addrs.append(_encode_ax25_addr(via, is_last=False))

    # Mark final address field.
    last = bytearray(addrs[-1])
    last[-1] |= 0x01
    addrs[-1] = bytes(last)

    payload = b"".join(addrs) + bytes([0x03, 0xF0]) + info.encode("ascii", errors="replace")
    fcs = _crc16_x25(payload)
    return payload + fcs.to_bytes(2, byteorder="little")


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


def _frame_to_bitstream(frame: bytes, preamble_flags: int = 120, trailing_flags: int = 12) -> list[int]:
    bits: list[int] = []

    # Preamble flags.
    for _ in range(max(8, preamble_flags)):
        bits.extend(_byte_lsb_bits(0x7E))

    one_count = 0
    for byte in frame:
        for bit in _byte_lsb_bits(byte):
            bits.append(bit)
            if bit == 1:
                one_count += 1
                if one_count == 5:
                    bits.append(0)
                    one_count = 0
            else:
                one_count = 0

    # Trailing flags.
    for _ in range(max(2, trailing_flags)):
        bits.extend(_byte_lsb_bits(0x7E))

    return bits


def _byte_lsb_bits(value: int) -> list[int]:
    return [(value >> i) & 1 for i in range(8)]


def _nrzi(bits: list[int]) -> list[int]:
    level = 1
    out: list[int] = []
    for bit in bits:
        if bit == 0:
            level ^= 1
        out.append(level)
    return out


def _afsk_from_nrzi(nrzi: list[int], sample_rate: int = 48000, tx_gain: float = 0.6) -> bytes:
    if not nrzi:
        return b""

    mark = 1200.0
    space = 2200.0
    baud = 1200.0
    samples_per_bit = float(sample_rate) / baud
    amp = max(0.05, min(0.95, tx_gain)) * 32767.0
    total_samples = max(1, int(round(len(nrzi) * samples_per_bit)))
    attack = max(1, int(0.001 * sample_rate))
    release = attack
    phase = 0.0
    two_pi = 2.0 * math.pi
    data = bytearray()
    sample_index = 0

    for bit_idx, level in enumerate(nrzi):
        freq = mark if level else space
        phase_inc = two_pi * freq / sample_rate
        bit_start = int(round(bit_idx * samples_per_bit))
        bit_end = int(round((bit_idx + 1) * samples_per_bit))
        n_this_bit = max(1, bit_end - bit_start)
        for i in range(n_this_bit):
            env = 1.0
            if sample_index < attack:
                env = sample_index / float(attack)
            elif sample_index > (total_samples - release):
                tail = max(0, total_samples - sample_index)
                env = tail / float(release)
            sample = int(env * amp * math.sin(phase))
            data.extend(sample.to_bytes(2, byteorder="little", signed=True))
            phase += phase_inc
            if phase >= two_pi:
                phase -= two_pi
            sample_index += 1

    return bytes(data)
