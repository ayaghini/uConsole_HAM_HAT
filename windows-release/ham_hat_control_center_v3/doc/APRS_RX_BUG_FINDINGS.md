# APRS Interoperability Bug — Investigation Findings

**Author:** Claude Code (AI)
**Date:** 2026-03-02
**Status:** Fixes implemented (2026-03-02) — pending field testing

---

## 1. Symptom

Two identical setups (Windows app + SA818 HAT) cannot exchange APRS packets with **each other**, yet **both** can successfully send and receive with an HT (handheld transceiver).

| Path | Result |
|------|--------|
| HT → App | ✓ Decodes |
| App → HT | ✓ Decodes |
| App A → App B | ✗ Fails |
| App B → App A | ✗ Fails |

---

## 2. Key Architecture Facts (recap)

- TX audio: app generates Bell 202 AFSK WAV at `tx_gain=0.34` (≈ −9.4 dBFS) → played via SA818's USB audio codec → enters SA818 MIC input → SA818 FM-modulates and transmits
- RX audio: SA818 FM-demodulates received signal → SA818 USB audio codec → captured by app → energy gate → AGC → AX.25 decoder
- Crucially: once the **energy gate** is passed, `_preprocess_samples` applies RMS AGC to normalise to 0.25 linear — so the decoder itself is **amplitude-insensitive**. The energy gate is the only level-sensitive step.

---

## 3. Root Causes

### Bug A — CRITICAL: SA818 audio output volume never set during RX monitor

**Location:** `app/engine/aprs_engine.py` → `start_rx_monitor()`

`start_rx_monitor` calls `push_config(aprs_radio)` (issues `AT+DMOSETGROUP`) and `set_filters(True, True, True)` (issues `AT+SETFILTER`), but **never** calls `set_volume`.

The SA818's audio output level is controlled by a separate `AT+DMOSETVOLUME` command (1–8). This value is **not** saved/restored by `push_config`/`pop_config` — those only manage `DMOSETGROUP` parameters.

**Consequence:** If the user has never pressed "Apply Radio" (which calls `set_volume`) and has never done a TX (which also calls `set_volume` via `_do_tx`), the SA818's volume remains at its power-on default. The SA818 datasheet does not guarantee what that default is; in practice it can be as low as 1/8 (very quiet). The received audio from a lower-power SA818 transmitter is then too quiet to clear the energy gate.

An HT transmitting at 5 W full deviation produces much stronger received audio at the SA818's demodulator, so the audio level is high enough to pass even at low SA818 volume.

**Fix:** Call `set_volume(8)` unconditionally inside `start_rx_monitor` (SA818 mode) after `set_filters`.

---

### Bug B — CRITICAL: Energy gate applied after −12 dB trim — weak signals silently dropped

**Location:** `app/engine/aprs_engine.py` → `_rx_loop()`

Current code (simplified):
```python
mono = _apply_trim_db(mono, self._rx_trim_db)   # trim_db=-12 → multiply by 0.25
rms  = float(np.sqrt(np.mean(mono * mono)))
if rms < 0.001:
    continue  # ← silent drop
```

With `trim_db = −12` dB (the default), the raw audio is multiplied by **0.25** before the energy check. A raw RMS of **0.004** (−48 dBFS) — perfectly audible — is trimmed to **0.001** and lands exactly on the gate boundary. Anything weaker is silently discarded.

An SA818-to-SA818 link can produce received audio at −45 to −55 dBFS (typical for 0.5–2 W at moderate range), meaning legitimate packets are frequently dropped before reaching the decoder.

An HT at 5 W + 3 kHz deviation produces much higher audio levels (typically −30 to −40 dBFS) that clear the gate comfortably even after −12 dB trim.

**Fix:** Compute the RMS gate on the **raw** (pre-trim) signal. Move `_apply_trim_db` to after the gate check. The threshold 0.001 (−60 dBFS) is already conservative and is appropriate for the raw signal.

```python
rms = float(np.sqrt(np.mean(mono * mono)))
if rms < 0.001:
    continue
mono = _apply_trim_db(mono, self._rx_trim_db)
```

---

### Bug C — MODERATE: `_apply_os_rx_level` targets Windows default microphone, not the SA818 input

**Location:** `app/app.py` → `_apply_os_rx_level()`

```python
mic = AudioUtilities.GetMicrophone()   # ← Windows default microphone endpoint
```

`AudioUtilities.GetMicrophone()` returns whatever device Windows has designated as the **default recording device** in Sound Control Panel. The SA818's USB audio codec is typically **not** the default microphone — users rarely change their default mic away from their headset or webcam.

**Consequence:** The OS-level gain slider in the app adjusts the wrong device. The SA818 USB audio input level is left at whatever Windows auto-set it to when the device was first plugged in (typically 100% in Windows, but can be auto-reduced by far-field echo cancellation or "Communications" device exclusivity).

**Fix:** Enumerate `AudioUtilities.GetAllDevices()` and match the device whose friendly name matches the selected input device name (the name shown in the app's audio device dropdown). Fall back to the default mic only if no match is found.

---

### Non-issue (investigated and cleared)

| Item | Finding |
|------|---------|
| TX sample rate | `play_wav_worker.py` plays at WAV's native 48 kHz; sounddevice handles device resampling. No tone distortion. |
| `pop_config` not restoring volume/filters | After TX, volume stays at profile max (=8), filters stay flat — both are optimal for RX. No negative effect. |
| CTCSS/DCS blocking RX | RX monitor uses `ctcss_rx=None` → no tone squelch. ✓ |
| Squelch during TX | TX uses `squelch=4`; pop_config restores `squelch=0` for RX monitor. ✓ |
| First-bit NRZI assumption | Compensated by brute-force offset search in decoder. ✓ |

---

## 4. Additional Findings (2026-03-02, round 2)

### Bug D — CRITICAL: `GetAllDevices()` returns both render AND capture endpoints

**Location:** `app/app.py` → `_apply_os_rx_level()`

`pycaw.AudioUtilities.GetAllDevices()` enumerates **all** active Windows audio endpoints regardless of data flow direction. When the SA818 USB audio codec names both its output endpoint and its input endpoint identically (Windows assigns "USB Audio Device" to both the speaker side and the microphone side of many USB codecs), the substring name search matches whichever endpoint appears first in the enumeration. If the render (output) endpoint appears first, the code sets the **speaker volume** to 35% while the actual microphone input level is never touched.

This explains the PC-to-PC discrepancy: on a PC where Windows happened to name the endpoints differently (e.g. "Speakers (USB Audio Device)" vs "Microphone (USB Audio Device)"), the match is correct and the mic level is set. On a PC where both share the name "USB Audio Device", the match is wrong and the mic level is left at whatever Windows auto-configured.

**Fix:** Use the Windows MMDevice endpoint ID to distinguish data flow direction. Endpoint IDs follow the format `{0.0.X.XXXXXXXX}.{GUID}` where the third octet is `0` for render and `1` for capture. Skip confirmed render endpoints (`".0.0."` in the ID) when looking for the input device.

---

### Bug E — IMPORTANT: SA818 playback device Windows volume never controlled

**Location:** `app/app.py` — no TX volume control existed

The SA818's FM deviation is determined by the audio amplitude going into its MIC input, which in turn depends on:
1. The AFSK WAV amplitude (`aprs_tx_gain`, default 0.34 = −9.4 dBFS)
2. The Windows playback device volume for the SA818 USB codec's output endpoint

Windows auto-configures the playback volume when a USB device is first plugged in; different machines end up with different values (commonly 50–100%). A 50% vs 100% difference in Windows playback volume halves the FM deviation, which is the difference between a clean APRS signal and a barely-decodable one.

**Fix:** Add `_apply_os_tx_level(100)` called whenever an audio pair is selected or the RX monitor is started. This uses the same endpoint ID filtering as the RX fix (skips capture endpoints) and sets the SA818's output endpoint to 100%.

---

### Bug F — MINOR: Audio level control results logged to debug only

`_log.debug("OS mic level error: ...")` — these errors are invisible unless debug logging is enabled. Success just updates the status bar (immediately overwritten by the next status message).

**Fix:** Route success and error messages to `_AprsLogEvt` (visible in the APRS log panel, persistent).

---

## 4. Implemented Fixes

### Fix 1 — `aprs_engine.py`: move energy gate to pre-trim signal

In `_rx_loop`, swap the order: gate on raw RMS, then apply trim.

### Fix 2 — `aprs_engine.py`: set SA818 volume=8 in `start_rx_monitor`

After `set_filters`, add `self._radio.set_volume(8)` in SA818 mode.

### Fix 3 — `app.py`: target correct audio device in `_apply_os_rx_level`

Match the selected input device name against `AudioUtilities.GetAllDevices()` before falling back to the default microphone.

---

## 5. Testing Checklist

After fixes, test these paths:

- [ ] App A TX → App B RX (SA818 ↔ SA818, same frequency, no CTCSS)
- [ ] App B TX → App A RX
- [ ] HT → App (regression — must still decode)
- [ ] App → HT (regression — must still decode)
- [ ] RX monitor decodes without prior "Apply Radio" button press
- [ ] RX monitor decodes at low Windows input volume (10–30 %)
- [ ] Profile save/load preserves rx trim and os level settings

---

*This document is updated as fixes are validated in the field.*
