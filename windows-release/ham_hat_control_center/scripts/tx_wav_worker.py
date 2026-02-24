#!/usr/bin/env python3
"""Transmit a WAV file through SA818 with explicit PTT control."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from audio_tools import play_wav_blocking_compatible  # noqa: E402
from sa818_client import RadioConfig, SA818Client  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SA818 WAV TX worker")
    p.add_argument("--port", required=True)
    p.add_argument("--wav", required=True)
    p.add_argument("--frequency", type=float, required=True)
    p.add_argument("--bandwidth", type=int, choices=[0, 1], default=0)
    p.add_argument("--squelch", type=int, default=4)
    p.add_argument("--volume", type=int, default=5)
    p.add_argument("--output-device", type=int, required=True)
    p.add_argument("--ptt-line", choices=["RTS", "DTR"], default="RTS")
    ptt = p.add_mutually_exclusive_group()
    ptt.add_argument("--ptt-active-high", dest="ptt_active_high", action="store_true")
    ptt.add_argument("--ptt-active-low", dest="ptt_active_high", action="store_false")
    p.set_defaults(ptt_active_high=True)
    p.add_argument("--ptt-pre-ms", type=float, default=400.0)
    p.add_argument("--ptt-post-ms", type=float, default=120.0)
    p.add_argument("--set-filters-flat", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    wav = Path(args.wav)
    if not wav.exists():
        print(f"WAV not found: {wav}", file=sys.stderr)
        return 2

    client = SA818Client()
    try:
        client.connect(args.port, timeout=1.2)
        cfg = RadioConfig(
            frequency=args.frequency,
            offset=0.0,
            bandwidth=args.bandwidth,
            squelch=max(0, min(8, args.squelch)),
            ctcss_tx=None,
            ctcss_rx=None,
            dcs_tx=None,
            dcs_rx=None,
        )
        client.set_radio(cfg)
        if args.volume is not None:
            client.set_volume(max(1, min(8, int(args.volume))))
        if args.set_filters_flat:
            try:
                client.set_filters(True, True, True)
            except Exception:
                pass

        client.set_ptt(True, line=args.ptt_line, active_high=args.ptt_active_high)
        time.sleep(max(0.0, args.ptt_pre_ms / 1000.0))
        try:
            play_wav_blocking_compatible(wav, device_index=args.output_device)
        finally:
            time.sleep(max(0.0, args.ptt_post_ms / 1000.0))
            client.set_ptt(False, line=args.ptt_line, active_high=args.ptt_active_high)
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
