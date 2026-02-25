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

## 4. First Bring-Up Workflow

1. Connect the device over USB.
2. Click `Refresh` to list ports.
3. Select serial port.
4. Click `Connect`.
5. Click `Read Version`.
6. Set frequency/offset/squelch/bandwidth.
7. Click `Apply Radio`.
8. Optional: apply filters and volume.
9. Save settings with `Save Profile`.

Expected result:
- Status changes to connected port.
- Command success messages appear in log.

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

No serial port found:
- Reconnect USB cable and click `Refresh`.
- Confirm USB serial driver is available.

Connect fails:
- Verify correct COM/tty device.
- Ensure no other program is holding the port.

No APRS decode (Windows):
- Confirm correct `Audio Input` device.
- Reduce clipping and adjust OS mic level.
- Try `Auto Find TX/RX Pair`.
- Ensure radio and modem frequencies/settings match the peer.

PTT keys but no usable decode:
- Re-check TX gain and preamble settings.
- Verify selected output path is the SA818 audio path.

Reliable TX not getting ACK:
- Validate destination callsign.
- Increase timeout/retries.
- Confirm peer auto-ACK behavior and RF path quality.

## 12. Operational Tips

- Start with conservative defaults and change one setting at a time.
- Keep a stable profile per station/device setup.
- Use test tone and announce sweep before APRS traffic when changing host audio devices.
