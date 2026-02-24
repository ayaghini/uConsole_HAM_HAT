#!/usr/bin/env python3
"""Play WAV on a specific output device in a standalone process."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from audio_tools import play_wav_blocking_compatible  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WAV playback worker")
    p.add_argument("--wav", required=True)
    p.add_argument("--output-device", type=int, required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    wav = Path(args.wav)
    if not wav.exists():
        print(f"WAV not found: {wav}", file=sys.stderr)
        return 2
    play_wav_blocking_compatible(wav, device_index=int(args.output_device))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

