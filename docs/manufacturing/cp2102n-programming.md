# CP2102N Programming (Dual-Chip Boards)

Last updated: 2026-04-26

## 1. Confirmed Findings

- For this project/hardware flow, **Simplicity Studio v5 works** for CP2102N GPIO customization.
- In our setup, **Simplicity Studio v6 did not expose Xpress Configurator** for CP2102N workflow.
- Legacy "USBXpress Device Customization" is not the recommended path for CP2102N configuration in this project.

## 2. Goal for This Board

Program **both CP2102N chips** on each board so:

- `GPIO.0 = TX Toggle`
- `GPIO.1 = RX Toggle`
- Output type: `Open-Drain` (active-low sink LED topology)

## 3. One-Time Setup (Engineer Station)

1. Install:
   - Silicon Labs Simplicity Studio v5 (with Xpress Configurator tooling)
   - Silicon Labs CP210x VCP driver
2. Create and save a CP2102N Xpress Configurator project with the target settings above.
3. Save project and export/use the generated `*.configuration` file.
4. Obtain `cp210xsmt` from AN721 standalone manufacturing tools package.
5. Validate command help:
   - `cp210xsmt --help`

## 4. Low-Volume Manual Flow (Debug/Bring-up)

Use SS5 Xpress Configurator, connect one board, then:

1. Read/import current device settings.
2. Set GPIO0/GPIO1 as above.
3. Program device(s).
4. Verify by readback and serial traffic LED blink.

For dual CP2102N boards, prefer controlled programming (see section 6) if chips need deterministic per-chip configs.

## 5. Production CLI Flow (Recommended for 100+ Boards)

Use `cp210xsmt` with the generated `.configuration` file:

- Program + verify in one step:
  - `cp210xsmt --device-count 2 --set-and-verify-config cp2102n_led.configuration --serial-nums GUID`

Notes:

- `--device-count` is mandatory (per AN721).
- `--serial-nums GUID` auto-generates unique serial numbers.
- If both CP2102N chips use the same config, programming both together is fast and reliable.

## 6. Dual-Chip Handling Strategy

### Case A: both chips use the same config

- Use `--device-count 2`.
- Program both in one invocation.
- Log generated serial numbers per board (required for traceability).

### Case B: chips use different configs (future)

- Do **not** connect both targets in programming mode simultaneously unless fixture can map chip identity deterministically.
- Use fixture control to program one chip at a time, or separate USB path exposure per chip.

## 7. Suggested Fixture / Station Rules

1. One DUT per station cycle.
2. Confirm exactly expected count is visible before programming.
3. Run program+verify command.
4. Parse serial-number output and append to production log.
5. Mark unit PASS only on zero exit code and expected verify text.

## 8. Automation Script

Use the script:

- `docs/manufacturing/scripts/program-cp2102n-batch.ps1`

It wraps:

- expected device count checks
- `set-and-verify` invocation
- run logging with timestamped files

Example:

```powershell
powershell -ExecutionPolicy Bypass -File .\docs\manufacturing\scripts\program-cp2102n-batch.ps1 `
  -ToolPath "C:\Silabs\AN721SW\cp210xsmt.exe" `
  -ConfigPath "C:\Silabs\configs\cp2102n_led.configuration" `
  -DeviceCount 2 `
  -SerialMode GUID `
  -LogDir ".\logs\cp2102n"
```

## 9. Known Risks / Controls

- A previously programmed or locked device may fail verification in SMT flow.
- Multiple untracked devices on the same USB bus can cause mis-targeting.
- Always use controlled fixture USB topology and strict `--device-count`.

## 10. References

- AN721: USBXpress Device Configuration and Programming Guide  
  https://www.silabs.com/documents/public/application-notes/AN721.pdf
- UG205: CP2102N-EK User Guide  
  https://www.silabs.com/documents/public/user-guides/UG205-CP2102N-EK-UserGuide.pdf
- CP210x VCP Drivers  
  https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers?tab=support
