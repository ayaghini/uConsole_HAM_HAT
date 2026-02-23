#!/usr/bin/env python3
"""Raspberry Pi UI for uConsole HAM HAT bring-up and SA818 control."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from serial.tools import list_ports

from sa818_client import RadioConfig, SA818Client, SA818Error


APP_DIR = Path(__file__).resolve().parents[1]
PROFILE_PATH = APP_DIR / "profiles" / "last_profile.json"


class HamHatControlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("uConsole HAM HAT Control Center")
        self.geometry("980x720")

        self.client = SA818Client()

        self._vars()
        self._build_ui()
        self.refresh_ports()
        self.load_profile(silent=True)

    def _vars(self) -> None:
        self.port_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Disconnected")

        self.frequency_var = tk.StringVar(value="145.070")
        self.offset_var = tk.StringVar(value="0.6")
        self.squelch_var = tk.StringVar(value="4")
        self.bandwidth_var = tk.StringVar(value="Wide")

        self.ctcss_tx_var = tk.StringVar(value="")
        self.ctcss_rx_var = tk.StringVar(value="")
        self.dcs_tx_var = tk.StringVar(value="")
        self.dcs_rx_var = tk.StringVar(value="")

        self.disable_emphasis_var = tk.BooleanVar(value=True)
        self.disable_highpass_var = tk.BooleanVar(value=True)
        self.disable_lowpass_var = tk.BooleanVar(value=True)

        self.volume_var = tk.IntVar(value=5)
        self.offline_bootstrap_var = tk.BooleanVar(value=False)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Serial Port:").pack(side="left")
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, width=28, state="readonly")
        self.port_combo.pack(side="left", padx=(6, 6))

        ttk.Button(top, text="Refresh", command=self.refresh_ports).pack(side="left")
        ttk.Button(top, text="Connect", command=self.connect).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Disconnect", command=self.disconnect).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Read Version", command=self.read_version).pack(side="left", padx=(8, 0))

        ttk.Label(top, textvariable=self.status_var).pack(side="right")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        control_tab = ttk.Frame(notebook, padding=10)
        setup_tab = ttk.Frame(notebook, padding=10)
        notebook.add(control_tab, text="Radio Control")
        notebook.add(setup_tab, text="Setup")

        self._build_control_tab(control_tab)
        self._build_setup_tab(setup_tab)

        log_frame = ttk.LabelFrame(self, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = ScrolledText(log_frame, height=14)
        self.log_text.pack(fill="both", expand=True)

    def _build_control_tab(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        left.pack(side="left", fill="both", expand=True)

        radio = ttk.LabelFrame(left, text="Radio", padding=10)
        radio.pack(fill="x")

        self._row(radio, "Frequency (MHz)", ttk.Entry(radio, textvariable=self.frequency_var, width=16), 0)
        self._row(radio, "Offset (MHz)", ttk.Entry(radio, textvariable=self.offset_var, width=16), 1)
        self._row(radio, "Squelch (0-8)", ttk.Entry(radio, textvariable=self.squelch_var, width=16), 2)

        bw_combo = ttk.Combobox(radio, textvariable=self.bandwidth_var, values=["Wide", "Narrow"], width=14, state="readonly")
        self._row(radio, "Bandwidth", bw_combo, 3)

        self._row(radio, "CTCSS TX", ttk.Entry(radio, textvariable=self.ctcss_tx_var, width=16), 4)
        self._row(radio, "CTCSS RX", ttk.Entry(radio, textvariable=self.ctcss_rx_var, width=16), 5)
        self._row(radio, "DCS TX", ttk.Entry(radio, textvariable=self.dcs_tx_var, width=16), 6)
        self._row(radio, "DCS RX", ttk.Entry(radio, textvariable=self.dcs_rx_var, width=16), 7)

        ttk.Button(radio, text="Apply Radio", command=self.apply_radio).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        filters = ttk.LabelFrame(left, text="Filters", padding=10)
        filters.pack(fill="x", pady=(10, 0))

        ttk.Checkbutton(filters, text="Disable pre/de-emphasis", variable=self.disable_emphasis_var).pack(anchor="w")
        ttk.Checkbutton(filters, text="Disable high-pass", variable=self.disable_highpass_var).pack(anchor="w")
        ttk.Checkbutton(filters, text="Disable low-pass", variable=self.disable_lowpass_var).pack(anchor="w")
        ttk.Button(filters, text="Apply Filters", command=self.apply_filters).pack(fill="x", pady=(8, 0))

        volume = ttk.LabelFrame(left, text="Volume", padding=10)
        volume.pack(fill="x", pady=(10, 0))
        ttk.Scale(volume, from_=1, to=8, variable=self.volume_var, orient="horizontal").pack(fill="x")
        ttk.Button(volume, text="Apply Volume", command=self.apply_volume).pack(fill="x", pady=(8, 0))

        profiles = ttk.LabelFrame(parent, text="Profiles", padding=10)
        profiles.pack(side="left", fill="y", padx=(10, 0))
        ttk.Button(profiles, text="Save Profile", command=self.save_profile).pack(fill="x")
        ttk.Button(profiles, text="Load Profile", command=self.load_profile).pack(fill="x", pady=(8, 0))

        hints = (
            "Hints\n"
            "- Use either CTCSS or DCS, not both\n"
            "- DCS format: 047N or 047I\n"
            "- For no tone, leave tone fields empty"
        )
        ttk.Label(profiles, text=hints, justify="left").pack(anchor="w", pady=(14, 0))

    def _build_setup_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Automated setup for third-party SA818 tools").pack(anchor="w")
        ttk.Checkbutton(parent, text="Offline mode (use local fallback snapshots)", variable=self.offline_bootstrap_var).pack(anchor="w", pady=(6, 10))
        ttk.Button(parent, text="Run Third-Party Bootstrap", command=self.run_bootstrap).pack(anchor="w")

        help_text = (
            "Bootstrap does:\n"
            "1. Install/upgrade pip\n"
            "2. Install pyserial\n"
            "3. Clone/pull SA818 and SRFRS repos\n"
            "4. Install SA818 python package\n"
        )
        ttk.Label(parent, text=help_text, justify="left").pack(anchor="w", pady=(12, 0))

    @staticmethod
    def _row(frame: ttk.Frame, label: str, widget: ttk.Widget, row: int) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        widget.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        frame.columnconfigure(1, weight=1)

    def log(self, msg: str) -> None:
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def refresh_ports(self) -> None:
        ports = [p.device for p in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])
        self.log(f"Ports: {ports if ports else 'none'}")

    def connect(self) -> None:
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Error", "Select a serial port")
            return
        try:
            self.client.connect(port)
        except Exception as exc:  # noqa: BLE001
            self.status_var.set("Disconnected")
            self.log(f"Connect failed: {exc}")
            messagebox.showerror("Connect failed", str(exc))
            return
        self.status_var.set(f"Connected: {port}")
        self.log(f"Connected to {port}")

    def disconnect(self) -> None:
        self.client.disconnect()
        self.status_var.set("Disconnected")
        self.log("Disconnected")

    def read_version(self) -> None:
        try:
            reply = self.client.version()
            self.log(f"Version: {reply}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Read version failed: {exc}")
            messagebox.showerror("Error", str(exc))

    def apply_radio(self) -> None:
        try:
            cfg = RadioConfig(
                frequency=float(self.frequency_var.get().strip()),
                offset=float(self.offset_var.get().strip()),
                bandwidth=1 if self.bandwidth_var.get() == "Wide" else 0,
                squelch=int(self.squelch_var.get().strip()),
                ctcss_tx=self._opt(self.ctcss_tx_var.get()),
                ctcss_rx=self._opt(self.ctcss_rx_var.get()),
                dcs_tx=self._opt(self.dcs_tx_var.get()),
                dcs_rx=self._opt(self.dcs_rx_var.get()),
            )
            if (cfg.ctcss_tx or cfg.ctcss_rx) and (cfg.dcs_tx or cfg.dcs_rx):
                raise SA818Error("Use either CTCSS or DCS, not both")
            reply = self.client.set_radio(cfg)
            self.log(f"Radio set OK: {reply}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Radio set failed: {exc}")
            messagebox.showerror("Error", str(exc))

    def apply_filters(self) -> None:
        try:
            reply = self.client.set_filters(
                disable_emphasis=self.disable_emphasis_var.get(),
                disable_highpass=self.disable_highpass_var.get(),
                disable_lowpass=self.disable_lowpass_var.get(),
            )
            self.log(f"Filters set OK: {reply}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Filter set failed: {exc}")
            messagebox.showerror("Error", str(exc))

    def apply_volume(self) -> None:
        try:
            reply = self.client.set_volume(int(self.volume_var.get()))
            self.log(f"Volume set OK: {reply}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Volume set failed: {exc}")
            messagebox.showerror("Error", str(exc))

    def save_profile(self) -> None:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "frequency": self.frequency_var.get(),
            "offset": self.offset_var.get(),
            "squelch": self.squelch_var.get(),
            "bandwidth": self.bandwidth_var.get(),
            "ctcss_tx": self.ctcss_tx_var.get(),
            "ctcss_rx": self.ctcss_rx_var.get(),
            "dcs_tx": self.dcs_tx_var.get(),
            "dcs_rx": self.dcs_rx_var.get(),
            "disable_emphasis": self.disable_emphasis_var.get(),
            "disable_highpass": self.disable_highpass_var.get(),
            "disable_lowpass": self.disable_lowpass_var.get(),
            "volume": int(self.volume_var.get()),
        }
        PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.log(f"Profile saved: {PROFILE_PATH}")

    def load_profile(self, silent: bool = False) -> None:
        if not PROFILE_PATH.exists():
            if not silent:
                messagebox.showinfo("Info", "No saved profile found")
            return
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        self.frequency_var.set(data.get("frequency", "145.070"))
        self.offset_var.set(data.get("offset", "0.6"))
        self.squelch_var.set(data.get("squelch", "4"))
        self.bandwidth_var.set(data.get("bandwidth", "Wide"))
        self.ctcss_tx_var.set(data.get("ctcss_tx", ""))
        self.ctcss_rx_var.set(data.get("ctcss_rx", ""))
        self.dcs_tx_var.set(data.get("dcs_tx", ""))
        self.dcs_rx_var.set(data.get("dcs_rx", ""))
        self.disable_emphasis_var.set(bool(data.get("disable_emphasis", True)))
        self.disable_highpass_var.set(bool(data.get("disable_highpass", True)))
        self.disable_lowpass_var.set(bool(data.get("disable_lowpass", True)))
        self.volume_var.set(int(data.get("volume", 5)))
        self.log(f"Profile loaded: {PROFILE_PATH}")

    def run_bootstrap(self) -> None:
        script = APP_DIR / "scripts" / "bootstrap_third_party.py"
        if not script.exists():
            messagebox.showerror("Error", f"Missing script: {script}")
            return

        cmd = [sys.executable, str(script), "--target", str(APP_DIR / "third_party")]
        if self.offline_bootstrap_var.get():
            cmd.append("--offline")

        def worker() -> None:
            self.log(f"Bootstrap starting: {' '.join(cmd)}")
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if proc.stdout:
                    self.log(proc.stdout.strip())
                if proc.stderr:
                    self.log(proc.stderr.strip())
                if proc.returncode == 0:
                    self.log("Bootstrap completed successfully")
                else:
                    self.log(f"Bootstrap failed with exit code {proc.returncode}")
            except Exception as exc:  # noqa: BLE001
                self.log(f"Bootstrap exception: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _opt(value: str) -> str | None:
        v = value.strip()
        return v or None


def main() -> int:
    app = HamHatControlApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
