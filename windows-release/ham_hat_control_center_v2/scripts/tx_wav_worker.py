#!/usr/bin/env python3
"""Transmit a WAV file through SA818 with explicit PTT control — standalone worker.

This is the subprocess used by AudioRouter for WASAPI-compatible TX.
It connects to the radio, keys PTT, plays the WAV, then releases PTT.
Radio config is restored by the caller (parent process); this worker only
applies the given config and transmits.

Exit codes:
  0 — success
  1 — error (message on stderr)
  2 — WAV file not found
"""

from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path


def _setup_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SA818 WAV TX worker")
    p.add_argument("--port",            required=True)
    p.add_argument("--wav",             required=True)
    p.add_argument("--frequency",       type=float, required=True)
    p.add_argument("--bandwidth",       type=int, choices=[0, 1], default=0)
    p.add_argument("--squelch",         type=int, default=4)
    p.add_argument("--volume",          type=int, default=5)
    p.add_argument("--output-device",   type=int, required=True)
    p.add_argument("--ptt-line",        choices=["RTS", "DTR"], default="RTS")
    p.add_argument("--ptt-pre-ms",      type=float, default=400.0)
    p.add_argument("--ptt-post-ms",     type=float, default=120.0)
    p.add_argument("--set-filters-flat", action="store_true",
                   help="Disable all SA818 audio filters before TX")

    ptt_grp = p.add_mutually_exclusive_group()
    ptt_grp.add_argument("--ptt-active-high", dest="ptt_active_high", action="store_true",
                         help="Active (TX) = logic HIGH on the control line")
    ptt_grp.add_argument("--ptt-active-low",  dest="ptt_active_high", action="store_false",
                         help="Active (TX) = logic LOW on the control line")
    p.set_defaults(ptt_active_high=True)
    return p.parse_args()


def main() -> int:
    _setup_path()
    args = parse_args()

    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(f"[tx_wav_worker] WAV not found: {wav_path}", file=sys.stderr)
        return 2

    from app.engine.sa818_client import SA818Client, SA818Error
    from app.engine.models import RadioConfig

    import sounddevice as sd
    import numpy as np

    client = SA818Client()
    try:
        client.connect(args.port, timeout=1.5)
        cfg = RadioConfig(
            frequency=float(args.frequency),
            offset=0.0,
            bandwidth=int(args.bandwidth),
            squelch=max(0, min(8, int(args.squelch))),
        )
        client.set_radio(cfg)
        client.set_volume(max(1, min(8, int(args.volume))))
        if args.set_filters_flat:
            try:
                client.set_filters(True, True, True)
            except Exception:
                pass

        # Load WAV
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
        peak = float(np.iinfo(dtype).max)
        data_f = data.astype(np.float32) / peak

        # PTT → pre-delay → play → post-delay → release
        client.set_ptt(True, line=args.ptt_line, active_high=args.ptt_active_high)
        time.sleep(max(0.0, args.ptt_pre_ms / 1000.0))
        try:
            sd.play(data_f, samplerate=rate, device=int(args.output_device), blocking=True)
        finally:
            time.sleep(max(0.0, args.ptt_post_ms / 1000.0))
            client.set_ptt(False, line=args.ptt_line, active_high=args.ptt_active_high)

        return 0

    except SA818Error as exc:
        print(f"[tx_wav_worker] SA818 error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[tx_wav_worker] Error: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            client.set_ptt(False, line=args.ptt_line, active_high=args.ptt_active_high)
        except Exception:
            pass
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
