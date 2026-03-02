# Setup Tab (`SetupTab`)

## Advanced Radio Controls

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Disable Pre/De-emphasis | Checkbutton | `_filter_emphasis_var`; `_apply_filters()` | Sets SA818 emphasis filter disable flag when `Apply Filters` is clicked. | Use flat audio response for APRS/data work. |
| Disable High-pass Filter | Checkbutton | `_filter_highpass_var`; `_apply_filters()` | Sets SA818 high-pass disable flag on apply. | Reduce frequency shaping for modem tones. |
| Disable Low-pass Filter | Checkbutton | `_filter_lowpass_var`; `_apply_filters()` | Sets SA818 low-pass disable flag on apply. | Preserve full modem tone bandwidth. |
| Apply Filters | Button | `HamHatApp.apply_filters()` | Applies all three filter flags to connected radio immediately. | Commit filter choices to hardware. |
| Volume slider (1-8) | Scale | `_volume_var` | Stores desired SA818 volume level. | Choose radio audio volume target. |
| Set Volume | Button | `HamHatApp.set_volume()` | Applies clamped volume value to connected SA818. | Commit volume change to hardware. |
| CTCSS TX/RX | Comboboxes | `_ctcss_tx_var`, `_ctcss_rx_var`; saved in profile | Stored into profile and used when radio config is applied (`Apply Radio` or post-connect apply), not applied instantly here. | Configure access tone encode/decode for voice/repeater operation. |
| DCS TX/RX | Entries | `_dcs_tx_var`, `_dcs_rx_var`; saved in profile | Same behavior as CTCSS: persisted and consumed on next radio apply/connect apply. | Configure digital coded squelch if required. |
| Open squelch tail | Checkbutton | `_open_tail_var` | Selects desired tail behavior value for apply action. | Choose tail open/closed behavior. |
| Apply Tail | Button | `HamHatApp.apply_tail()` | Sends SA818 tail command immediately if connected. | Commit squelch-tail setting to hardware. |

## Shared Configuration Blocks

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| PTT Enabled / Line / Active High / Pre / Post | Shared checkboxes/combobox/spinboxes | Bound to shared app vars used by TX snapshot | These controls change the same PTT state used by Control tab and all TX operations. | Fine-tune keying timing/polarity from Setup view. |
| APRS TX Advanced (Re-program, Preamble, Repeats, Gain) | Shared controls | Bound to shared APRS TX vars | A second editing surface for APRS TX behavior used by message/position/group/intro sends. | Tune APRS transmit robustness and level. |
| APRS RX Advanced (Duration, Chunk, Trim, OS level) | Shared controls | Bound to shared APRS RX vars | Same values used by one-shot decode and monitor startup. | Tune RX decode behavior and gain handling. |

## Audio Tools

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Frequency (Hz) | Spinbox | `_tone_freq_var` | Sets generated test tone frequency. | Pick calibration/test frequency. |
| Duration (s) | Spinbox | `_tone_duration_var` | Sets test tone play length. | Choose test duration. |
| Play Test Tone | Button | `HamHatApp.play_test_tone()` | Generates WAV and plays it on selected output using current PTT config. | Verify TX audio path/keying. |
| Stop Audio | Button | `HamHatApp.stop_audio()` | Stops active audio playback in router and updates status. | Abort ongoing test playback. |
| Packet text | Entry | `_manual_aprs_var` | Text payload for manual APRS packet audio generation. | Set custom APRS packet body for dry run. |
| Encode & Play (no PTT) | Button | `play_manual_aprs_packet()` | Builds APRS WAV and plays it with PTT forcibly disabled. | Validate modulation/audio path without keying transmitter. |
| Run TX Channel Sweep | Button | `tx_channel_sweep()` | Runs fixed tone sweep sequence with configured PTT behavior. | Find/verify correct TX channel routing. |
| Auto-detect RX Level | Button | `auto_detect_rx()` | Captures audio, computes RMS, and suggests OS mic level value. | Fast receive gain calibration helper. |

## Profile, Diagnostics, and Optional TTS

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Save Profile... | Button | `_save_profile()` -> `save_profile(path)` | Saves full current app profile to selected JSON path. | Persist current station setup. |
| Load Profile... | Button | `_load_profile()` -> `load_profile(path)` | Loads selected profile and applies values to all tabs/comms. | Restore a previously saved setup. |
| Reset Defaults | Button | `_reset_defaults()` -> `reset_defaults()` | Resets to `AppProfile()` defaults after confirmation. | Return app to known baseline. |
| Install / Update Dependencies | Button | `run_bootstrap()` | Launches `scripts/bootstrap_third_party.py` in separate console. | Install/update required third-party components. |
| Run Two-Radio Diagnostic | Button | `run_two_radio_diagnostic()` | Launches diagnostic script in separate console. | Run multi-radio troubleshooting flow. |
| Announce received APRS messages via TTS | Checkbutton | `_tts_enabled_var`; read by `SetupTab.tts_enabled` | If enabled, received APRS messages trigger Windows SpeechSynthesizer announcement. | Audible receive notifications on Windows. |
