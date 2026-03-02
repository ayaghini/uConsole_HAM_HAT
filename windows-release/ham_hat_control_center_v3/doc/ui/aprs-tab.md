# APRS Tab (`AprsTab`)

## APRS Identity + TX Tuning

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Source | Entry | `aprs_source_var` | Used as APRS source callsign for outgoing packets and chat TX messages. | Set your station callsign-SSID (example `VA7XYZ-7`). |
| Preset `VA7AYG-00` | Button | `apply_callsign_preset("VA7AYG-00", "VA7AYG-01")` | Sets source and default message target in one click. | Quick operator preset switching. |
| Preset `VA7AYG-01` | Button | `apply_callsign_preset("VA7AYG-01", "VA7AYG-00")` | Same behavior with reversed source/target preset. | Quick peer-switch during tests. |
| Destination | Entry | `aprs_dest_var` | APRS destination field for encoded packets. | Usually leave as `APRS` unless using special destination IDs. |
| Path | Entry | `aprs_path_var` | APRS path string used when building outgoing payloads. | Set digipeater path such as `WIDE1-1`. |
| TX Gain (0.05-0.40) | Entry | `aprs_tx_gain_var` | Scales generated AFSK signal amplitude before playback. | Lower to reduce clipping; raise if packets are weak. |
| Preamble Flags (16-400) | Entry | `aprs_preamble_var` | Number of opening HDLC flags generated before payload. | Increase if receiver needs more sync lead-in. |
| TX Repeats (1-5) | Entry | `aprs_repeats_var` | Number of retransmissions per send action. | Use >1 for noisy links (at cost of airtime). |
| Re-init SA818 before APRS TX | Checkbutton | `aprs_reinit_var` | Allows reconnect/reinitialize behavior before TX when needed. | Keep enabled if hardware link can be flaky. |

## Message TX

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| To | Entry | `aprs_msg_to_var` | Destination addressee for direct APRS message payload. | Enter target callsign-SSID. |
| Message | Entry | `aprs_msg_text_var` | Message body; chunked automatically if too long. | Enter plain text to transmit. |
| Message ID (opt) | Entry | `aprs_msg_id_var` | UI field exists but TX logic currently generates IDs via `AprsEngine.new_message_id()`. | Informational/manual field; current send path does not consume it. |
| Reliable mode (ACK/retry) | Checkbutton | `aprs_reliable_var` | If enabled, sends via `send_reliable()` and waits/retries for ACK by configured policy. | Enable for important direct messages. |
| ACK Timeout (s) | Entry | `aprs_ack_timeout_var` | Timeout per reliable send attempt. | Increase for slow/weak links. |
| ACK Retries (1-10) | Entry | `aprs_ack_retries_var` | Number of reliable TX attempts before fail. | Increase if ACKs are often missed. |
| Send Message | Button | `HamHatApp.send_aprs_message()` | Validates To/Text, chunks text, sends reliable or normal payload, and appends TX chat messages. | Primary direct APRS messaging action. |

## Position TX

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Latitude (deg) | Entry | `aprs_lat_var` | Parsed to float for position packet encoding. | Enter current latitude. |
| Longitude (deg) | Entry | `aprs_lon_var` | Parsed to float for position packet encoding. | Enter current longitude. |
| Comment | Entry | `aprs_comment_var` | Included in APRS position comment text. | Add station/status note. |
| Symbol Table | Entry | `aprs_symbol_table_var` | APRS symbol table selector used in position payload. | Set per APRS symbol convention (often `/`). |
| Symbol | Entry | `aprs_symbol_var` | APRS symbol code used in position payload. | Choose icon representing station type. |
| Send Position | Button | `HamHatApp.send_aprs_position()` | Validates coordinates then sends APRS position payload. | Transmit current station position beacon. |

## RX Monitor

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Capture Sec | Entry | `aprs_rx_dur_var` | One-shot decode recording length. | Set one-shot capture window. |
| Chunk Sec | Entry | `aprs_rx_chunk_var` | Continuous monitor chunk size (`>=8s enforced on Windows`). | Tune latency vs decode reliability. |
| RX Trim (dB) slider | Scale + label | `aprs_rx_trim_var` | Applies negative gain trim before decode DSP. | Reduce overload/clipping into decoder. |
| Input Level | Label | `aprs_rx_level_var` via `set_input_level()` | Displays live normalized RX input level percentage. | Monitor receive signal level. |
| Input Clip | Label | `rx_clip_var` via `set_rx_clip()` | Shows percent of clipped samples; warns when >5%. | Detect overdriven input path. |
| OS Mic Level slider | Scale + label | `aprs_rx_os_level_var` | Stores desired Windows microphone level percentage. | Set host OS input gain target. |
| Apply OS Level | Button | `apply_os_rx_level()` -> `_apply_os_rx_level()` | Uses `pycaw` (Windows) to set system microphone scalar level. | Apply slider value to OS mixer. |
| Always-on RX Monitor | Checkbutton | `aprs_rx_auto_var`, command `on_rx_auto_toggle()` | Starts/stops continuous RX monitor immediately when toggled. | Keep enabled for passive monitoring. |
| Auto-ACK direct messages | Checkbutton | `aprs_auto_ack_var` | Enables automatic ACK TX for direct messages addressed to local call. | Enable for standards-compliant reliable exchanges. |
| One-Shot Decode | Button | `rx_one_shot()` -> `one_shot_rx()` | Records once, decodes packets from recorded WAV, logs results. | Use for quick spot checks. |
| Start Monitor | Button | `start_rx_monitor()` | Starts continuous capture/decode loop with APRS RX radio config push. | Start ongoing APRS receive monitoring. |
| Stop Monitor | Button | `stop_rx_monitor()` | Stops RX thread and restores prior radio config. | Stop monitoring or before disconnect. |
| Monitor status label | Label | `set_monitor_active()` | Displays `MONITORING` indicator while RX loop is active. | Visual confirmation that background RX is running. |

## Stations Map (Offline)

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| Offline map canvas | `AprsMapCanvas` | `add_map_point()`, pan/zoom/click handlers | Plots parsed APRS positions, supports pan/zoom, click-pick logging. | Track heard station positions locally without online tiles. |
| Clear Map | Button | `_clear_map()` | Removes plotted points and writes `Map cleared` log line. | Reset map view/history. |
| Open Last In Browser | Button | `_open_in_browser()` | Opens last plotted position in OpenStreetMap browser URL. | Jump to online map detail for most recent point. |
| Map help label | Label | static text | Documents drag/scroll/click interactions. | Reminder of map controls. |

## APRS Monitor

| Element | Type | Connected code | What it actually does | Purpose and how to use |
|---|---|---|---|---|
| APRS Monitor log | `BoundedLog` | `append_log()/aprs_log()` via APRS events | Shows APRS TX/RX/reliable/monitor logs and status lines. | Primary low-level APRS diagnostics output. |
