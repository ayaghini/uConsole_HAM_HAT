# uConsole HAM HAT

## Important Update

- I am now considering a first production batch.
- If you are interested, please email: **va7ayg+hamhat [at] gmail [dot] com**
- Software has moved to its dedicated repository: https://github.com/ayaghini/Ham-Radio-Hat-Software
- Support this project on Patreon: https://www.patreon.com/c/VA7AYG

uConsole HAM HAT is a hardware and software project for SA818-based 2m radio control and APRS workflows.

Current repository status:
- Hardware design baseline and manufacturing notes are documented.
- A cross-platform control app exists with:
  - Raspberry Pi mode for serial/radio configuration.
  - Windows mode for full APRS TX/RX, map, and comms workflows.

## Key Capabilities

- SA818 serial discovery, connect, version read, and programming.
- Radio parameter control (frequency, offset, squelch, bandwidth, tones).
- Filter and volume control.
- Profile save/load.
- Third-party bootstrap (SA818 + SRFRS tooling).
- Windows package extras:
  - APRS message and position TX.
  - APRS RX decode (one-shot and monitor).
  - Reliable direct messaging with ACK/retry.
  - Contact/group comms with intro discovery packets.
  - Audio routing and auto-mapping utilities.
  - Offline station map with OpenStreetMap handoff.

## Repository Layout

- `docs/`: architecture, operations, manufacturing, specification, user docs.
- `pi-release/ham_hat_control_center/`: Raspberry Pi application package.
- `windows-release/ham_hat_control_center/`: Windows application package.
- `PCB/`, `CAD/`, `Components/`: design assets (see source-of-truth doc).
- `Pictures/`: project photos/screenshots.

## Quick Start

Windows:
- [windows-release/ham_hat_control_center/QUICK_START_WINDOWS.md](windows-release/ham_hat_control_center/QUICK_START_WINDOWS.md)

Raspberry Pi:
- [pi-release/ham_hat_control_center/QUICK_START.md](pi-release/ham_hat_control_center/QUICK_START.md)

## Documentation Index

- Functional specification:
  - [docs/specifications/functional-specification.md](docs/specifications/functional-specification.md)
- Full user manual:
  - [docs/user-manual.md](docs/user-manual.md)
- Source-of-truth map:
  - [docs/architecture/source-of-truth.md](docs/architecture/source-of-truth.md)
- Bring-up guide:
  - [docs/operations/bring-up.md](docs/operations/bring-up.md)
- Manufacturing readiness:
  - [docs/manufacturing/rev02-readiness.md](docs/manufacturing/rev02-readiness.md)

## Hardware Timeline

2025-10-30:
- PCB design completed for first prototype submission.

2025-11-01:
- Proof-of-concept validation completed using SA818 + SRFRS.

2025-11-11:
- Design iteration applied:
  - SMA switched to panel mount.
  - USB connector switched to horizontal.
  - BOM updated with MPNs and minor value/package refinements.

2025-12-08:
- First batch received and basic functional checks passed.

![uConsole HAM HAT first batch](Pictures/IMG_9012.jpeg)

## Safety and Compliance

- Operate only on frequencies allowed by your license and jurisdiction.
- Use proper antenna/load and avoid uncontrolled transmissions during bench tests.
- Confirm local regulations before on-air testing.
