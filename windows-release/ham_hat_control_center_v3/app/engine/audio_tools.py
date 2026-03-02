#!/usr/bin/env python3
"""Audio I/O helpers for playback, recording, and device enumeration.

v2 improvements over v1:
- list_output_devices / list_input_devices share a single internal helper;
  no code duplication.
- CRC is not duplicated here; it lives in aprs_modem.
- play_wav_blocking_compatible uses proper linear resampling.
- record_wav / capture_samples unchanged but with clearer error messages.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional

try:
    import winsound  # type: ignore
except ImportError:
    winsound = None  # type: ignore

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    np = None  # type: ignore
    sd = None  # type: ignore


# ---------------------------------------------------------------------------
# Device enumeration (single shared implementation)
# ---------------------------------------------------------------------------

def _list_devices(direction: str) -> list[tuple[int, str]]:
    """Enumerate audio devices filtered by direction ('input' or 'output').

    Returns list of (device_index, display_name) sorted by name.
    Favours WASAPI → MME; excludes DirectSound and Sound Mapper duplicates.
    """
    if sd is None:
        return []
    direction = direction.lower()
    ch_key = "max_output_channels" if direction == "output" else "max_input_channels"

    try:
        hostapis = sd.query_hostapis()
        devices = sd.query_devices()
    except Exception:
        return []

    ranked: list[tuple[int, int, str, str]] = []
    for idx, dev in enumerate(devices):
        if not dev.get(ch_key, 0):
            continue
        ha_idx = int(dev.get("hostapi", 0))
        ha_name = str(hostapis[ha_idx].get("name", "Unknown")) if ha_idx < len(hostapis) else "Unknown"
        if ha_name == "Windows DirectSound":
            continue
        name = str(dev.get("name", f"Device {idx}"))
        rank = {"Windows WASAPI": 0, "MME": 1}.get(ha_name, 3 if "WDM" not in ha_name else 2)
        ranked.append((rank, idx, name, ha_name))

    ranked.sort(key=lambda x: (x[0], x[1]))

    # De-duplicate by normalised name, preferring the lowest rank (WASAPI first)
    chosen: dict[str, tuple[int, int, str, str]] = {}
    for item in ranked:
        key = item[2].strip().lower()
        if key not in chosen:
            chosen[key] = item

    out = list(chosen.values())
    # Further filter: if WASAPI entries exist, drop MME duplicates of the same name
    if any(x[0] == 0 for x in out):
        out = [x for x in out if x[0] == 0]
    elif any(x[0] <= 1 for x in out):
        out = [x for x in out if x[0] <= 1]

    # Remove generic Sound Mapper entries
    out = [x for x in out if "sound mapper" not in x[2].strip().lower()]
    out.sort(key=lambda x: x[2].lower())
    return [(idx, name) for _, idx, name, _ in out]


def list_output_devices() -> list[tuple[int, str]]:
    return _list_devices("output")


def list_input_devices() -> list[tuple[int, str]]:
    return _list_devices("input")


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------

def play_wav(path: Path, device_index: Optional[int] = None) -> None:
    """Non-blocking WAV playback. Stops any current playback first."""
    if sd is not None and np is not None:
        data, rate = _load_wav_as_int16(path)
        sd.stop()
        sd.play(data, samplerate=rate, device=device_index, blocking=False)
        return
    if winsound is None:
        raise RuntimeError("No audio playback backend available")
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


def play_wav_blocking(path: Path, device_index: Optional[int] = None) -> None:
    """Blocking WAV playback."""
    if sd is not None and np is not None:
        data, rate = _load_wav_as_int16(path)
        sd.stop()
        sd.play(data, samplerate=rate, device=device_index, blocking=True)
        return
    if winsound is None:
        raise RuntimeError("No audio playback backend available")
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_SYNC | winsound.SND_NODEFAULT)


def play_wav_blocking_compatible(path: Path, device_index: int) -> None:
    """Blocking playback with device-compatible resampling (mono, device sample rate).

    Tries mono first; if the device refuses mono, pads to multichannel.
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
    dst_rate = int(round(float(info.get("default_samplerate", src_rate) or src_rate)))
    if dst_rate <= 0:
        dst_rate = int(src_rate)

    if dst_rate != src_rate and len(mono_f) > 1:
        src_n = len(mono_f)
        dst_n = max(1, int(round(src_n * dst_rate / src_rate)))
        xp = np.linspace(0.0, 1.0, src_n, endpoint=False)
        xq = np.linspace(0.0, 1.0, dst_n, endpoint=False)
        mono_f = np.interp(xq, xp, mono_f).astype(np.float32)

    mono_f = np.clip(mono_f, -1.0, 1.0)
    sd.stop()
    try:
        sd.play(mono_f, samplerate=dst_rate, device=device_index, blocking=True)
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
    if winsound is not None:
        try:
            winsound.PlaySound(None, 0)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Recording / capture
# ---------------------------------------------------------------------------

def record_wav(path: Path, seconds: float, device_index: Optional[int] = None, sample_rate: int = 48000) -> None:
    """Record mono 16-bit WAV from selected input device (blocking)."""
    if sd is None or np is None:
        raise RuntimeError("sounddevice/numpy are required for recording")
    if seconds <= 0:
        raise ValueError("Record duration must be > 0")
    frames = int(sample_rate * seconds)
    data = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="int16",
                  device=device_index, blocking=True)
    raw = data.reshape(-1).tobytes()
    _write_pcm16_mono(path, sample_rate, raw)


def capture_samples(seconds: float, device_index: Optional[int] = None,
                    sample_rate: int = 48000) -> tuple[int, "np.ndarray"]:
    """Capture mono float32 samples. Returns (sample_rate, float32_array)."""
    if sd is None or np is None:
        raise RuntimeError("sounddevice/numpy are required for recording")
    if seconds <= 0:
        raise ValueError("Capture duration must be > 0")
    frames = int(sample_rate * seconds)
    data = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="int16",
                  device=device_index, blocking=True)
    mono = data.reshape(-1).astype(np.float32) / 32768.0
    return sample_rate, mono


# ---------------------------------------------------------------------------
# WAV utilities
# ---------------------------------------------------------------------------

def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        rate = float(wav.getframerate())
        frames = float(wav.getnframes())
        return frames / rate if rate > 0 else 0.0


def estimate_wav_level(path: Path) -> float:
    """Return a normalised RMS level 0..1 for visualiser gain estimation."""
    if np is None:
        return 0.6
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
        x = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(x * x)))
        return max(0.05, min(1.0, rms * 6.0))
    except Exception:
        return 0.6


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_wav_as_int16(path: Path) -> tuple["np.ndarray", int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        raise RuntimeError("Only 16-bit PCM WAV is supported")
    data = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        data = data.reshape(-1, channels)
    return data, rate


def _write_pcm16_mono(path: Path, sample_rate: int, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(data)
