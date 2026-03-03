# DigiRig Mobile Integration — Planning & Implementation Roadmap

**Author:** Claude Code (AI)
**Date:** 2026-03-02
**Status:** Implementation Complete (2026-03-02) — pending field testing

---

## 1. What is DigiRig Mobile?

[DigiRig Mobile](https://github.com/softcomplex/Digirig-Mobile) is an open-source,
integrated digital-mode interface for amateur radio.

| Property | Details |
|----------|---------|
| USB-to-serial chip | Silicon Labs CP2102 (device name: "Silicon Labs CP210x USB to UART Bridge") |
| PTT mechanism | Hardware: open-collector NPN transistor shorts PTT-to-GND when **RTS is HIGH (active)** |
| PTT polarity | RTS high = PTT on (same as SA818 `active_high=True`) |
| PTT line | RTS (same serial port that appears as CP210x) |
| Audio device | Windows: **"USB PnP Sound Device"** (USB audio codec, 2-channel, 48 kHz capable) |
| Radio control | **None** — DigiRig does NOT issue AT commands; user programs the radio manually |
| Connection to PC | Single USB Type-C port (power + serial + audio all in one) |
| Transceiver side | 3.5mm TRRS jacks (audio + PTT; optional CAT serial) |

### Key difference from SA818 HAT

| | SA818 HAT | DigiRig |
|-|-----------|---------|
| Serial port purpose | AT commands + PTT | PTT only |
| Radio frequency/squelch control | Yes (AT+DMOSETGROUP) | No |
| Audio | SA818's built-in USB codec | DigiRig's USB codec ("USB PnP Sound Device") |
| APRS audio path | SA818 USB audio device | DigiRig USB audio device |

---

## 2. Integration Architecture

### Concept: hardware mode flag

The app gains a **hardware mode selector** with two options:

- **SA818 HAT** (default, existing behaviour) — serial port = AT commands + PTT; full radio control
- **DigiRig** — serial port = PTT only; no radio AT control; user programs radio manually

A `hw_mode` string ("SA818" or "DigiRig") flows through:
1. `AppProfile` (persisted in JSON)
2. `AppState` tk vars
3. `_TxSnapshot` (passed to engine worker threads)
4. Engine methods (`_do_tx`, `start_rx_monitor`, `stop_rx_monitor`)

### What changes in DigiRig mode

| Layer | Change |
|-------|--------|
| `AppProfile` | Add `hardware_mode: str`, `digirig_port: str` |
| `profile.py` | Load/save new fields |
| `_TxSnapshot` | Add `hw_mode`, `ptt_serial_port` slots |
| `aprs_engine._do_tx` | Skip `push_config`/`set_filters`/`set_volume`/`pop_config`; open transient serial port for PTT |
| `aprs_engine.start_rx_monitor` | Skip `push_config`/`set_filters`; store `_rx_hw_mode` |
| `aprs_engine.stop_rx_monitor` | Skip `pop_config` when `_rx_hw_mode == "DigiRig"` |
| `audio_router.auto_select_usb_pair` | Recognise "usb pnp sound device" (DigiRig) in addition to "usb audio device" (SA818) |
| `app_state.py` | Add `hardware_mode_var`, `digirig_port_var` |
| `app.py` | Mode-aware connect, rx-monitor gate, tx-snapshot builder, apply-radio guards |
| `main_tab.py` | Mode selector combobox; DigiRig port field; hide SA818 radio params in DigiRig mode |

### PTT in DigiRig mode (transient serial)

Each TX opens the DigiRig serial port, asserts RTS for PTT, plays WAV, releases RTS, closes port.
This is a safe, stateless approach with no persistent DigiRig connection needed.

```
_do_tx (DigiRig path):
  open serial(snap.ptt_serial_port)
  → ptt_cb(True)  = serial.rts = True   (key PTT)
  → play WAV
  → ptt_cb(False) = serial.rts = False  (release PTT)
  close serial (always in finally block)
```

---

## 3. Files to Modify

| # | File | Change Summary |
|---|------|----------------|
| 1 | `app/engine/models.py` | Add `hardware_mode`, `digirig_port` to `AppProfile` |
| 2 | `app/engine/profile.py` | Load/save `hardware_mode`, `digirig_port` |
| 3 | `app/engine/aprs_engine.py` | `_TxSnapshot` new slots; `_do_tx` DigiRig path; `start/stop_rx_monitor` mode-aware |
| 4 | `app/engine/audio_router.py` | `auto_select_usb_pair` — recognise DigiRig audio device name |
| 5 | `app/app_state.py` | Add `hardware_mode_var`, `digirig_port_var` tk vars |
| 6 | `app/app.py` | Mode wiring: connect, rx monitor, tx snapshot, radio action guards |
| 7 | `app/ui/main_tab.py` | Mode selector combobox, DigiRig port field, conditional SA818 UI |

No new files are required.

---

## 4. Implementation Steps

Each step is atomic and leaves the app in a runnable state.

---

### STEP 1 — `models.py`: Add DigiRig fields to `AppProfile` [x]

**File:** `app/engine/models.py`

Add two fields at end of `AppProfile`:
```python
hardware_mode: str = "SA818"   # "SA818" or "DigiRig"
digirig_port: str = ""          # serial port for DigiRig PTT (e.g. "COM5")
```

---

### STEP 2 — `profile.py`: Persist `hardware_mode` and `digirig_port` [x]

**File:** `app/engine/profile.py`

In `_profile_to_dict`:
```python
d["hardware_mode"] = p.hardware_mode
d["digirig_port"]  = p.digirig_port
```

In `_dict_to_profile`:
```python
p.hardware_mode = str(d.get("hardware_mode", "SA818"))
p.digirig_port  = str(d.get("digirig_port", ""))
```

---

### STEP 3 — `aprs_engine.py`: Mode-aware TX and RX [x]

**File:** `app/engine/aprs_engine.py`

#### 3a — `_TxSnapshot`: add `hw_mode` and `ptt_serial_port` slots

Add to `__slots__`:
```python
"hw_mode",           # "SA818" or "DigiRig"
"ptt_serial_port",   # DigiRig PTT port (blank for SA818)
```

Add to `__init__` signature and body with defaults `hw_mode="SA818"`, `ptt_serial_port=""`.

#### 3b — `_do_tx`: DigiRig branch

Add a branch at the start of `_do_tx`:

```python
if snap.hw_mode == "DigiRig":
    _do_tx_digirig(self, payload, snap, attempt)
    return
```

Implement `_do_tx_digirig` as a helper that:
- Opens transient `serial.Serial(snap.ptt_serial_port, 9600, dsrdtr=False, rtscts=False, timeout=0.1)` for PTT
- Writes WAV and calls `play_with_ptt_blocking` with PTT callback using the transient serial
- Closes serial in `finally`
- Skips all SA818 push/pop/filters/volume calls

Or alternatively, inline the DigiRig logic with a clear `if snap.hw_mode == "DigiRig": ... else: ...` split to keep it readable.

#### 3c — `start_rx_monitor`: skip SA818 config in DigiRig mode

Add `hw_mode: str = "SA818"` parameter. Store as `self._rx_hw_mode = hw_mode`.
Wrap the `push_config` / `set_filters` calls:
```python
if hw_mode != "DigiRig":
    self._radio.push_config(aprs_radio)
    try:
        self._radio.set_filters(True, True, True)
    except Exception:
        pass
    self._aprs_log("RX monitor: SA818 squelch=0 flat filters applied")
else:
    self._aprs_log("RX monitor: DigiRig mode - listening on selected audio device")
```

#### 3d — `stop_rx_monitor`: skip pop_config in DigiRig mode

```python
if self._rx_hw_mode != "DigiRig":
    try:
        restored = self._radio.pop_config()
        if restored:
            self._aprs_log("RX monitor stopped: radio config restored")
    except Exception as exc:
        self._aprs_log(f"RX monitor restore warning: {exc}")
```

---

### STEP 4 — `audio_router.py`: DigiRig audio auto-detect [x]

**File:** `app/engine/audio_router.py`

Extend `auto_select_usb_pair` strategy 2 (unique USB pair) to also match "usb pnp sound device":
```python
USB_KEYWORDS = ("usb audio device", "usb pnp sound device", "digirig")

usb_outs = [(i, n) for i, n in outs if any(k in n.lower() for k in USB_KEYWORDS)]
usb_ins  = [(i, n) for i, n in ins  if any(k in n.lower() for k in USB_KEYWORDS)]
```

Update strategy 3 (shared token) similarly.

---

### STEP 5 — `app_state.py`: Add DigiRig tk vars [x]

**File:** `app/app_state.py`

```python
self.hardware_mode_var = tk.StringVar(value="SA818")
self.digirig_port_var  = tk.StringVar(value="")
```

---

### STEP 6 — `app.py`: Mode-aware wiring [x]

**File:** `app/app.py`

#### 6a — Mirror new state vars in `HamHatApp.__init__`
```python
self.hardware_mode_var = self.state.hardware_mode_var
self.digirig_port_var  = self.state.digirig_port_var
```

#### 6b — Add `_hw_mode()` helper
```python
def _hw_mode(self) -> str:
    return self.hardware_mode_var.get()
```

#### 6c — `connect()`: DigiRig mode informs user, skips SA818 connect
```python
def connect(self, port: str = "") -> None:
    if self._hw_mode() == "DigiRig":
        self._set_status("DigiRig mode: no SA818 connection needed. Select audio device and PTT port.")
        return
    # existing SA818 connect logic ...
```

#### 6d — `disconnect()`: DigiRig mode no-op
Wrap existing logic with `if self._hw_mode() != "DigiRig":`

#### 6e — `start_rx_monitor()`: bypass radio.connected gate in DigiRig mode; pass hw_mode
```python
def start_rx_monitor(self) -> None:
    hw = self._hw_mode()
    if hw != "DigiRig" and not self.radio.connected:
        self._set_status("Not connected"); return
    p = self._get_current_profile()
    bw = 1 if p.bandwidth.lower().startswith("w") else 0
    aprs_radio = RadioConfig(frequency=p.frequency, offset=0.0, bandwidth=bw,
                             squelch=0, ...)
    in_dev = getattr(self, "_input_dev_idx", None)
    self.aprs.start_rx_monitor(
        in_dev=in_dev, chunk_s=p.aprs_rx_chunk,
        trim_db=p.aprs_rx_trim_db, aprs_radio=aprs_radio,
        hw_mode=hw,
    )
    ...
```

#### 6f — `one_shot_rx()`: bypass radio.connected gate in DigiRig mode
```python
def one_shot_rx(self) -> None:
    if self._hw_mode() != "DigiRig" and not self.radio.connected:
        self._set_status("Not connected"); return
    ...
```

#### 6g — `apply_radio()`, `apply_filters()`, `set_volume()`, `apply_tail()`, `read_version()`: guard
Add `if self._hw_mode() == "DigiRig": self._set_status("Not available in DigiRig mode"); return` at top.

#### 6h — `_make_tx_snapshot()`: populate `hw_mode` and `ptt_serial_port`
```python
hw = self._hw_mode()
ptt_serial_port = self.digirig_port_var.get().strip() if hw == "DigiRig" else ""
return _TxSnapshot(
    ...,
    hw_mode=hw,
    ptt_serial_port=ptt_serial_port,
)
```

Also: in DigiRig mode, allow `snap` even when `radio.connected` is False (remove the `None` return guard that depends on radio connected state — currently it returns `None` if no port and reinit is off, but in DigiRig mode there's no SA818 port).

#### 6i — `auto_identify_and_connect()`: DigiRig auto-find (SA818-aware)
When in DigiRig mode, probes every serial port with `AT+DMOCONNECT` (short timeout):
- Port replies `+DMOCONNECT:0` → it is the SA818 HAT → **skip it**
- Port does not reply → SA818-negative candidate (DigiRig / other)

Among SA818-negative candidates, prefer "CP210x / Silicon Labs" descriptions (DigiRig uses CP2102).
Auto-selects if exactly one candidate; logs all choices if ambiguous.
This reliably distinguishes DigiRig from SA818 HAT even when both are connected simultaneously.

#### 6j — Profile apply/collect: wire new vars
In `_apply_profile_to_tabs`: set `hardware_mode_var` and `digirig_port_var`.
In `_collect_profile_snapshot`: read them back.

---

### STEP 7 — `main_tab.py`: DigiRig UI [x]

**File:** `app/ui/main_tab.py`

#### 7a — Hardware mode selector
Add a combobox at the top of the Connection LabelFrame:
```
Hardware Mode: [SA818 HAT ▾]   ← existing/default
               [DigiRig      ]  ← new option
```

#### 7b — DigiRig PTT port entry
Below the SA818 Serial Port row, add a conditionally-visible DigiRig row:
```
DigiRig PTT Port: [COM5      ] (shown only in DigiRig mode)
```

Bind to `self._state.digirig_port_var`.

#### 7c — Conditional SA818 controls
In DigiRig mode, disable (grey out) the SA818-specific buttons:
- Connect, Disconnect, Read Version, Auto Identify
And disable the Radio Parameters section.
Use `widget.configure(state="disabled")` or show/hide based on mode.

#### 7d — Update auto-audio checkbox label
Change "Auto-select SA818 audio on connect" to
"Auto-select USB audio pair on connect" (applies to both modes).

#### 7e — Profile apply/collect
Add `hardware_mode` and `digirig_port` to `apply_profile` and `collect_profile`.

---

## 5. Testing Checklist

After all steps are complete:

### SA818 mode (regression)
- [ ] App launches; SA818 mode selected by default
- [ ] Connect/Disconnect/Read Version work
- [ ] Apply Radio works
- [ ] APRS TX works (PTT on SA818 port)
- [ ] RX monitor starts and decodes
- [ ] Profile save/load restores SA818 mode and settings

### DigiRig mode
- [ ] Switch to DigiRig mode in UI
- [ ] Connect button shows informational message (no SA818 probe)
- [ ] Radio Parameters section disabled
- [ ] DigiRig PTT port entry visible and editable
- [ ] Auto Find TX/RX Pair finds "USB PnP Sound Device"
- [ ] APRS TX: WAV plays through DigiRig audio; RTS on DigiRig serial keyed during playback
- [ ] RX monitor: starts without radio.connected; audio captured from DigiRig device; decodes packets
- [ ] Profile save/load restores DigiRig mode + port
- [ ] One-shot RX decode works without radio.connected

---

## 6. Progress Tracker

| Step | File | Status |
|------|------|--------|
| 1 | `models.py` — AppProfile new fields | [x] DONE |
| 2 | `profile.py` — load/save | [x] DONE |
| 3 | `aprs_engine.py` — DigiRig TX/RX | [x] DONE |
| 4 | `audio_router.py` — DigiRig audio detect | [x] DONE |
| 5 | `app_state.py` — new tk vars | [x] DONE |
| 6 | `app.py` — mode wiring | [x] DONE |
| 7 | `main_tab.py` — DigiRig UI | [x] DONE |

---

*This document is updated as steps are completed. Mark steps `[x]` when done.*
