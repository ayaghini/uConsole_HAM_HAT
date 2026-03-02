#!/usr/bin/env python3
"""Install core Python requirements and optional third-party SA818 tools.

Run once after cloning / extracting the release archive:

    python scripts/bootstrap_third_party.py

Options:
    --offline    Use local resource snapshots instead of cloning from GitHub
    --dev        Also install pycaw (Windows audio volume control)
    --target     Where to store cloned repos (default: third_party/)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPOS = {
    "sa818": "https://github.com/0x9900/SA818.git",
    "srfrs":  "https://github.com/jumbo5566/SRFRS.git",
}

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    label = " ".join(str(c) for c in cmd)
    print(f"  [run] {label}")
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _pip(*packages: str) -> None:
    _run([sys.executable, "-m", "pip", "install", "--upgrade", *packages])


def install_core_requirements() -> None:
    req_file = _ROOT / "requirements.txt"
    if req_file.exists():
        print("\nInstalling core requirements…")
        _pip("-r", str(req_file))
    else:
        print("\nrequirements.txt not found — installing defaults…")
        _pip("pyserial", "numpy", "sounddevice")


def install_pycaw() -> None:
    print("\nInstalling pycaw (Windows audio volume control)…")
    _pip("pycaw")


def clone_or_pull(name: str, url: str, target_root: Path) -> Path:
    target = target_root / name
    if target.exists() and (target / ".git").exists():
        print(f"  [git pull] {name}")
        _run(["git", "pull", "--ff-only"], cwd=target)
    elif target.exists():
        print(f"  [skip] {target} exists (not a git repo)")
    else:
        print(f"  [git clone] {name}")
        _run(["git", "clone", url, str(target)])
    return target


def copy_local_fallback(target_root: Path) -> None:
    """Copy bundled resource snapshots when offline."""
    fallbacks = {
        "sa818": _ROOT.parent.parent / "Resources" / "SA818 programmer" / "SA818",
        "srfrs":  _ROOT.parent.parent / "Resources" / "SRFRS" / "SRFRS-main" / "SRFRS-main",
    }
    for name, src in fallbacks.items():
        dst = target_root / name
        if dst.exists() or not src.exists():
            continue
        print(f"  [copy] {src} → {dst}")
        shutil.copytree(src, dst)


def install_sa818_package(target_root: Path) -> None:
    sa818_dir = target_root / "sa818"
    if sa818_dir.exists() and (sa818_dir / "setup.py").exists():
        print("\nInstalling SA818 Python package from local clone…")
        _pip(str(sa818_dir))


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap HAM HAT Control Center v2 dependencies")
    parser.add_argument("--offline", action="store_true",
                        help="Use only local resource snapshots (no internet required)")
    parser.add_argument("--dev", action="store_true",
                        help="Also install pycaw for Windows audio volume control")
    parser.add_argument("--target", default="third_party",
                        help="Directory for cloned third-party repos (default: third_party/)")
    args = parser.parse_args()

    target_root = (_ROOT / args.target).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    # Step 1: core Python packages
    install_core_requirements()

    # Step 2: optional pycaw
    if args.dev:
        install_pycaw()

    # Step 3: third-party SA818 tools
    print("\nFetching third-party SA818 tools…")
    if args.offline:
        copy_local_fallback(target_root)
    else:
        for name, url in REPOS.items():
            try:
                clone_or_pull(name, url, target_root)
            except subprocess.CalledProcessError:
                print(f"  [warn] network fetch of {name} failed — trying local fallback")
                copy_local_fallback(target_root)
                break

    install_sa818_package(target_root)

    print("\n[done] bootstrap complete")
    print(f"[info] third-party tools: {target_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
