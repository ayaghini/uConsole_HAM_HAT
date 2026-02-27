#!/usr/bin/env python3
"""Capture audio from a selected input device and write a WAV — standalone subprocess worker.

Spawned by AudioRouter to work around Windows WASAPI thread-affinity issues.
Exits with code 0 on success, non-zero on error.
"""

from __future__ import annotations

import argparse
import struct
import sys
import wave
from pathlib import Path


def _setup_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture WAV worker")
    p.add_argument("--wav", required=True, help="Output WAV file path")
    p.add_argument("--seconds", type=float, required=True, help="Recording duration in seconds")
    p.add_argument("--sample-rate", type=int, default=48000)
    p.add_argument("--channels", type=int, default=1)
    p.add_argument("--input-device", type=int, default=-1,
                   help="sounddevice input device index (-1 = default)")
    return p.parse_args()


def main() -> int:
    _setup_path()
    args = parse_args()

    out_path = Path(args.wav)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    device = None if int(args.input_device) < 0 else int(args.input_device)

    try:
        import sounddevice as sd
        import numpy as np

        data = sd.rec(
            frames=int(args.seconds * args.sample_rate),
            samplerate=args.sample_rate,
            channels=args.channels,
            dtype="int16",
            device=device,
        )
        sd.wait()

        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(args.channels)
            wf.setsampwidth(2)   # int16
            wf.setframerate(args.sample_rate)
            wf.writeframes(data.tobytes())

        return 0

    except Exception as exc:
        print(f"[capture_wav_worker] Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
