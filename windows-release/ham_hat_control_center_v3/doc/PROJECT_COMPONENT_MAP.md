# HAM HAT Control Center v2 - Project Component Map

This document is a fast onboarding map for developers who need to understand
the app architecture, major files, key functions, and dependency boundaries.

## 1) What this app does

Desktop control center (Tkinter) for SA818 radio modules:

- Connect/disconnect SA818 over serial.
- Apply radio config (frequency, squelch, bandwidth, tones, filters, volume).
- TX/RX APRS packets (direct, group, position, intro, ACK/retry).
- Manage contacts/groups/threaded chat.
- Manage audio routing, PTT timing/line, and diagnostics tools.

## 2) Runtime architecture

Primary pattern:

1. `HamHatApp` (UI thread) receives user actions from tab widgets.
2. UI captures current settings as plain values (`AppProfile` / `_TxSnapshot`).
3. Engine work runs in worker threads (`AprsEngine`, `RadioController`, `AudioRouter`).
4. Worker threads push typed events into a thread-safe queue.
5. UI thread drains queue every 40 ms and updates widgets.

Important rule: engine threads must not touch Tkinter objects directly.

## 3) High-level file map

### Root entry and config

- `main.py`
  - CLI entrypoint (`main()`), logging setup (`_configure_logging()`), launches `HamHatApp`.
- `requirements.txt`
  - Runtime deps: `pyserial`, `numpy`, `sounddevice`, `sv-ttk`.
  - Optional perf/system deps: `scipy` (faster APRS DSP convolution), `pycaw` (Windows mic level control).
- `functional-specification.md`
  - Functional requirements reference.
- `profiles/last_profile.json`
  - Last saved profile.
- `audio_out/`
  - Generated APRS/test WAV outputs and RX captures.

### Application shell

- `app/app.py` (`HamHatApp`)
  - Main coordinator: UI construction, callback wiring, queue dispatch, action handlers.
  - Major method groups:
    - UI/event loop: `_build_ui`, `_wire_callbacks`, `_drain_queue`, `_dispatch`
    - Radio actions: `connect`, `disconnect`, `apply_radio`, `apply_filters`, `set_volume`
    - APRS TX/RX actions: `send_aprs_message`, `send_group_message`, `send_position`, `start_rx_monitor`, `one_shot_rx`
    - Comms actions: `add_contact`, `set_group`, `delete_group`
    - Profile actions: `save_profile`, `load_profile`, `_collect_profile_snapshot`
    - Tools: `play_test_tone`, `play_manual_aprs_packet`, `run_bootstrap`, `run_two_radio_diagnostic`
- `app/app_state.py` (`AppState`)
  - Shared container for engine instances, event queue, and Tk variables.

### Engine layer (`app/engine`)

- `models.py`
  - Shared dataclasses: `RadioConfig`, `AppProfile`, `PttConfig`, `ChatMessage`, `DecodedPacket`, etc.
  - `MSG_ID_COUNTER`: thread-safe monotonic APRS message ID allocator.
- `sa818_client.py` (`SA818Client`)
  - Low-level serial protocol for SA818 (`AT+...` commands), PTT line control, tone encoding helpers.
- `radio_ctrl.py` (`RadioController`)
  - Thread-safe wrapper around `SA818Client` with config push/pop restore and connect callbacks.
- `audio_tools.py`
  - Device enumeration, compatible playback, recording/capture, WAV helpers.
- `audio_router.py` (`AudioRouter`)
  - Audio routing + PTT-aware playback orchestration.
  - Windows subprocess fallback for capture/playback worker scripts.
- `aprs_modem.py`
  - APRS/AX.25 encode/decode pipeline, payload builders/parsers, DSP helpers.
  - Position parsers include uncompressed, compressed (base91), and Mic-E decode.
- `aprs_engine.py` (`AprsEngine`)
  - APRS TX worker logic, reliable ACK/retry flow, RX monitor loop, duplicate suppression.
  - RX includes silence gate before decode; TX cleans temporary WAV files after send.
- `comms_mgr.py` (`CommsManager`)
  - Contacts, groups, heard stations, threads/unread counts, chat message storage.
- `profile.py` (`ProfileManager`)
  - Typed profile load/save with validation and clamping.

### UI layer (`app/ui`)

- `main_tab.py` (`MainTab`)
  - Connection, radio controls, audio routing selection, log panel.
- `aprs_tab.py` (`AprsTab`)
  - APRS identity/message/position, RX monitor controls, APRS monitor log, offline map.
- `comms_tab.py` (`CommsTab`)
  - Contacts, groups, heard list, thread view, compose/send, intro packet send.
- `setup_tab.py` (`SetupTab`)
  - Advanced settings: filters, tones, volume, PTT, diagnostics, profile import/export, TTS toggle.
- `widgets.py`
  - Shared UI widgets/helpers: row helper, scroll container, bounded log, waterfall, map canvas.
- `events.py`
  - Alternate typed event dataclasses (currently not the primary queue type used by `app.py`).

### Scripts (`scripts`)

- `play_wav_worker.py`, `capture_wav_worker.py`, `rx_score_worker.py`, `tx_wav_worker.py`
  - Standalone subprocess workers for Windows audio/PTT reliability.
- `bootstrap_third_party.py`
  - Installs dependencies and optional third-party tools.
- `two_radio_diagnostic.py`
  - Two-radio loop test for serial/PTT/APRS reliability.

## 4) Core data and control flow

### Direct message TX flow

1. UI button in `CommsTab` or `AprsTab` calls `HamHatApp.send_aprs_message(...)`.
2. `HamHatApp` creates `_TxSnapshot` from current profile/device selection.
3. Text is chunked (`CommsManager.build_direct_chunks`).
4. Payload built (`build_aprs_message_payload`) and sent through `AprsEngine`.
5. `AprsEngine` reconfigures radio for APRS, writes WAV, plays with PTT, restores config.

### RX monitor flow

1. `HamHatApp.start_rx_monitor()` configures APRS RX radio params.
2. `AprsEngine.start_rx_monitor()` spawns `_rx_loop` thread.
3. Audio capture -> trim -> clip/level/waterfall callbacks -> packet decode.
4. Packet events are queued to UI thread (`_PacketEvt`) and rendered in tabs.
5. Auto-ACK may trigger background ACK TX thread.
6. Very low-energy chunks are skipped to reduce decode CPU cost/noise-triggered work.

### Profile flow

1. UI values are collected from all tabs (`_collect_profile_snapshot`).
2. `ProfileManager.save()` writes validated JSON.
3. On load, `ProfileManager.load()` parses/clamps values into `AppProfile`.
4. Tabs apply profile via `apply_profile`.

## 5) External libraries and how they are used

- `pyserial`: COM/serial communication with SA818 (`SA818Client`).
- `numpy`: DSP, sample transforms, APRS modulation/demodulation helpers.
- `scipy` (optional): `fftconvolve` acceleration for APRS FIR/filter stages.
- `sounddevice`: audio device list, capture, playback.
- `tkinter` + `ttk`: desktop UI framework.
- `sv-ttk`: theme styling.
- `pycaw` (optional, Windows): OS microphone level control.

## 6) Where to add features

- New radio command/behavior:
  - Low-level protocol: `app/engine/sa818_client.py`
  - High-level thread-safe call: `app/engine/radio_ctrl.py`
  - UI action wiring: `app/app.py` + relevant tab file.
- New APRS payload type:
  - Payload format/parser: `app/engine/aprs_modem.py`
  - Send/receive workflow: `app/engine/aprs_engine.py`
  - UI controls and display: `app/ui/aprs_tab.py` or `app/ui/comms_tab.py`.
- New persisted setting:
  - Add field in `AppProfile` (`models.py`)
  - Add load/save mapping in `profile.py`
  - Add UI vars + tab apply/collect methods.
- New diagnostics tool:
  - Add script in `scripts/`
  - Add launcher action in `HamHatApp` + button in `setup_tab.py`.

## 7) Threading and safety notes

- Tkinter updates must stay on the main thread.
- Engine callbacks can run on worker threads; always marshal to queue/UI thread.
- Radio config push/pop in APRS TX/RX is critical; do not bypass restore logic.
- Avoid reading Tk variables inside worker threads; snapshot values first.

## 8) Quick start for contributors

1. Read `main.py`, `app/app.py`, `app/app_state.py`.
2. Read engine modules in this order:
   `models.py` -> `sa818_client.py` -> `radio_ctrl.py` -> `audio_router.py`
   -> `aprs_modem.py` -> `aprs_engine.py` -> `comms_mgr.py` -> `profile.py`.
3. Read UI tabs (`main_tab.py`, `aprs_tab.py`, `comms_tab.py`, `setup_tab.py`).
4. Run app and verify:
   - connect/disconnect
   - apply radio settings
   - send APRS message
   - start/stop RX monitor
   - save/load profile

## 9) AI Fast-Path (token-saving)

If an AI agent needs to move quickly, read only these files first:

1. `app/app.py` (orchestration + all user actions)
2. `app/app_state.py` (global state + engine wiring)
3. `app/engine/models.py` (all core data contracts)
4. `app/engine/aprs_engine.py` (TX/RX runtime logic)
5. `app/engine/aprs_modem.py` (APRS payload/decoder rules)
6. `app/engine/radio_ctrl.py` + `app/engine/sa818_client.py` (radio I/O boundary)
7. `app/ui/comms_tab.py`, `app/ui/aprs_tab.py`, `app/ui/main_tab.py` (UI trigger points)

That set usually gives enough context for most fixes/features without opening every file.

## 10) Task-to-file routing

- "Radio connect/config bug":
  - `app/app.py` (`connect`, `apply_radio`, `apply_filters`, `set_volume`)
  - `app/engine/radio_ctrl.py`
  - `app/engine/sa818_client.py`
- "APRS encode/decode issue":
  - `app/engine/aprs_modem.py`
  - `app/engine/aprs_engine.py`
- "Message/group/intro behavior":
  - `app/app.py` (`send_aprs_message`, `send_group_message`, `send_intro`, `_handle_packet`)
  - `app/engine/comms_mgr.py`
  - `app/ui/comms_tab.py`
- "Audio device/routing/PTT timing":
  - `app/engine/audio_router.py`
  - `app/engine/audio_tools.py`
  - `scripts/play_wav_worker.py`, `scripts/capture_wav_worker.py`
- "Profile not saving/loading":
  - `app/engine/models.py` (`AppProfile`)
  - `app/engine/profile.py`
  - tab `apply_profile` / `collect_profile` methods
- "UI visual issue / control wiring":
  - relevant file in `app/ui/*.py`
  - shared widgets in `app/ui/widgets.py`

## 11) Critical invariants (do not break)

- Tkinter updates happen on main thread only.
- Worker threads must never read/write Tk vars directly.
- APRS TX/RX temporary radio config must restore prior user config (`push_config`/`pop_config`).
- `AppProfile` field changes require synchronized updates in:
  - `models.py`
  - `profile.py` load/save mappings
  - tab `apply_profile`/`collect_profile`
- Direct/group message flow depends on `thread_key` consistency for CommsTab rendering.

## 12) High-value extension patterns

- Add new APRS payload type:
  - Build/parse in `aprs_modem.py`
  - Integrate send/receive in `app.py` + `aprs_engine.py`
  - Add UI controls in `aprs_tab.py` or `comms_tab.py`
- Add new persisted setting:
  - Add `AppProfile` field -> map in `profile.py` -> bind in tab UI.
- Add diagnostic action:
  - Add script in `scripts/` -> launch from `HamHatApp` -> button in `setup_tab.py`.

## 13) Minimal smoke test checklist

After any meaningful change:

1. App launches (`python main.py`).
2. COM ports list refresh works.
3. Connect + Read Version works.
4. Apply radio settings works.
5. Send direct APRS message triggers TX log.
6. Start/stop RX monitor works.
7. Save profile, restart app, load profile values persist.

## 14) Canonical workflows (detailed)

### A) Direct APRS message with reliable mode

1. UI send action from `CommsTab`/`AprsTab` calls `HamHatApp.send_aprs_message`.
2. `HamHatApp._send_aprs_message_impl` creates `_TxSnapshot`.
3. `CommsManager.build_direct_chunks` splits text if needed.
4. Unique message IDs generated (`AprsEngine.new_message_id`).
5. Reliable path calls `AprsEngine.send_reliable`:
   - `_do_tx` transmit attempt
   - `_wait_ack` on condition variable
   - retry loop up to configured attempts
6. RX ACK packet path:
   - packet decode in `AprsEngine._rx_loop`
   - parsed in `handle_received_packet`
   - `note_ack` resolves waiting reliable TX.

### B) Always-on RX monitor

1. Toggle in `AprsTab` calls `HamHatApp.on_rx_auto_toggle`.
2. `start_rx_monitor` builds APRS-safe `RadioConfig` and calls engine.
3. Engine applies temporary config via `push_config`.
4. `_rx_loop` captures chunk audio, computes clip/level/waterfall callbacks.
5. Packets decoded and deduplicated.
6. UI receives `_PacketEvt`; `HamHatApp._handle_packet` updates map/comms.
7. Stop restores user radio config via `pop_config`.

### C) Profile save/load cycle

1. `_collect_profile_snapshot` asks all tabs to `collect_profile`.
2. `CommsManager` contacts/groups injected into `AppProfile`.
3. `ProfileManager.save` writes JSON.
4. `ProfileManager.load` parses/clamps into typed `AppProfile`.
5. Tabs `apply_profile`, then audio device names are best-effort restored.

## 15) Event queue contract used by app.py

The active UI queue protocol in `app/app.py` uses private dataclasses:

- `_LogEvt`, `_AprsLogEvt`, `_ErrorEvt`
- `_ConnectEvt`, `_DisconnectEvt`
- `_PacketEvt`, `_AudioPairEvt`
- `_InputLevelEvt`, `_OutputLevelEvt`, `_WaterfallEvt`, `_RxClipEvt`
- `_HeardEvt`, `_ChatMsgEvt`, `_ContactsEvt`
- `_StatusEvt`, `_SuggestRxOsLevelEvt`

`app/ui/events.py` defines alternate typed event classes but `app.py` currently
uses its own internal event dataclasses.

## 16) Shared state model (high-impact vars)

`AppState` (`app/app_state.py`) is the single source for:

- Engine instances:
  - `radio`, `audio`, `aprs`, `comms`, `prof`
- Event queue:
  - `evq`
- Runtime-bound Tk vars (examples):
  - radio: `frequency_var`, `offset_var`, `squelch_var`, `bandwidth_var`
  - audio: `audio_out_var`, `audio_in_var`, `auto_audio_var`
  - ptt: `ptt_enabled_var`, `ptt_line_var`, `ptt_pre_ms_var`, `ptt_post_ms_var`
  - aprs tx: `aprs_source_var`, `aprs_dest_var`, `aprs_path_var`
  - aprs rx: `aprs_rx_chunk_var`, `aprs_rx_trim_var`, `aprs_rx_os_level_var`

## 17) Hotspots and common failure modes

- Invalid group/intro user input can raise payload validator exceptions
  unless caller wraps and reports to UI.
- Audio device mismatches:
  - output/input names can drift if OS device labels change.
- Windows audio thread-affinity:
  - playback/capture from worker threads relies on subprocess workers.
- Profile drift:
  - adding `AppProfile` fields without updating all mappings causes silent loss.
- Close path safety:
  - ensure RX monitor stop and PTT release happen cleanly during shutdown.
- APRS defaults changed:
  - default APRS preamble flags are now `60` (previously higher).

## 18) Compatibility assumptions

- Primary target platform is Windows.
- SA818 serial behavior assumes 9600 baud and expected `AT+DMOCONNECT` replies.
- APRS decode path assumes 16-bit PCM sample workflows in encode/decode helpers.

## 19) Contributor commands

- Launch app:
  - `python main.py`
- Compile sanity check:
  - `python -m compileall -q .`
- Generate AI onboarding artifacts:
  - `python scripts/generate_agent_onboarding_pack.py`

## 20) AI onboarding artifacts in this repo

- `PROJECT_COMPONENT_MAP.md` (this file): architectural narrative + task routing.
- `AGENT_CONTEXT.json`: compact machine-readable architecture summary.
- `AGENT_CODE_INDEX.json`: generated code index with modules/classes/functions.
- `AGENT_ONBOARDING_PACK.md`: generated human-readable indexed pack.

For fastest onboarding, read in this order:

1. `AGENT_CONTEXT.json`
2. `AGENT_CODE_INDEX.json` (search specific symbols)
3. `app/app.py`
4. relevant module from task routing sections above

## 21) When adding new code, keep docs aligned

If you add a new module or major feature path:

1. Update this map (`PROJECT_COMPONENT_MAP.md`) with workflow and routing.
2. Update `AGENT_CONTEXT.json` task router / invariants.
3. Regenerate onboarding pack:
   - `python scripts/generate_agent_onboarding_pack.py`

## 22) Suggested AI execution strategy

For best token efficiency and low regression risk:

1. Load `AGENT_CONTEXT.json` and this file first.
2. Open only target module group from task router.
3. Trace one complete call chain end-to-end before editing.
4. Prefer changing orchestration in `app.py` before low-level engine code.
5. Run compile/smoke checks after edits.
