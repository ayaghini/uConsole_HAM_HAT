#!/usr/bin/env python3
"""HAM HAT Control Center v2 — entry point."""

from __future__ import annotations

import logging
import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the package is importable regardless of working directory
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _configure_logging(level: int = logging.WARNING) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy library warnings
    for noisy in ("sounddevice", "comtypes", "pyserial"):
        logging.getLogger(noisy).setLevel(logging.ERROR)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HAM HAT Control Center v2.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity. -v for INFO, -vv for DEBUG.",
    )
    args = parser.parse_args()

    # Each -v flag decreases the log level by 10
    log_level = logging.WARNING - (args.verbose * 10)
    # Ensure the level doesn't go below DEBUG (10)
    log_level = max(log_level, logging.DEBUG)
    _configure_logging(level=log_level)

    try:
        from app.app import HamHatApp
    except ImportError as exc:
        print(f"Import error — is your virtualenv active?\n{exc}", file=sys.stderr)
        return 1

    app = HamHatApp(app_dir=_HERE)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
