# User Manual

Last updated: 2026-02-25
Applies to:
- `windows-release/ham_hat_control_center`
- `pi-release/ham_hat_control_center`

## 1. What This App Does

uConsole HAM HAT Control Center provides a desktop UI to:
- Connect to SA818 radio hardware.
- Configure radio operating parameters.
- Control filters, volume, and profiles.
- Run APRS and comms workflows (Windows package).

## 2. Before You Start

Hardware:
- uConsole HAM HAT (or compatible SA818 serial/audio wiring)
- SA818 module connected
- USB cable
- Proper antenna/load for RF testing

Software:
- Windows package: Python 3, internet for initial dependency install
- Pi package: Python 3.9+, `python3-venv`, `python3-tk`, `git`

Safety:
- Operate only on legal frequencies for your license and region.
- Avoid uncontrolled TX during bench debugging.

## 3. Installation and Launch

### Windows

From repository root:
```bat
cd windows-release\ham_hat_control_center
run_windows.bat
```

Alternative PowerShell launcher:
```powershell
cd windows-release/ham_hat_control_center
./run_windows.ps1
```

If execution policy blocks script launch:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Raspberry Pi

Install prerequisites:
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk git
```

Launch app:
```bash
cd pi-release/ham_hat_control_center
chmod +x run_pi.sh
./run_pi.sh
```

## 4. Quick Start (Recommended for New Users)

### 4.1 Auto-select serial port (Windows)

1. Connect the device over USB.
2. Open the app.
3. In `Connection`, click `Refresh`.
4. Click `Auto Identify`.
5. Confirm status changes to `Connected: <COMx>`.
6. Click `Read Version` to verify SA818 response.

If `Auto Identify` does not connect:
1. Use `Refresh`.
2. Select the expected COM port manually.
3. Click `Connect`.

### 4.2 Find the correct audio output/input (Windows)

1. In `Main` tab, confirm `Audio Routing + Auto Detection` is visible.
2. Click `Refresh Audio Devices`.
3. Ensure `Auto-select SA818 audio on connect` is enabled.
4. Click `Auto Find TX/RX Pair` and wait for completion in logs.
5. Verify selected `Audio Output` and `Audio Input` fields changed to detected devices.

If auto-find cannot resolve the pair:
1. Click `TX Channel Announce Sweep`.
2. Listen on handheld and note the announced channel number that is heard correctly.
3. Set that device in `Audio Output`.
4. Click `Auto Detect RX by Voice` while transmitting voice from a handheld near the receiver.
5. Set the highest-scoring device as `Audio Input`.

### 4.3 Quick operational test

1. In `Connection`, click `Read Version`.
2. In `Radio Parameters`, set frequency/offset/squelch/bandwidth and click `Apply Radio`.
3. In `PTT`, enable `Key PTT during TX audio`.
4. In `Setup` tab, click `Play Test Tone`.
5. Confirm TX keys and tone is heard on peer receiver.
6. Save baseline with `Save Profile`.

## 5. Main Tab (Windows)

### Connection
- `Refresh`: refresh serial port list.
- `Auto Identify`: probe ports for SA818 and auto-connect.
- `Connect` / `Disconnect`.
- `Read Version`: query SA818 firmware response.

### Radio Parameters
- `Frequency (MHz)`
- `Offset (MHz)`
- `Squelch (0-8)`
- `Bandwidth`: `Wide` or `Narrow`
- `Apply Radio`

Tone rule:
- Use either CTCSS or DCS, not both.

### Audio Routing + Auto Detection
- `Audio Output`: TX output device.
- `Audio Input`: RX capture device.
- `Refresh Audio Devices`.
- `Auto Find TX/RX Pair`: attempts decode-based pairing.
- `TX Channel Announce Sweep`: announces channel index over TX.
- `Auto Detect RX by Voice`: scores RX input by voice activity.
- `Auto-select SA818 audio on connect`.

### PTT
- `Key PTT during TX audio`
- `PTT Line`: `RTS` or `DTR`
- `PTT Active High`
- `PTT Pre (ms)` and `PTT Post (ms)`

## 6. APRS Tab (Windows)

### Identity + TX Tuning
- `Source`, `Destination`, `Path`
- `TX Gain` valid range: `0.05` to `0.40`
- `Preamble Flags` valid range: `16` to `400`
- `TX Repeats` valid range: `1` to `5`
- `Re-init SA818 before APRS TX`

### APRS Message Send
- Fill `To (Message)` and `Text`.
- Optional message ID.
- Click `Send APRS Message`.

Reliable mode:
- Enable reliable send checkbox.
- Set `ACK timeout` (>0 seconds).
- Set retries (`1` to `10`).
- App retransmits until ACK or retry limit.

### APRS Position Send
- Set decimal latitude/longitude.
- Add optional comment.
- Click `Send Position`.

### RX Monitor
- `Capture Sec` for one-shot decode.
- `Chunk Sec` for monitor loop.
- `RX Trim (dB)` controls decode preprocessing level.
- `OS Mic Level` can be applied from UI.
- `Always-on RX Monitor` keeps monitor running.
- `Auto-ACK direct messages` sends ACK replies automatically.

Buttons:
- `One-Shot Decode`
- `Start Monitor`
- `Stop Monitor`

### Map and Monitor Panels
- Offline map plots TX/RX positions.
- Drag/pan and mouse-wheel zoom supported.
- `Open Last In Browser` opens last point in OpenStreetMap.
- APRS monitor panel shows decoded traffic and TX logs.

## 7. Comms Tab (Windows)

### Contacts
- Add/remove direct contacts.
- Select contact to target direct message.

### Heard Stations
- Recently heard callsigns are listed from RX traffic.
- `Add Heard To Contacts` copies selected entries to contacts.

### Groups
- Group name plus CSV members.
- `Save Group` stores local group definition.
- Group messages are sent as APRS group wire payloads.

### Inbox and Chat
- Threaded inbox per direct/group thread.
- Unread count per thread.
- Styled chat history for TX/RX/system messages.

### Compose and Discovery
- `Send To Selected Contact`
- `Send To Group`
- `Reply Last RX`
- `Broadcast Intro + Location` sends intro packet (`@INTRO/...`) and updates peer/map state.

## 8. Setup Tab

### Advanced Radio
- CTCSS/DCS entries.
- Filter checkboxes.
- Volume slider.
- `Apply Radio (With Tone)`, `Apply Filters`, `Apply Volume`.

### Audio + Profile Tools (Windows)
- `Play Test Tone`
- `Play APRS Packet (Message)`
- `Stop Audio`
- `Save Profile`
- `Load Profile`

### Third-Party Bootstrap
- Optional offline mode checkbox.
- `Run Third-Party Bootstrap` installs/syncs SA818/SRFRS tools.

## 9. Raspberry Pi UI Differences

Pi package includes:
- Serial connect/disconnect/version
- Radio configuration
- Tone/filter/volume controls
- Save/load profile
- Third-party bootstrap

Pi package does not include full Windows APRS/comms/audio mapping suite.

## 10. Profiles

Profile file path:
- Windows: `windows-release/ham_hat_control_center/profiles/last_profile.json`
- Pi: `pi-release/ham_hat_control_center/profiles/last_profile.json`

Recommended practice:
- Save a known-good profile after first successful on-air or bench validation.

## 11. Troubleshooting

### 11.1 Serial / Port Issues

No serial port found:
- Reconnect USB cable and click `Refresh`.
- Confirm USB serial driver is available.
- Try a different USB cable/port.

Connect fails:
- Verify correct COM/tty device.
- Ensure no other program is holding the port.
- Use `Auto Identify` first, then manual `Connect` as fallback.
- Power-cycle device and retry.

`Auto Identify` shows no SA818:
- Confirm SA818 module is installed and powered.
- Confirm serial path wiring is correct.
- Try manual port selection and `Read Version`.

### 11.2 Audio Input/Output Mapping (Windows)

`Auto Find TX/RX Pair` fails:
- Ensure radio is connected first.
- Stop any active playback/record jobs, then retry.
- Click `Refresh Audio Devices`.
- Select likely USB audio devices manually and retest.
- Use `TX Channel Announce Sweep` to identify a valid TX output.
- Use `Auto Detect RX by Voice` to identify a valid RX input.

No APRS decode (Windows):
- Confirm correct `Audio Input` device.
- Reduce clipping and adjust OS mic level.
- Try `Auto Find TX/RX Pair`.
- Ensure radio and modem frequencies/settings match the peer.
- Increase preamble flags and retry.

PTT keys but no usable decode:
- Re-check TX gain and preamble settings.
- Verify selected output path is the SA818 audio path.
- Verify `PTT Line` (`RTS`/`DTR`) and `PTT Active High` match wiring.

Reliable TX not getting ACK:
- Validate destination callsign.
- Increase timeout/retries.
- Confirm peer auto-ACK behavior and RF path quality.

### 11.3 Common UI/Workflow Issues

`Apply OS Level` fails:
- Select an `Audio Input` first.

Cannot run APRS/audio tools:
- These advanced workflows are Windows-only in current release.

Bootstrap issues:
- Retry with network access enabled.
- If offline, enable bootstrap offline mode and retry.

## 12. Operational Tips

- Start with conservative defaults and change one setting at a time.
- Keep a stable profile per station/device setup.
- Use test tone and announce sweep before APRS traffic when changing host audio devices.
