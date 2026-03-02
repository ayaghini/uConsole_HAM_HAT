#!/usr/bin/env python3
"""Play WAV on a specific output device — standalone subprocess worker.

Used by AudioRouter to work around Windows WASAPI thread-affinity restrictions.
The main process spawns this as a subprocess so audio plays from a fresh thread.
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path


def _setup_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WAV playback worker")
    p.add_argument("--wav", required=True, help="Path to WAV file")
    p.add_argument("--output-device", type=int, required=True,
                   help="sounddevice output device index")
    return p.parse_args()


def main() -> int:
    _setup_path()
    args = parse_args()

    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(f"[play_wav_worker] WAV not found: {wav_path}", file=sys.stderr)
        return 2

    try:
        import sounddevice as sd
        import numpy as np

        with wave.open(str(wav_path), "rb") as wf:
            rate      = wf.getframerate()
            channels  = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            frames    = wf.readframes(wf.getnframes())

        dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
        dtype = dtype_map.get(sampwidth, np.int16)
        data = np.frombuffer(frames, dtype=dtype)
        if channels > 1:
            data = data.reshape(-1, channels)

        # Normalise to float32 for sounddevice
        peak = float(np.iinfo(dtype).max)
        data_f = data.astype(np.float32) / peak

        sd.play(data_f, samplerate=rate, device=int(args.output_device), blocking=True)
        return 0

    except Exception as exc:
        print(f"[play_wav_worker] Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
