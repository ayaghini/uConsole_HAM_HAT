# Control Tab (`MainTab`)

## Connection

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Serial Port | Read-only combobox | `port_var` -> `HamHatApp.connect()` | Holds selected COM port name for manual connect. | Pick the COM port for SA818 before pressing `Connect`. |
| Status text (right side of port row) | Label | `status_var` | Mirrors app status messages (`_set_status`). | Read current operation result/error quickly. |
| Refresh | Button | `HamHatApp.refresh_ports()` | Scans serial ports and repopulates COM list. | Click when plugging/unplugging USB serial devices. |
| Auto Identify | Button | `HamHatApp.auto_identify()` -> `auto_identify_and_connect()` | Probes all COM ports in background and connects to first SA818 found. | Use when you do not know the SA818 COM port. |
| Connect | Button | `HamHatApp.connect()` | Connects to selected COM port, then auto-applies radio profile settings. | Use after selecting a COM port. |
| Disconnect | Button | `HamHatApp.disconnect()` | Stops APRS RX monitor and disconnects serial radio link. | Use before unplugging or switching radios. |
| Read Version | Button | `HamHatApp.read_version()` | Queries SA818 firmware version and logs/statuses the response. | Use to confirm the connected module is responding. |
| Import Profile | Button | `HamHatApp.import_profile()` | Opens file picker and loads profile JSON into all tabs. | Load saved station presets/settings. |
| Export Profile | Button | `HamHatApp.export_profile()` | Opens file picker and saves current full profile snapshot to JSON. | Backup or share current configuration. |

## Radio Parameters

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Frequency (MHz) | Entry | `frequency_var` | Parsed by `collect_profile`; applied to SA818 via `apply_radio()` / connect auto-apply. | Enter operating frequency like `145.070`. |
| Offset (MHz) | Entry | `offset_var` | Parsed into `RadioConfig.offset`; used when applying radio settings. | Enter repeater shift if needed. |
| Squelch (0-8) | Entry | `squelch_var` | Parsed as int; used in `RadioConfig.squelch`. | Raise to suppress weak noise, lower for sensitivity. |
| Bandwidth | Read-only combobox | `bandwidth_var` | Mapped to SA818 mode (`Wide`=1, `Narrow`=0). | Choose channel bandwidth for your plan. |
| Apply Radio | Button | `HamHatApp.apply_radio()` | Sends current frequency/offset/squelch/bandwidth + tones/filters/volume profile to connected SA818. | Press after changing radio-related settings. |

## Audio Routing + Auto Detection

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Audio Output | Read-only combobox | `audio_out_var`, `MainTab._on_out_selected()` -> `HamHatApp.set_output_device()` | Stores output device index/name used for APRS TX/test tones. | Select the playback device feeding SA818 mic input path. |
| Audio Input | Read-only combobox | `audio_in_var`, `MainTab._on_in_selected()` -> `HamHatApp.set_input_device()` | Stores input device index/name used for APRS RX decode/capture. | Select the recording device fed by SA818 audio out. |
| Refresh Audio Devices | Button | `HamHatApp.refresh_audio_devices()` | Re-enumerates OS audio devices and repopulates both comboboxes. | Click after audio hardware changes. |
| Auto Find TX/RX Pair | Button | `HamHatApp.auto_find_audio_pair()` | Runs USB-pair auto-selection in background and updates both devices if found. | Fast way to match SA818 USB audio endpoints. |
| TX Channel Announce Sweep | Button | `HamHatApp.tx_channel_sweep()` | Plays sequence of tones (1200/1500/1800/2200 Hz), with configured PTT behavior. | Use while tracing correct TX routing/channel. |
| Auto Detect RX by Voice | Button | `HamHatApp.auto_detect_rx()` | Captures ~3s audio, estimates RMS, and suggests OS mic level (`aprs_rx_os_level_var`). | Use to quickly tune receive gain for decode quality. |
| Auto-select SA818 audio on connect | Checkbutton | `auto_audio_var` | If enabled, startup/auto-find logic attempts preferred USB audio pair automatically. | Leave enabled for stable single-radio setups. |

## PTT

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Key PTT during TX audio | Checkbutton | `ptt_enabled_var` -> `_make_ptt_config()` | Enables/disables serial-line keying during APRS TX/test tones. | Disable only for dry-run audio tests. |
| PTT Line | Read-only combobox | `ptt_line_var` | Chooses which serial control line is toggled (`RTS` or `DTR`). | Match your interface wiring. |
| PTT Active High | Checkbutton | `ptt_active_high_var` | Controls PTT polarity when toggling selected line. | Toggle if keying seems inverted. |
| PTT Pre (ms) | Entry | `ptt_pre_ms_var` | Delay between PTT key and audio playback. | Increase if first symbols are being clipped. |
| PTT Post (ms) | Entry | `ptt_post_ms_var` | Delay after audio before unkeying PTT. | Increase if tail of packet is clipped. |

## Radio Log

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Radio Log panel | `BoundedLog` | `MainTab.append_log()` via app event queue | Displays radio/general/APRS-prefixed operational logs (auto-trimmed to max lines). | Watch for connection, apply, TX/RX workflow messages and warnings. |
