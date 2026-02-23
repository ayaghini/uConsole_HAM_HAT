#!/usr/bin/env python3
"""Two-radio diagnostic for SA818 APRS TX/RX reliability."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from aprs_modem import decode_ax25_from_wav  # noqa: E402
from audio_tools import (  # noqa: E402
    play_wav_blocking,
    record_wav,
    stop_playback,
    wav_duration_seconds,
    write_aprs_wav,
)
from sa818_client import RadioConfig, SA818Client  # noqa: E402


def _radio_cfg(freq: float, squelch: int, bandwidth: int) -> RadioConfig:
    return RadioConfig(
        frequency=freq,
        offset=0.0,
        bandwidth=bandwidth,
        squelch=squelch,
        ctcss_tx=None,
        ctcss_rx=None,
        dcs_tx=None,
        dcs_rx=None,
    )


def _serial_stress(client: SA818Client, loops: int, ptt_line: str, active_high: bool) -> tuple[int, int]:
    ok = 0
    fail = 0
    for i in range(loops):
        try:
            _ = client.version()
            client.set_ptt(True, line=ptt_line, active_high=active_high)
            time.sleep(0.08)
            client.set_ptt(False, line=ptt_line, active_high=active_high)
            ok += 1
            print(f"[serial] iter {i+1}/{loops}: ok")
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"[serial] iter {i+1}/{loops}: fail: {exc}")
    return ok, fail


def run(args: argparse.Namespace) -> int:
    audio_dir = ROOT / "audio_out"
    audio_dir.mkdir(parents=True, exist_ok=True)

    tx = SA818Client()
    rx = SA818Client()
    tx_ok = 0
    rx_ok = 0

    try:
        print(f"Connecting TX radio on {args.tx_port}...")
        try:
            tx.connect(args.tx_port, timeout=1.2)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"TX radio on {args.tx_port} is not responding: {exc}") from exc
        print(f"TX version: {tx.version()}")

        print(f"Connecting RX radio on {args.rx_port}...")
        try:
            rx.connect(args.rx_port, timeout=1.2)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"RX radio on {args.rx_port} is not responding: {exc}") from exc
        print(f"RX version: {rx.version()}")

        tx.set_radio(_radio_cfg(args.frequency, squelch=4, bandwidth=args.bandwidth))
        rx.set_radio(_radio_cfg(args.frequency, squelch=0, bandwidth=args.bandwidth))
        tx.set_volume(args.volume)
        rx.set_volume(args.volume)
        print("Both radios configured.")

        # Always perform serial stability checks.
        print("\nRunning serial/PTT stress checks...")
        tx_ok, tx_fail = _serial_stress(tx, args.serial_loops, args.ptt_line, args.ptt_active_high)
        rx_ok, rx_fail = _serial_stress(rx, args.serial_loops, args.ptt_line, args.ptt_active_high)
        print(f"[serial] TX ok={tx_ok} fail={tx_fail} | RX ok={rx_ok} fail={rx_fail}")

        if args.skip_audio:
            return 0

        print("\nRunning APRS over-air/audio loop test...")
        pass_count = 0
        for i in range(args.aprs_loops):
            msg = f"DIAG-{i+1:02d}-{int(time.time())%100000}"
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
            tx_sec = wav_duration_seconds(wav_tx)
            rec_sec = tx_sec + args.extra_record_sec

            print(f"[aprs] iter {i+1}/{args.aprs_loops}: msg={msg}, tx={tx_sec:.2f}s rec={rec_sec:.2f}s")
            tx.set_ptt(True, line=args.ptt_line, active_high=args.ptt_active_high)
            try:
                time.sleep(max(0.0, args.ptt_pre_ms / 1000.0))
                # Start recording first so packet preamble is not missed.
                import threading

                rec_exc: list[Exception] = []

                def rec_worker() -> None:
                    try:
                        record_wav(wav_rx, seconds=rec_sec, device_index=args.input_device, sample_rate=48000)
                    except Exception as exc:  # noqa: BLE001
                        rec_exc.append(exc)

                t = threading.Thread(target=rec_worker, daemon=True)
                t.start()
                time.sleep(0.10)
                play_wav_blocking(wav_tx, device_index=args.output_device)
                t.join()
                if rec_exc:
                    raise rec_exc[0]
            finally:
                time.sleep(max(0.0, args.ptt_post_ms / 1000.0))
                tx.set_ptt(False, line=args.ptt_line, active_high=args.ptt_active_high)

            decoded = decode_ax25_from_wav(str(wav_rx))
            got = [p.text for p in decoded]
            hit = any(msg in t for t in got)
            if hit:
                pass_count += 1
                print(f"[aprs] iter {i+1}: PASS ({len(got)} packet(s))")
            else:
                print(f"[aprs] iter {i+1}: FAIL ({len(got)} packet(s))")
                for t in got[:3]:
                    print(f"  rx: {t}")

        print(f"\n[aprs] summary: {pass_count}/{args.aprs_loops} decoded")
        return 0 if pass_count > 0 else 2
    finally:
        stop_playback()
        try:
            tx.set_ptt(False, line=args.ptt_line, active_high=args.ptt_active_high)
        except Exception:
            pass
        tx.disconnect()
        rx.disconnect()
        print(f"Done. Serial checks tx_ok={tx_ok} rx_ok={rx_ok}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Two SA818 APRS diagnostic")
    p.add_argument("--tx-port", required=True, help="COM port for TX radio (e.g. COM8)")
    p.add_argument("--rx-port", required=True, help="COM port for RX radio (e.g. COM7)")
    p.add_argument("--frequency", type=float, default=145.050, help="Test frequency MHz")
    p.add_argument("--bandwidth", type=int, choices=[0, 1], default=0, help="0 narrow, 1 wide")
    p.add_argument("--volume", type=int, default=5, help="SA818 volume 1..8")
    p.add_argument("--serial-loops", type=int, default=20, help="Serial/PTT stress loops")
    p.add_argument("--skip-audio", action="store_true", help="Only do serial tests")

    p.add_argument("--aprs-loops", type=int, default=10, help="Over-air APRS loops")
    p.add_argument("--source", default="N0CALL-9")
    p.add_argument("--destination", default="APRS")
    p.add_argument("--path", default="WIDE1-1")
    p.add_argument("--tx-gain", type=float, default=0.24)
    p.add_argument("--preamble-flags", type=int, default=160)
    p.add_argument("--extra-record-sec", type=float, default=1.3)
    p.add_argument("--input-device", type=int, default=None, help="sounddevice input device index")
    p.add_argument("--output-device", type=int, default=None, help="sounddevice output device index")

    p.add_argument("--ptt-line", choices=["RTS", "DTR"], default="RTS")
    ptt = p.add_mutually_exclusive_group()
    ptt.add_argument("--ptt-active-high", dest="ptt_active_high", action="store_true", help="Asserted line means TX")
    ptt.add_argument("--ptt-active-low", dest="ptt_active_high", action="store_false", help="Deasserted line means TX")
    p.set_defaults(ptt_active_high=True)
    p.add_argument("--ptt-pre-ms", type=int, default=400)
    p.add_argument("--ptt-post-ms", type=int, default=120)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
