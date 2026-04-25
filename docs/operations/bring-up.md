# Bring-Up Guide

Last updated: 2026-04-24

This guide is for bring-up of the uConsole HAM HAT hardware using the current hardware repository layout.

## 1. Goal

- Verify SA818 serial control path.
- Verify audio/USB enumeration path.
- Verify Ethernet interface enumeration.
- Verify basic RF set and PTT workflow.

## 2. Required Hardware

- Assembled board (Rev04 preferred; Rev03/Rev02 supported for comparison).
- Connected SA818S module.
- Antenna or proper RF load as required.
- USB-C cable to host.
- Optional internal uConsole 4-pin path for integrated test.

## 3. Required Software

- Python 3.x
- `pyserial` package
- One of the SA818 tools bundled under `Resources/`:
  - `Resources/SRFRS/SRFRS-main/SRFRS-main/srfrs.py`
  - `Resources/SA818 programmer/SA818/sa818.py`

Install dependency:

```powershell
python -m pip install pyserial
```

Note: full Control Center app workflows were moved to:
`https://github.com/ayaghini/Ham-Radio-Hat-Software`

## 4. Identify Serial Port

On Windows, find COM port in Device Manager after plugging the board.

## 5. Basic SA818 Programming Test (SRFRS)

From repo root:

```powershell
python .\Resources\SRFRS\SRFRS-main\SRFRS-main\srfrs.py --port COM9 radio --frequency 145.070 --offset +.6
```

Expected response pattern:

- `+DMOSETGROUP:0` plus RX/TX frequencies in output.

## 6. Alternative SA818 Test (sa818 CLI)

From repo root:

```powershell
python .\Resources\SA818 programmer\SA818\sa818.py --port COM9 radio --frequency 145.070 --offset 0.6
python .\Resources\SA818 programmer\SA818\sa818.py --port COM9 filters --emphasis disable --highpass disable --lowpass disable
python .\Resources\SA818 programmer\SA818\sa818.py --port COM9 volume --level 5
```

## 7. Functional Checklist

- Serial link stable over repeated programming.
- Frequency + offset applied correctly.
- Volume command accepted.
- Filter command accepted.
- Audio device(s) enumerate from CM108B path.
- Ethernet interface enumerates from LAN9514 path.
- PTT line behavior validates in real TX/RX test.

## 8. Troubleshooting

- No serial response:
  - Confirm COM port and cable.
  - Confirm 5V/3.3V rails.
  - Try `sa818.py version` command.
- Garbled response:
  - Verify 9600 baud path.
- RF path weak/noisy:
  - Recheck filter and grounding path in active board revision.
  - For Rev04 SA818 power hardening:
    - minimum acceptable network is `+5V -> FB16 -> +5V_SA818` with `C113` close to SA818 VCC.
    - if FL7 is not populated, ensure FL7 path is shorted/0R (not left open).
- USB or Ethernet missing:
  - Recheck LAN9514, power switches (MIC2026), and decoupling population.

## 9. Safety and Compliance

- Use only frequencies permitted for your license and region.
- Validate RF output with proper antenna/load.
- Do not perform uncontrolled TX during bench debug.
