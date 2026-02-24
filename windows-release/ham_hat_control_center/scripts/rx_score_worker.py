#!/usr/bin/env python3
"""Capture input audio and print a simple voice-activity score."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from audio_tools import capture_samples  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RX voice score worker")
    p.add_argument("--seconds", type=float, required=True)
    p.add_argument("--sample-rate", type=int, default=48000)
    p.add_argument("--input-device", type=int, default=-1)
    return p.parse_args()


def voice_activity_score(samples: np.ndarray) -> float:
    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(x) < 32:
        return 0.0
    x = x - float(np.mean(x))
    rms = float(np.sqrt(np.mean(x * x)))
    p95 = float(np.percentile(np.abs(x), 95))
    return (0.7 * rms) + (0.3 * p95)


def main() -> int:
    args = parse_args()
    dev = None if int(args.input_device) < 0 else int(args.input_device)
    _, mono = capture_samples(
        seconds=float(args.seconds),
        device_index=dev,
        sample_rate=int(args.sample_rate),
    )
    score = voice_activity_score(mono)
    print(f"{score:.8f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

