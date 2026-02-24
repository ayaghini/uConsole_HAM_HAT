#!/usr/bin/env python3
"""Record mono WAV from a selected input device in a standalone process."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from audio_tools import record_wav  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture WAV worker")
    p.add_argument("--wav", required=True)
    p.add_argument("--seconds", type=float, required=True)
    p.add_argument("--sample-rate", type=int, default=48000)
    p.add_argument("--input-device", type=int, default=-1)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.wav)
    dev = None if int(args.input_device) < 0 else int(args.input_device)
    record_wav(
        path=out,
        seconds=float(args.seconds),
        device_index=dev,
        sample_rate=int(args.sample_rate),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

