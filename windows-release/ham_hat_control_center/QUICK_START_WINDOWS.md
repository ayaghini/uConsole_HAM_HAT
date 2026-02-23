# uConsole HAM HAT Control Center (Windows)

This is the Windows build/test bundle for the uConsole HAM HAT control app.

## Quick Start

### Option A: Batch launcher

```bat
cd windows-release\ham_hat_control_center
run_windows.bat
```

### Option B: PowerShell launcher

```powershell
cd windows-release/ham_hat_control_center
./run_windows.ps1
```

If script execution is blocked, run once in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Build Windows EXE

```bat
cd windows-release\ham_hat_control_center
build_windows.bat
```

EXE output:

- `dist\ham-hat-control.exe`

## Notes

- This Windows package includes APRS TX/RX workflows and audio-device mapping tools.
- Requires Python 3 and internet for first-time dependency install.
- You can run third-party bootstrap from the Setup tab in the app.
- Audio playback uses selectable output devices; choose the correct USB audio endpoint in `Audio Output`.

## Device Test Flow

1. Plug in the board over USB.
2. Click `Refresh`.
3. Click `Auto Identify SA818` (or select COM port and click `Connect`).
4. Click `Read Version`.
5. Apply radio settings.
6. In `Audio Test / APRS`, enable `Key PTT during playback`.
7. Select `PTT Line` (`RTS` or `DTR`) and `PTT Active High` to match your board wiring.
8. Click `Play Test Tone` to verify TX key + audio path.
9. Click `Play APRS Packet` to send APRS-style AFSK test audio.

## APRS Tab

1. Open `APRS` tab.
2. Configure `Source`, `Destination`, and `Path`.
3. For APRS message:
   - Set `To (Message)`, `Text`, optional `Msg ID`
   - Set `TX Gain` (start with `0.12`, valid range `0.05` to `0.40`)
   - Click `Send APRS Message`
4. For APRS position:
   - Set decimal `Latitude` and `Longitude`, optional `Comment`
   - Click `Send APRS Position`
5. For receive:
   - Select `Input Device`
   - Enable `Always-on RX Monitor`
   - Set `Chunk Sec` (start with `2.0`)
   - Click `Start RX Monitor` (or use one-shot `Receive APRS`)
   - One-shot mode: set `Capture Sec` (for example `10`)
   - Click `Receive APRS`
   - Check decoded packets in `APRS Monitor`
