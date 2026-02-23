#!/usr/bin/env python3
"""Optional bootstrap for third-party SA818 tools."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPOS = {
    "sa818": "https://github.com/0x9900/SA818.git",
    "srfrs": "https://github.com/jumbo5566/SRFRS.git",
}


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"[run] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def clone_or_pull(name: str, url: str, target_root: Path) -> Path:
    target = target_root / name
    if target.exists() and (target / ".git").exists():
        run(["git", "pull", "--ff-only"], cwd=target)
    elif target.exists():
        print(f"[skip] {target} exists but is not a git repo")
    else:
        run(["git", "clone", url, str(target)])
    return target


def install_python_deps(target: Path) -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "pyserial"])
    sa818_dir = target / "sa818"
    if sa818_dir.exists() and (sa818_dir / "setup.py").exists():
        run([sys.executable, "-m", "pip", "install", str(sa818_dir)])


def copy_local_fallback(target_root: Path) -> None:
    """Copy local snapshots if running inside your project repository."""
    project_root = Path(__file__).resolve().parents[2]
    fallbacks = {
        "sa818": project_root / "Resources" / "SA818 programmer" / "SA818",
        "srfrs": project_root / "Resources" / "SRFRS" / "SRFRS-main" / "SRFRS-main",
    }
    for name, src in fallbacks.items():
        dst = target_root / name
        if dst.exists() or not src.exists():
            continue
        print(f"[copy] {src} -> {dst}")
        shutil.copytree(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup third-party SA818 tooling")
    parser.add_argument("--offline", action="store_true", help="Use only local fallback copies")
    parser.add_argument("--target", default="third_party", help="Where tools are stored")
    args = parser.parse_args()

    target_root = Path(args.target).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    if args.offline:
        copy_local_fallback(target_root)
    else:
        for name, url in REPOS.items():
            try:
                clone_or_pull(name, url, target_root)
            except subprocess.CalledProcessError:
                print(f"[warn] failed to fetch {name} from network, trying local fallback")
                copy_local_fallback(target_root)

    install_python_deps(target_root)

    print("[done] bootstrap complete")
    print(f"[info] tools location: {target_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
