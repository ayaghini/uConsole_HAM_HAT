# Quick Start (Raspberry Pi)

## 1. Copy folder to Pi

Copy this folder to Raspberry Pi:

- `pi-release/ham_hat_control_center`

## 2. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk git
```

## 3. Run app

```bash
cd ham_hat_control_center
chmod +x run_pi.sh
./run_pi.sh
```

## 4. Connect and test

1. Plug in the board over USB
2. Click `Refresh`
3. Select detected serial port
4. Click `Connect`
5. Click `Read Version`
6. Apply radio settings

## 5. Optional third-party setup

Use Setup tab -> `Run Third-Party Bootstrap`.

Or run directly:

```bash
source .venv/bin/activate
python scripts/bootstrap_third_party.py --target third_party
```

Offline mode using local snapshots:

```bash
python scripts/bootstrap_third_party.py --offline --target third_party
```
