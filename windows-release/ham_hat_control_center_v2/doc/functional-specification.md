# Functional Specification

Document owner: uConsole HAM HAT project
Document version: 1.0
Last updated: 2026-02-25

## 1. Purpose

Define the required functional behavior of the uConsole HAM HAT Control Center software packages:
- Windows package: `windows-release/ham_hat_control_center`
- Raspberry Pi package: `pi-release/ham_hat_control_center`

This document reflects implemented behavior as of the date above.

## 2. Scope

In scope:
- SA818 radio serial control.
- Local UI workflows for radio configuration.
- APRS TX/RX workflows (Windows package).
- APRS comms workflows (Windows package).
- Local profile persistence.
- Third-party tool bootstrap workflow.

Out of scope:
- Cloud services and remote control APIs.
- Automatic regulatory compliance enforcement.
- Hardware manufacturing process details.

## 3. System Context

Primary components:
- SA818 radio module controlled over USB serial.
- Host computer running Python/Tkinter app (Windows or Raspberry Pi).
- Audio interface path for APRS AFSK TX/RX (Windows package full support).

Primary interfaces:
- Serial AT command path to SA818.
- Audio input/output device selection and capture/playback.
- Local filesystem profile storage (`profiles/last_profile.json`).

## 4. Platform and Dependency Requirements

Windows package:
- Python 3.x
- `pyserial`, `numpy`, `sounddevice`
- Windows audio stack for APRS audio workflows

Raspberry Pi package:
- Python 3.9+
- `pyserial`
- `python3-tk` installed on OS

## 5. User Roles

- Operator: configures radio and performs normal APRS/comms use.
- Integrator/tester: validates cable/audio routing, bootstrap, and diagnostics.

## 6. Functional Requirements

### FR-01: Application Startup and UI
- The app shall open a desktop UI with control sections relevant to the package.
- The app shall auto-load last saved profile if present.
- The app shall present operation logs for user-visible feedback.

### FR-02: Serial Port Discovery and Connection
- The app shall list available serial ports.
- The app shall allow manual connect/disconnect.
- The app shall allow SA818 version read after connection.
- Windows package shall provide an auto-identify flow that probes ports for SA818.

Acceptance:
- Connected state is shown with selected port.
- Connection/read failures are shown in UI error dialogs and log.

### FR-03: Radio Parameter Programming
- The app shall allow setting:
  - Frequency (MHz)
  - Offset (MHz)
  - Squelch
  - Bandwidth (Wide/Narrow)
  - Optional CTCSS TX/RX
  - Optional DCS TX/RX
- The app shall reject simultaneous CTCSS and DCS use.
- The app shall send valid SA818 radio configuration commands.

Acceptance:
- Successful apply logs reply from SA818.
- Invalid tone combinations produce explicit error.

### FR-04: Filter and Volume Control
- The app shall allow toggling filter flags:
  - Disable pre/de-emphasis
  - Disable high-pass
  - Disable low-pass
- The app shall allow setting SA818 volume in range 1..8.

Acceptance:
- Successful apply logs reply from SA818.
- Invalid value conversions show user error.

### FR-05: Profile Persistence
- The app shall save current UI settings to JSON profile.
- The app shall reload profile and restore saved values.
- Profile location shall be package-local: `profiles/last_profile.json`.

Windows profile shall include APRS/comms/audio/PTT settings.
Raspberry Pi profile shall include radio/filter/volume settings.

### FR-06: Third-Party Bootstrap
- The app shall provide a bootstrap action to execute `scripts/bootstrap_third_party.py`.
- The app shall support offline mode for local snapshot fallback.
- The app shall stream bootstrap output to app log.

Acceptance:
- Completion/failure state is visible in log.

### FR-07: Audio Playback and PTT Control (Windows)
- The app shall support TX audio playback on selected output device.
- The app shall optionally key PTT during playback.
- PTT options shall include:
  - Line selection (`RTS` or `DTR`)
  - Active-high toggle
  - Pre/post keying delay (ms)
- The app shall provide test tone playback.
- The app shall provide APRS test packet audio playback.

### FR-08: Audio Device Management (Windows)
- The app shall list available audio output and input devices.
- The app shall allow manual selection of TX output and RX input.
- The app shall provide auto-find TX/RX pair workflow.
- The app shall provide TX channel announce sweep.
- The app shall provide RX input auto-detection by voice activity.

### FR-09: APRS Message TX (Windows)
- The app shall build and transmit APRS message payloads.
- APRS message text length shall be constrained to APRS wire limits.
- Source, destination, and path values shall be configurable.
- TX tuning controls shall include:
  - TX gain, valid range 0.05..0.40
  - Preamble flags, valid range 16..400
  - TX repeats, valid range 1..5

### FR-10: Reliable APRS Direct Messaging (Windows)
- The app shall support reliable mode for direct APRS messages.
- Reliable mode shall:
  - Use message ID (user supplied or generated)
  - Wait for ACK
  - Retry until ACK or retry limit reached
- ACK timeout shall be configurable and > 0.
- Retry count shall be constrained to 1..10.

### FR-11: APRS Position TX and Map (Windows)
- The app shall send APRS position payloads from decimal lat/lon.
- Latitude shall be validated within -90..90.
- Longitude shall be validated within -180..180.
- The app shall plot transmitted/received positions on an offline map canvas.
- The app shall support map clear and open-last-position-in-browser actions.

### FR-12: APRS RX Decode (Windows)
- The app shall provide one-shot RX decode capture for configured duration.
- The app shall provide continuous monitor mode with configurable chunk duration.
- The app shall decode AX.25/APRS packets from captured WAV audio.
- The app shall log decoded packets to APRS monitor.
- Optional auto-ACK for direct messages shall be supported.

### FR-13: Comms Workflows (Windows)
- The app shall provide contacts management.
- The app shall track heard stations from RX activity.
- The app shall provide group definitions with CSV member entry.
- The app shall maintain thread-based inbox/chat history.
- The app shall support:
  - Send to selected contact
  - Send to selected group
  - Reply last sender
- The app shall support intro discovery broadcast (`@INTRO/...`) with location.

### FR-14: Logging and Error Handling
- User-facing operations shall log status and failure messages.
- Recoverable input/configuration failures shall show clear dialog errors.
- Background worker failures shall be surfaced to UI logs/errors.

## 7. Data Requirements

Profile storage format:
- UTF-8 JSON file.
- Backward-compatible loading using defaults when keys are absent.

Comms/APRS data:
- APRS message body limit: 67 characters (wire-level helper limit).
- Group wire format: `@GRP/GROUP[/part/total]:text` with group token `[A-Z0-9_-]{1,16}`.
- Intro wire format: `@INTRO/CALL/LAT/LON:note`.

## 8. Non-Functional Requirements

- Desktop responsiveness: long-running operations run in background threads.
- Operational observability: log panel for major actions.
- Local-only persistence by default (no remote telemetry requirement).
- Deterministic validation on key numeric fields before TX.

## 9. Constraints and Known Limitations

- Raspberry Pi package does not implement full APRS TX/RX and comms suite present in Windows package.
- Several advanced audio functions are intentionally Windows-only.
- Regulatory compliance is operator responsibility.
- Repo `.gitignore` currently excludes core hardware design directories from git tracking (see architecture source-of-truth note).

## 10. Verification Checklist

Minimum acceptance test matrix:
- Connect/disconnect/version read on SA818.
- Apply radio/filter/volume success path.
- Save/load profile and persistence check.
- Bootstrap success and offline fallback behavior.
- Windows-only:
  - APRS message TX and position TX.
  - Reliable mode ACK success and timeout path.
  - One-shot RX decode and monitor mode.
  - Contact/group/comms thread behavior.
  - Auto audio mapping and manual override.

## 11. Change Control

When behavior changes, update this document with:
- Date of change.
- Added/modified FR IDs.
- Any changed defaults, limits, or platform support boundaries.
