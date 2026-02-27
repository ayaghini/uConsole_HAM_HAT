#!/usr/bin/env python3
"""Two-radio APRS TX/RX reliability diagnostic.

Requires two SA818 radios on separate COM ports. Runs serial/PTT stress tests
then over-air APRS loop tests.

Usage:
    python scripts/two_radio_diagnostic.py --tx-port COM8 --rx-port COM7

Exit codes:
  0  success (all serial tests ok, at least one APRS packet decoded if --aprs-loops > 0)
  1  configuration / connection error
  2  APRS loop test: all packets failed to decode
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import wave
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


from app.engine.aprs_modem import decode_ax25_from_samples, write_aprs_wav  # noqa: E402
from app.engine.models import RadioConfig  # noqa: E402
from app.engine.sa818_client import SA818Client, SA818Error  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_radio_cfg(freq: float, squelch: int, bw: int) -> RadioConfig:
    return RadioConfig(frequency=freq, offset=0.0, bandwidth=bw, squelch=squelch)


def _serial_ptt_stress(
    client: SA818Client, loops: int, ptt_line: str, active_high: bool
) -> tuple[int, int]:
    ok = fail = 0
    for i in range(loops):
        try:
            client.version()
            client.set_ptt(True,  line=ptt_line, active_high=active_high)
            time.sleep(0.08)
            client.set_ptt(False, line=ptt_line, active_high=active_high)
            ok += 1
            print(f"  [serial {i+1:3d}/{loops}] OK")
        except Exception as exc:
            fail += 1
            print(f"  [serial {i+1:3d}/{loops}] FAIL: {exc}")
    return ok, fail


def _record_into(path: Path, seconds: float, device: int | None, rate: int) -> None:
    import sounddevice as sd
    import numpy as np
    data = sd.rec(int(seconds * rate), samplerate=rate, channels=1,
                  dtype="int16", device=device)
    sd.wait()
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data.tobytes())


def _play_wav(path: Path, device: int | None, rate: int) -> None:
    import sounddevice as sd
    import numpy as np
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    sd.play(data, samplerate=rate, device=device, blocking=True)


def _decode_wav(path: Path, rate: int) -> list:
    import numpy as np
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        r = wf.getframerate()
    mono = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return decode_ax25_from_samples(r, mono)


# ---------------------------------------------------------------------------
# Main diagnostic logic
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    audio_dir = _ROOT / "audio_out"
    audio_dir.mkdir(parents=True, exist_ok=True)
    sample_rate = 48000

    tx = SA818Client()
    rx = SA818Client()
    tx_ok = rx_ok = 0

    try:
        # ---- Connect ----
        print(f"\nConnecting TX radio on {args.tx_port}…")
        tx.connect(args.tx_port, timeout=1.5)
        print(f"  TX version: {tx.version()}")

        print(f"Connecting RX radio on {args.rx_port}…")
        rx.connect(args.rx_port, timeout=1.5)
        print(f"  RX version: {rx.version()}")

        # ---- Configure ----
        bw = int(args.bandwidth)
        tx.set_radio(_build_radio_cfg(args.frequency, squelch=4, bw=bw))
        rx.set_radio(_build_radio_cfg(args.frequency, squelch=0, bw=bw))
        tx.set_volume(args.volume)
        rx.set_volume(args.volume)
        print("Both radios configured.\n")

        # ---- Serial / PTT stress ----
        print(f"Serial/PTT stress ({args.serial_loops} iterations each)…")
        tx_ok, tx_fail = _serial_ptt_stress(tx, args.serial_loops, args.ptt_line, args.ptt_active_high)
        rx_ok, rx_fail = _serial_ptt_stress(rx, args.serial_loops, args.ptt_line, args.ptt_active_high)
        print(f"\n  TX: ok={tx_ok} fail={tx_fail}  |  RX: ok={rx_ok} fail={rx_fail}\n")

        if args.skip_audio:
            print("[done] Skipping audio tests (--skip-audio).")
            return 0

        # ---- APRS over-air loops ----
        print(f"APRS over-air test ({args.aprs_loops} loops)…")
        pass_count = 0

        for i in range(args.aprs_loops):
            msg = f"DIAG-{i+1:02d}-{int(time.time()) % 100000}"
            wav_tx = audio_dir / f"diag_tx_{i+1:02d}.wav"
            wav_rx = audio_dir / f"diag_rx_{i+1:02d}.wav"

            write_aprs_wav(
                wav_tx,
                source=args.source,
                destination=args.destination,
                path_via=args.path,
                message=msg,
                tx_gain=args.tx_gain,
                preamble_flags=args.preamble_flags,
                trailing_flags=12,
            )

            # Calculate durations
            with wave.open(str(wav_tx), "rb") as wf:
                tx_sec = wf.getnframes() / wf.getframerate()
            rec_sec = tx_sec + args.extra_record_sec

            print(f"  [loop {i+1:2d}/{args.aprs_loops}]  msg={msg}  tx={tx_sec:.2f}s rec={rec_sec:.2f}s")

            tx.set_ptt(True, line=args.ptt_line, active_high=args.ptt_active_high)
            rec_errors: list[Exception] = []

            def _rec() -> None:
                try:
                    _record_into(wav_rx, rec_sec, args.input_device, sample_rate)
                except Exception as exc:
                    rec_errors.append(exc)

            rec_thread = threading.Thread(target=_rec, daemon=True)
            try:
                time.sleep(max(0.0, args.ptt_pre_ms / 1000.0))
                rec_thread.start()
                time.sleep(0.08)   # brief overlap so RX is already open
                _play_wav(wav_tx, args.output_device, sample_rate)
                rec_thread.join()
                if rec_errors:
                    raise rec_errors[0]
            finally:
                time.sleep(max(0.0, args.ptt_post_ms / 1000.0))
                tx.set_ptt(False, line=args.ptt_line, active_high=args.ptt_active_high)

            decoded = _decode_wav(wav_rx, sample_rate)
            hit = any(msg in pkt.text for pkt in decoded)
            if hit:
                pass_count += 1
                print(f"    → PASS  ({len(decoded)} packet(s) decoded)")
            else:
                print(f"    → FAIL  ({len(decoded)} packet(s) decoded)")
                for pkt in decoded[:3]:
                    print(f"       rx: {pkt.text}")

        print(f"\n[result] {pass_count}/{args.aprs_loops} APRS loops decoded successfully")
        return 0 if pass_count > 0 else 2

    except SA818Error as exc:
        print(f"\n[error] SA818: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\n[error] {exc}", file=sys.stderr)
        return 1

    finally:
        for client, label in [(tx, "TX"), (rx, "RX")]:
            try:
                client.set_ptt(False, line=args.ptt_line, active_high=args.ptt_active_high)
            except Exception:
                pass
            try:
                client.disconnect()
            except Exception:
                pass
        print(f"[done] Serial results  TX ok={tx_ok}  RX ok={rx_ok}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Two SA818 APRS reliability diagnostic")

    # Radio
    p.add_argument("--tx-port",   required=True, help="COM port for TX radio (e.g. COM8)")
    p.add_argument("--rx-port",   required=True, help="COM port for RX radio (e.g. COM7)")
    p.add_argument("--frequency", type=float, default=145.050, help="Test frequency MHz")
    p.add_argument("--bandwidth", type=int, choices=[0, 1], default=0, help="0=narrow 1=wide")
    p.add_argument("--volume",    type=int, default=5, help="SA818 speaker volume 1..8")

    # Serial tests
    p.add_argument("--serial-loops", type=int, default=20)
    p.add_argument("--skip-audio",   action="store_true", help="Run serial tests only")

    # APRS tests
    p.add_argument("--aprs-loops",       type=int,   default=10)
    p.add_argument("--source",           default="N0CALL-9")
    p.add_argument("--destination",      default="APRS")
    p.add_argument("--path",             default="WIDE1-1")
    p.add_argument("--tx-gain",          type=float, default=0.28)
    p.add_argument("--preamble-flags",   type=int,   default=180)
    p.add_argument("--extra-record-sec", type=float, default=1.5)
    p.add_argument("--input-device",     type=int,   default=None)
    p.add_argument("--output-device",    type=int,   default=None)

    # PTT
    p.add_argument("--ptt-line", choices=["RTS", "DTR"], default="RTS")
    ptt = p.add_mutually_exclusive_group()
    ptt.add_argument("--ptt-active-high", dest="ptt_active_high", action="store_true")
    ptt.add_argument("--ptt-active-low",  dest="ptt_active_high", action="store_false")
    p.set_defaults(ptt_active_high=True)
    p.add_argument("--ptt-pre-ms",  type=int, default=400)
    p.add_argument("--ptt-post-ms", type=int, default=120)

    return p


def main() -> int:
    return run(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
