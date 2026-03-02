# Agent Onboarding Pack

This file is generated. Rebuild with:
`python scripts/generate_agent_onboarding_pack.py`

## Project Snapshot

- Project: `HAM HAT Control Center v2`
- Python files indexed: `28`
- Top-level functions: `114`
- Classes: `61`
- Class methods: `284`

## Fast Read Order

- `main.py`
- `app/app.py`
- `app/app_state.py`
- `app/engine/models.py`
- `app/engine/aprs_engine.py`
- `app/engine/aprs_modem.py`
- `app/engine/radio_ctrl.py`
- `app/engine/sa818_client.py`
- `app/ui/comms_tab.py`
- `app/ui/aprs_tab.py`
- `app/ui/main_tab.py`

## Component File Lists

### app_core

- `app/__init__.py`
- `app/app.py`
- `app/app_state.py`

### engine

- `app/engine/__init__.py`
- `app/engine/aprs_engine.py`
- `app/engine/aprs_modem.py`
- `app/engine/audio_router.py`
- `app/engine/audio_tools.py`
- `app/engine/comms_mgr.py`
- `app/engine/models.py`
- `app/engine/profile.py`
- `app/engine/radio_ctrl.py`
- `app/engine/sa818_client.py`

### ui

- `app/ui/__init__.py`
- `app/ui/aprs_tab.py`
- `app/ui/comms_tab.py`
- `app/ui/events.py`
- `app/ui/main_tab.py`
- `app/ui/setup_tab.py`
- `app/ui/widgets.py`

### scripts

- `scripts/bootstrap_third_party.py`
- `scripts/capture_wav_worker.py`
- `scripts/generate_agent_onboarding_pack.py`
- `scripts/play_wav_worker.py`
- `scripts/rx_score_worker.py`
- `scripts/two_radio_diagnostic.py`
- `scripts/tx_wav_worker.py`

### entry

- `main.py`

## Class and Function Index

### app/__init__.py

- Size: `1 lines`, `0 bytes`

### app/app.py

- Module: HamHatApp — main application window.
- Size: `1247 lines`, `48990 bytes`
- Constants: `_VERSION_FILE`
- Classes:
  - `_LogEvt`  [L76]
  - `_AprsLogEvt`  [L78]
  - `_ErrorEvt`  [L80]
  - `_ConnectEvt`  [L82]
  - `_DisconnectEvt`  [L84]
  - `_PacketEvt`  [L86]
  - `_AudioPairEvt`  [L88]
  - `_InputLevelEvt`  [L90]
  - `_OutputLevelEvt`  [L92]
  - `_WaterfallEvt`  [L94]
  - `_RxClipEvt`  [L96]
  - `_HeardEvt`  [L98]
  - `_ChatMsgEvt`  [L100]
  - `_ContactsEvt`  [L102]
  - `_StatusEvt`  [L104]
  - `_SuggestRxOsLevelEvt`  [L106]
  - `HamHatApp` (tk.Tk)  [L109]
    - `__init__(self, app_dir)`  [L116]
    - `_build_ui(self)`  [L206]
    - `_wire_callbacks(self)`  [L248]
    - `_wire_comms(self)`  [L265]
    - `_drain_queue(self)`  [L276]
    - `_dispatch(self, evt)`  [L286]
    - `_vis_tick(self)`  [L349]
    - `_startup_auto_tasks(self)`  [L366]
    - `_auto_find_audio_background(self)`  [L374]
    - `connect(self, port)`  [L400]
    - `_apply_radio_after_connect(self)`  [L419]
    - `disconnect(self)`  [L423]
    - `scan_ports(self)`  [L433]
    - `auto_identify_and_connect(self)`  [L441]
    - `apply_radio(self)`  [L462]
    - `_apply_radio_config(self, p)`  [L470]
    - `apply_filters(self, emphasis, highpass, lowpass)`  [L500]
    - `set_volume(self, level)`  [L513]
    - `apply_tail(self, open_tail)`  [L526]
    - `refresh_audio_devices(self)`  [L543]
    - `auto_find_audio_pair(self)`  [L549]
    - `stop_audio(self)`  [L552]
    - `set_output_device(self, idx, name)`  [L556]
    - `set_input_device(self, idx, name)`  [L560]
    - `apply_callsign_preset(self, src, dst)`  [L568]
    - `send_aprs_message(self, to, text, reliable)`  [L572]
    - `_send_aprs_message_impl(self, to, text, reliable)`  [L584]
    - `send_direct_message(self, to, text, reliable)`  [L616]
    - `send_aprs_position(self)`  [L620]
    - `apply_os_rx_level(self)`  [L631]
    - `on_rx_auto_toggle(self)`  [L636]
    - `rx_one_shot(self)`  [L643]
    - `aprs_log(self, msg)`  [L647]
    - `send_group_message(self, group, text)`  [L651]
    - `send_position(self, lat, lon, comment)`  [L672]
    - `send_intro(self, note)`  [L687]
    - `start_rx_monitor(self)`  [L702]
    - `stop_rx_monitor(self)`  [L720]
    - `one_shot_rx(self)`  [L726]
    - `play_test_tone(self, freq, duration)`  [L737]
    - `play_manual_aprs_packet(self, text)`  [L743]
    - `tx_channel_sweep(self)`  [L771]
    - `auto_detect_rx(self)`  [L796]
    - `_handle_packet(self, pkt)`  [L832]
    - `add_contact(self, call)`  [L910]
    - `remove_contact(self, call)`  [L913]
    - `import_heard_to_contacts(self)`  [L916]
    - `clear_heard(self)`  [L919]
    - `set_group(self, name, members)`  [L923]
    - `delete_group(self, name)`  [L926]
    - `save_profile(self, path)`  [L933]
    - `load_profile(self, path)`  [L947]
    - `import_profile(self)`  [L956]
    - `export_profile(self)`  [L968]
    - `reset_defaults(self)`  [L981]
    - `_load_and_apply_profile(self)`  [L985]
    - `_apply_profile_to_tabs(self, p)`  [L989]
    - `_restore_audio_from_profile(self, p)`  [L1000]
    - `_collect_profile_snapshot(self)`  [L1015]
    - `_get_current_profile(self)`  [L1026]
    - `_autosave(self)`  [L1033]
    - `_make_tx_snapshot(self)`  [L1044]
    - `_make_ptt_config(self)`  [L1091]
    - `_apply_os_rx_level(self, level)`  [L1107]
    - `_tts_announce(self, source, text)`  [L1133]
    - `run_bootstrap(self)`  [L1163]
    - `run_two_radio_diagnostic(self)`  [L1174]
    - `refresh_ports(self)`  [L1189]
    - `auto_identify(self)`  [L1197]
    - `read_version(self)`  [L1201]
    - `_set_status(self, text)`  [L1215]
    - `_on_close(self)`  [L1223]
- Top-level functions:
  - `_read_version()`  [L64]

### app/app_state.py

- Module: AppState — shared application state (tk.Var containers + engine instances).
- Size: `77 lines`, `3497 bytes`
- Classes:
  - `AppState`  [L17]
    - `__init__(self, app_dir)`  [L20]

### app/engine/__init__.py

- Size: `1 lines`, `0 bytes`

### app/engine/aprs_engine.py

- Module: AprsEngine: manages APRS TX, RX monitor, and reliable messaging.
- Size: `620 lines`, `23930 bytes`
- Classes:
  - `_TxSnapshot`  [L57]
    - `__init__(self, source, destination, path, gain, preamble_flags, trailing_flags, repeats, out_dev, ptt, radio, volume, reinit, port)`  [L64]
  - `AprsEngine`  [L95]
    - `__init__(self, radio, audio, audio_dir)`  [L101]
    - `on_log(self, cb)`  [L137]
    - `on_aprs_log(self, cb)`  [L140]
    - `on_error(self, cb)`  [L143]
    - `on_packet(self, cb)`  [L146]
    - `on_ack_tx(self, cb)`  [L149]
    - `on_output_level(self, cb)`  [L152]
    - `on_input_level(self, cb)`  [L155]
    - `on_waterfall(self, cb)`  [L158]
    - `on_rx_clip(self, cb)`  [L161]
    - `send_payload(self, payload, snap)`  [L168]
    - `send_payload_blocking(self, payload, snap)`  [L173]
    - `_tx_worker(self, payload, snap)`  [L177]
    - `_do_tx(self, payload, snap, attempt)`  [L189]
    - `send_reliable(self, addressee, text, snap, message_id, timeout_s, retries)`  [L261]
    - `_reliable_worker(self, addressee, text, snap, message_id, timeout_s, retries)`  [L278]
    - `note_ack(self, message_id)`  [L301]
    - `_wait_ack(self, message_id, timeout_s)`  [L309]
    - `new_message_id()`  [L326]
    - `play_test_tone(self, freq_hz, duration_s, out_dev, ptt, ptt_cb)`  [L333]
    - `rx_running(self)`  [L359]
    - `start_rx_monitor(self, in_dev, chunk_s, trim_db, aprs_radio)`  [L362]
    - `stop_rx_monitor(self)`  [L389]
    - `_rx_loop(self, in_dev, chunk_s, trim_db)`  [L405]
    - `one_shot_decode(self, in_dev, duration_s, trim_db)`  [L480]
    - `handle_received_packet(self, pkt, local_calls, auto_ack, snap)`  [L520]
    - `_dispatch_auto_ack(self, addressee, msg_id, snap)`  [L585]
    - `_log(self, msg)`  [L603]
    - `_aprs_log(self, msg)`  [L607]
- Top-level functions:
  - `_apply_trim_db(mono, trim_db)`  [L616]

### app/engine/aprs_modem.py

- Module: APRS payload helpers and AX.25/AFSK modem.
- Size: `793 lines`, `27392 bytes`
- Constants: `APRS_MESSAGE_BODY_MAX, APRS_MESSAGE_TEXT_MAX, APRS_POSITION_COMMENT_MAX, FLAG_BITS, GROUP_WIRE_RE, INTRO_WIRE_RE, _CRC16_TABLE, _FLAG_ARR, _LSB_WEIGHTS`
- Top-level functions:
  - `build_ax25_ui_frame(source, destination, path_via, info)`  [L65]
  - `frame_to_bitstream(frame, preamble_flags, trailing_flags)`  [L86]
  - `nrzi_encode(bits)`  [L106]
  - `afsk_from_nrzi(nrzi, sample_rate, tx_gain)`  [L116]
  - `write_aprs_wav(path, source, destination, message, path_via, sample_rate, tx_gain, preamble_flags, trailing_flags)`  [L171]
  - `write_test_tone_wav(path, frequency_hz, seconds, sample_rate)`  [L191]
  - `build_aprs_message_payload(addressee, text, message_id)`  [L205]
  - `build_aprs_ack_payload(addressee, message_id)`  [L213]
  - `build_aprs_position_payload(lat_deg, lon_deg, comment, symbol_table, symbol)`  [L221]
  - `build_group_wire_text(group, body, part, total)`  [L238]
  - `build_intro_wire_text(callsign, lat, lon, note)`  [L256]
  - `split_text_for_group(text, group)`  [L271]
  - `split_aprs_text_chunks(text, max_len)`  [L280]
  - `_split_chunks(body, limit)`  [L285]
  - `parse_aprs_message_info(info)`  [L309]
  - `parse_aprs_position_info(info, destination)`  [L329]
  - `_parse_compressed_position(payload)`  [L360]
  - `_mic_e_digit_flag(c)`  [L382]
  - `_parse_mice_position(dest, info)`  [L391]
  - `parse_group_wire_text(text)`  [L431]
  - `parse_intro_wire_text(text)`  [L442]
  - `decode_ax25_from_wav(path)`  [L459]
  - `decode_ax25_from_samples(rate, mono)`  [L464]
  - `_build_crc16_table()`  [L504]
  - `crc16_x25(data)`  [L520]
  - `_write_pcm16_mono(path, sample_rate, data)`  [L531]
  - `_read_wav_mono(path)`  [L542]
  - `_byte_lsb(value)`  [L556]
  - `_encode_ax25_addr(value, is_last)`  [L560]
  - `_decode_addr(adr)`  [L576]
  - `_format_lat(lat)`  [L582]
  - `_format_lon(lon)`  [L590]
  - `_parse_aprs_lat(token)`  [L598]
  - `_parse_aprs_lon(token)`  [L613]
  - `_lowpass_kernel(rate, cutoff_hz, taps)`  [L631]
  - `_preprocess_samples(samples, rate)`  [L644]
  - `_afsk_discriminator(samples, rate, mark_hz, space_hz)`  [L661]
  - `_extract_nrzi_levels(demod, spb, offset, invert_tones)`  [L681]
  - `_nrzi_to_bits(levels)`  [L693]
  - `_extract_hdlc_frames(bits)`  [L706]
  - `_remove_bit_stuffing(bits)`  [L730]
  - `_bits_to_bytes_lsb(bits)`  [L755]
  - `_decode_ax25_frame(frame)`  [L763]

### app/engine/audio_router.py

- Module: AudioRouter: device selection, PTT integration, and playback management.
- Size: `279 lines`, `10522 bytes`
- Classes:
  - `AudioRouter`  [L37]
    - `__init__(self, app_dir)`  [L40]
    - `set_log_cb(self, cb)`  [L48]
    - `_log(self, msg)`  [L51]
    - `refresh_output_devices(self)`  [L59]
    - `refresh_input_devices(self)`  [L62]
    - `auto_select_usb_pair(self, out_hint, in_hint)`  [L69]
    - `worker_busy(self)`  [L139]
    - `stop_audio(self)`  [L142]
    - `play_with_ptt_blocking(self, wav_path, out_dev, ptt, ptt_cb)`  [L150]
    - `capture_compatible(self, seconds, device_index, wav_out_path)`  [L189]
    - `record_compatible(self, wav_path, seconds, device_index)`  [L221]
    - `tx_active(self)`  [L236]
    - `tx_level_hold(self)`  [L240]
- Top-level functions:
  - `_play_wav_subprocess(wav_path, device_index, app_dir)`  [L248]
  - `_capture_wav_subprocess(wav_path, seconds, device_index, app_dir)`  [L262]

### app/engine/audio_tools.py

- Module: Audio I/O helpers for playback, recording, and device enumeration.
- Size: `260 lines`, `9533 bytes`
- Top-level functions:
  - `_list_devices(direction)`  [L35]
  - `list_output_devices()`  [L86]
  - `list_input_devices()`  [L90]
  - `play_wav(path, device_index)`  [L98]
  - `play_wav_blocking(path, device_index)`  [L110]
  - `play_wav_blocking_compatible(path, device_index)`  [L122]
  - `stop_playback()`  [L169]
  - `record_wav(path, seconds, device_index, sample_rate)`  [L183]
  - `capture_samples(seconds, device_index, sample_rate)`  [L196]
  - `wav_duration_seconds(path)`  [L214]
  - `estimate_wav_level(path)`  [L221]
  - `_load_wav_as_int16(path)`  [L239]
  - `_write_pcm16_mono(path, sample_rate, data)`  [L253]

### app/engine/comms_mgr.py

- Module: CommsManager: contacts, groups, and chat thread logic.
- Size: `255 lines`, `9120 bytes`
- Classes:
  - `CommsManager`  [L23]
    - `__init__(self)`  [L26]
    - `on_contacts_changed(self, cb)`  [L45]
    - `on_message_added(self, cb)`  [L48]
    - `on_heard_changed(self, cb)`  [L51]
    - `contacts(self)`  [L59]
    - `add_contact(self, call)`  [L62]
    - `remove_contact(self, call)`  [L71]
    - `ensure_contact(self, call)`  [L80]
    - `add_heard_to_contacts(self)`  [L83]
    - `groups(self)`  [L97]
    - `set_group(self, name, members)`  [L100]
    - `delete_group(self, name)`  [L107]
    - `heard(self)`  [L119]
    - `note_heard(self, call)`  [L122]
    - `clear_heard(self)`  [L129]
    - `messages(self)`  [L139]
    - `add_message(self, msg)`  [L142]
    - `messages_for_thread(self, thread_key)`  [L149]
    - `all_thread_keys(self)`  [L152]
    - `unread_for_thread(self, thread_key)`  [L159]
    - `set_active_thread(self, thread_key)`  [L162]
    - `active_thread(self)`  [L167]
    - `last_direct_sender(self)`  [L171]
    - `set_last_direct_sender(self, call)`  [L174]
    - `build_direct_chunks(self, text)`  [L181]
    - `build_group_chunks(self, group, text)`  [L185]
    - `build_intro_payload(self, callsign, lat, lon, note)`  [L193]
    - `should_process_intro(self, src_call, lat, lon, note)`  [L200]
    - `infer_thread_key(self, src, dst, text, local_calls)`  [L211]
    - `to_dict(self)`  [L229]
    - `from_dict(self, data)`  [L235]
- Top-level functions:
  - `_norm_call(token)`  [L252]

### app/engine/models.py

- Module: Shared dataclasses, enums, and type aliases used across the engine layer.
- Size: `199 lines`, `5287 bytes`
- Constants: `MSG_ID_COUNTER`
- Classes:
  - `RadioConfig`  [L16]
    - `clone(self)`  [L26]
  - `DecodedPacket`  [L44]
  - `AprsConfig`  [L53]
  - `ReliableConfig`  [L66]
  - `PttConfig`  [L78]
  - `AudioConfig`  [L87]
  - `ChatMessage`  [L99]
  - `_MsgIdCounter`  [L113]
    - `__init__(self)`  [L114]
    - `next(self)`  [L118]
  - `AppProfile`  [L132]

### app/engine/profile.py

- Module: ProfileManager: validated load/save of AppProfile to JSON.
- Size: `193 lines`, `8492 bytes`
- Classes:
  - `ProfileManager`  [L24]
    - `__init__(self, profile_path)`  [L25]
    - `path(self)`  [L29]
    - `save(self, profile)`  [L32]
    - `load(self)`  [L37]
- Top-level functions:
  - `_profile_to_dict(p)`  [L52]
  - `_dict_to_profile(d)`  [L106]

### app/engine/radio_ctrl.py

- Module: RadioController: thread-safe radio state manager with save/restore.
- Size: `156 lines`, `5732 bytes`
- Classes:
  - `RadioController`  [L21]
    - `__init__(self)`  [L22]
    - `set_on_connect(self, cb)`  [L34]
    - `set_on_disconnect(self, cb)`  [L37]
    - `connected(self)`  [L45]
    - `client(self)`  [L49]
    - `connect(self, port, baud, timeout)`  [L56]
    - `disconnect(self)`  [L64]
    - `probe_and_connect(self, port, baud, timeout)`  [L72]
    - `apply_config(self, cfg)`  [L87]
    - `push_config(self, cfg)`  [L94]
    - `pop_config(self)`  [L106]
    - `has_saved_config(self)`  [L120]
    - `set_volume(self, level)`  [L128]
    - `set_filters(self, disable_emphasis, disable_highpass, disable_lowpass)`  [L132]
    - `set_tail(self, open_tail)`  [L136]
    - `version(self)`  [L140]
    - `set_ptt(self, enabled, line, active_high)`  [L144]
    - `release_ptt(self, line, active_high)`  [L148]

### app/engine/sa818_client.py

- Module: SA818 serial control backend.
- Size: `290 lines`, `10228 bytes`
- Constants: `CTCSS, DCS_CODES`
- Classes:
  - `SA818Error` (Exception)  [L46]
  - `SA818Client`  [L50]
    - `__init__(self)`  [L55]
    - `connected(self)`  [L64]
    - `connect(self, port, baud, timeout)`  [L67]
    - `probe(cls, port, baud, timeout)`  [L89]
    - `disconnect(self)`  [L104]
    - `_command(self, cmd, pause)`  [L117]
    - `command(self, cmd, pause)`  [L140]
    - `version(self)`  [L149]
    - `set_volume(self, level)`  [L152]
    - `set_filters(self, disable_emphasis, disable_highpass, disable_lowpass)`  [L160]
    - `set_tail(self, open_tail)`  [L167]
    - `set_radio(self, cfg)`  [L173]
    - `set_ptt(self, enabled, line, active_high)`  [L197]
    - `_release_ptt_safe(self)`  [L215]
    - `_safe_modem_lines(self)`  [L225]
    - `_flush_rx(self)`  [L235]
- Top-level functions:
  - `_validate_frequency(freq)`  [L248]
  - `_encode_tones(cfg)`  [L255]
  - `_encode_ctcss(value)`  [L267]
  - `_encode_dcs(value)`  [L280]

### app/ui/__init__.py

- Size: `1 lines`, `0 bytes`

### app/ui/aprs_tab.py

- Module: APRS Tab — TX, RX monitor, position, and map.
- Size: `301 lines`, `15147 bytes`
- Classes:
  - `AprsTab` (ttk.Frame)  [L19]
    - `__init__(self, parent, app)`  [L20]
    - `_build(self)`  [L25]
    - `_build_identity(self, parent)`  [L51]
    - `_build_message(self, parent)`  [L71]
    - `_build_position(self, parent)`  [L85]
    - `_build_rx(self, parent)`  [L97]
    - `_build_map(self, parent)`  [L147]
    - `_build_monitor(self, parent)`  [L160]
    - `aprs_log(self, msg)`  [L168]
    - `add_map_point(self, lat, lon, label)`  [L171]
    - `_clear_map(self)`  [L174]
    - `_open_in_browser(self)`  [L178]
    - `apply_profile(self, p)`  [L192]
    - `collect_profile(self, p)`  [L217]
    - `append_log(self, msg)`  [L273]
    - `set_monitor_active(self, active)`  [L277]
    - `set_input_level(self, level)`  [L281]
    - `set_output_level(self, level)`  [L286]
    - `push_waterfall(self, mono, rate)`  [L290]
    - `set_rx_clip(self, pct)`  [L295]

### app/ui/comms_tab.py

- Module: CommsTab — Contacts, Groups, Chat Threads, Intro Discovery.
- Size: `393 lines`, `16033 bytes`
- Classes:
  - `CommsTab` (ttk.Frame)  [L22]
    - `__init__(self, parent, app)`  [L25]
    - `_build(self)`  [L34]
    - `_build_left(self, parent)`  [L51]
    - `_build_right(self, parent)`  [L116]
    - `_add_contact(self)`  [L173]
    - `_remove_contact(self)`  [L178]
    - `_import_heard_to_contacts(self)`  [L186]
    - `_clear_heard(self)`  [L189]
    - `_new_group(self)`  [L196]
    - `_edit_group(self)`  [L210]
    - `_delete_group(self)`  [L229]
    - `_on_group_select(self, _e)`  [L238]
    - `_send_intro(self)`  [L253]
    - `_on_thread_select(self, _e)`  [L260]
    - `_load_thread(self, thread_key)`  [L275]
    - `_render_message(self, msg)`  [L284]
    - `_on_compose_enter(self, event)`  [L302]
    - `_send_message(self)`  [L309]
    - `on_message(self, msg)`  [L326]
    - `refresh_contacts(self)`  [L334]
    - `refresh_heard(self)`  [L354]
    - `_refresh_thread_list(self)`  [L364]
    - `apply_profile(self, p)`  [L385]
    - `collect_profile(self, p)`  [L389]

### app/ui/events.py

- Module: Typed event dataclasses for the engine→UI queue.
- Size: `124 lines`, `1921 bytes`
- Classes:
  - `LogEvent`  [L20]
  - `AprsLogEvent`  [L25]
  - `ErrorEvent`  [L30]
  - `ConnectionEvent`  [L36]
  - `PacketEvent`  [L42]
  - `MapPointEvent`  [L53]
  - `AudioPairEvent`  [L60]
  - `InputDeviceEvent`  [L66]
  - `InputLevelEvent`  [L71]
  - `OutputLevelEvent`  [L76]
  - `WaterfallEvent`  [L81]
  - `RxClipEvent`  [L87]
  - `HeardStationEvent`  [L92]
  - `ChatMessageEvent`  [L97]
  - `ContactsChangedEvent`  [L102]

### app/ui/main_tab.py

- Module: Main Tab — Radio control, connection, and audio routing.
- Size: `236 lines`, `11705 bytes`
- Classes:
  - `MainTab` (ttk.Frame)  [L19]
    - `__init__(self, parent, state)`  [L22]
    - `_build(self)`  [L29]
    - `_build_params(self, parent)`  [L51]
    - `apply_profile(self, p)`  [L134]
    - `collect_profile(self, p)`  [L146]
    - `_on_out_selected(self, _e)`  [L180]
    - `_on_in_selected(self, _e)`  [L185]
    - `refresh_audio_devices(self)`  [L194]
    - `populate_audio_devices(self, outs, ins)`  [L201]
    - `on_audio_pair(self, out_idx, out_name, in_idx, in_name)`  [L220]
    - `on_connect(self, port)`  [L227]
    - `on_disconnect(self)`  [L230]
    - `append_log(self, msg)`  [L233]

### app/ui/setup_tab.py

- Module: SetupTab — Advanced Radio, Audio Tools, Profile, Bootstrap.
- Size: `412 lines`, `18698 bytes`
- Classes:
  - `SetupTab` (ttk.Frame)  [L26]
    - `__init__(self, parent, app)`  [L29]
    - `_build(self)`  [L38]
    - `_build_left(self, parent)`  [L54]
    - `_build_right(self, parent)`  [L196]
    - `_apply_filters(self)`  [L298]
    - `_set_volume(self)`  [L305]
    - `_apply_tail(self)`  [L308]
    - `_play_test_tone(self)`  [L311]
    - `_stop_audio(self)`  [L317]
    - `_play_manual_aprs(self)`  [L320]
    - `_tx_channel_sweep(self)`  [L323]
    - `_auto_detect_rx(self)`  [L326]
    - `_save_profile(self)`  [L329]
    - `_load_profile(self)`  [L339]
    - `_reset_defaults(self)`  [L348]
    - `_bootstrap(self)`  [L353]
    - `_two_radio_diagnostic(self)`  [L356]
    - `apply_profile(self, p)`  [L363]
    - `collect_profile(self, p)`  [L386]
    - `tts_enabled(self)`  [L410]

### app/ui/widgets.py

- Module: Shared UI widget helpers and reusable components.
- Size: `320 lines`, `12534 bytes`
- Constants: `_WF_LUT`
- Classes:
  - `BoundedLog` (ScrolledText)  [L59]
    - `__init__(self, parent, **kwargs)`  [L64]
    - `append(self, msg)`  [L67]
  - `WaterfallCanvas` (tk.Canvas)  [L112]
    - `__init__(self, parent, width, height, **kwargs)`  [L115]
    - `_on_resize(self, event)`  [L126]
    - `push_spectrum(self, rate, mono)`  [L138]
    - `_spectrum_row(self, rate, mono)`  [L147]
    - `_redraw(self)`  [L175]
  - `AprsMapCanvas` (tk.Canvas)  [L189]
    - `__init__(self, parent, **kwargs)`  [L192]
    - `set_on_pick(self, cb)`  [L209]
    - `add_point(self, lat, lon, label)`  [L212]
    - `clear(self)`  [L226]
    - `last_position(self)`  [L235]
    - `_latlon_to_xy(self, lat, lon, w, h)`  [L238]
    - `_xy_to_latlon(self, x, y, w, h)`  [L245]
    - `_draw(self)`  [L254]
    - `_on_press(self, event)`  [L278]
    - `_on_drag(self, event)`  [L281]
    - `_on_release(self, event)`  [L290]
    - `_on_wheel(self, event)`  [L309]
- Top-level functions:
  - `add_row(frame, label, widget, row)`  [L19]
  - `scrollable_frame(parent)`  [L24]
  - `_build_wf_lut()`  [L89]

### main.py

- Module: HAM HAT Control Center v2 — entry point.
- Size: `63 lines`, `1805 bytes`
- Constants: `_HERE`
- Top-level functions:
  - `_configure_logging(level)`  [L19]
  - `main()`  [L30]

### scripts/bootstrap_third_party.py

- Module: Install core Python requirements and optional third-party SA818 tools.
- Size: `132 lines`, `4247 bytes`
- Constants: `REPOS, _HERE, _ROOT`
- Top-level functions:
  - `_run(cmd, cwd)`  [L31]
  - `_pip(*packages)`  [L37]
  - `install_core_requirements()`  [L41]
  - `install_pycaw()`  [L51]
  - `clone_or_pull(name, url, target_root)`  [L56]
  - `copy_local_fallback(target_root)`  [L69]
  - `install_sa818_package(target_root)`  [L83]
  - `main()`  [L90]

### scripts/capture_wav_worker.py

- Module: Capture audio from a selected input device and write a WAV — standalone subprocess worker.
- Size: `71 lines`, `2016 bytes`
- Top-level functions:
  - `_setup_path()`  [L17]
  - `parse_args()`  [L23]
  - `main()`  [L34]

### scripts/generate_agent_onboarding_pack.py

- Module: Generate AI onboarding artifacts for this repository.
- Size: `335 lines`, `10092 bytes`
- Constants: `ROOT, ROOT_FILES, SKIP_DIRS, TARGET_DIRS`
- Classes:
  - `FuncInfo`  [L28]
  - `ClassInfo`  [L38]
  - `ImportInfo`  [L49]
  - `FileInfo`  [L56]
- Top-level functions:
  - `_safe_read(path)`  [L67]
  - `_short_doc(node)`  [L71]
  - `_unparse(node)`  [L77]
  - `_decorators(node)`  [L86]
  - `_func_info(node)`  [L95]
  - `_class_info(node)`  [L115]
  - `_imports(tree)`  [L131]
  - `_constants(tree)`  [L153]
  - `analyze_python_file(path)`  [L167]
  - `iter_python_files()`  [L194]
  - `build_index()`  [L210]
  - `build_markdown(index)`  [L252]
  - `main()`  [L321]

### scripts/play_wav_worker.py

- Module: Play WAV on a specific output device — standalone subprocess worker.
- Size: `69 lines`, `2007 bytes`
- Top-level functions:
  - `_setup_path()`  [L16]
  - `parse_args()`  [L22]
  - `main()`  [L30]

### scripts/rx_score_worker.py

- Module: Capture audio and print a voice-activity score — standalone subprocess worker.
- Size: `74 lines`, `2005 bytes`
- Top-level functions:
  - `_setup_path()`  [L15]
  - `parse_args()`  [L21]
  - `voice_activity_score(samples)`  [L29]
  - `main()`  [L41]

### scripts/two_radio_diagnostic.py

- Module: Two-radio APRS TX/RX reliability diagnostic.
- Size: `264 lines`, `9802 bytes`
- Constants: `_HERE, _ROOT`
- Top-level functions:
  - `_build_radio_cfg(freq, squelch, bw)`  [L41]
  - `_serial_ptt_stress(client, loops, ptt_line, active_high)`  [L45]
  - `_record_into(path, seconds, device, rate)`  [L63]
  - `_play_wav(path, device, rate)`  [L76]
  - `_decode_wav(path, rate)`  [L85]
  - `run(args)`  [L98]
  - `_build_parser()`  [L221]
  - `main()`  [L258]

### scripts/tx_wav_worker.py

- Module: Transmit a WAV file through SA818 with explicit PTT control — standalone worker.
- Size: `128 lines`, `4516 bytes`
- Top-level functions:
  - `_setup_path()`  [L24]
  - `parse_args()`  [L30]
  - `main()`  [L54]
