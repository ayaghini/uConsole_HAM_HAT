# uConsole HAM HAT Control Center (Cross-Platform)

This folder is the Windows-ready package of the same app used for Raspberry Pi.

## Run on Windows

- `run_windows.bat` (Command Prompt)
- `run_windows.ps1` (PowerShell)

## Build on Windows

- `build_windows.bat`

## App features

- SA818 serial connect/version
- Radio setup (frequency/offset/squelch/bandwidth)
- CTCSS or DCS tone config
- Filter and volume control
- APRS send/receive (message + position + ACK)
- Comms inbox threads (direct and group)
- Intro discovery packet (`@INTRO`) with location broadcast and auto-contact/map update
- Profile save/load
- Third-party tool bootstrap (SA818 + SRFRS)

## Callsign convention for dual-device QA

- Device 1: `VA7AYG-00`
- Device 2: `VA7AYG-01`

See `QUICK_START_WINDOWS.md` for exact commands.
