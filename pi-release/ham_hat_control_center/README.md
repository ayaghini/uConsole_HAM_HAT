# uConsole HAM HAT Control Center (Raspberry Pi)

This folder contains a Raspberry Pi-ready UI app to automate bring-up and SA818 control.

## What it automates

- Serial port discovery and SA818 connect test
- SA818 radio programming (frequency, offset, bandwidth, squelch)
- CTCSS or DCS tone setup
- Audio filter setup (`AT+SETFILTER`)
- Volume setup (`AT+DMOSETVOLUME`)
- Local profile save/load
- Optional bootstrap of third-party tools (SA818 + SRFRS repos)

## Folder layout

- `app/main.py`: tkinter UI app
- `app/sa818_client.py`: SA818 serial backend
- `scripts/bootstrap_third_party.py`: third-party setup automation
- `requirements.txt`: Python dependencies
- `run_pi.sh`: quick run script for Raspberry Pi
- `build_pi.sh`: optional single-binary build using PyInstaller

## Requirements on Raspberry Pi

- Raspberry Pi OS with desktop
- Python 3.9+
- `python3-venv` package installed
- USB serial access permissions

Install system prerequisites:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk git
```

## Quick start

```bash
cd pi-release/ham_hat_control_center
chmod +x run_pi.sh build_pi.sh
./run_pi.sh
```

Then in the app:

1. Connect board and click `Refresh`
2. Select port and click `Connect`
3. Click `Read Version`
4. Set frequency/offset and click `Apply Radio`
5. Set filters/volume as needed

## Third-party bootstrap

From Setup tab click `Run Third-Party Bootstrap`.

This installs `pyserial` and tries to fetch:

- `https://github.com/0x9900/SA818.git`
- `https://github.com/jumbo5566/SRFRS.git`

If network fetch fails, script tries local fallback copies from your repository `Resources/` tree.

## Optional build

```bash
cd pi-release/ham_hat_control_center
./build_pi.sh
```

Binary output:

- `dist/ham-hat-control`

## Notes

- Use either CTCSS or DCS at one time.
- DCS format is `047N` or `047I`.
- Stay within legal frequencies for your license and region.
