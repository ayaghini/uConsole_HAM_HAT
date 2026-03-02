# QA Verification Log

Last run date: 2026-02-27
Scope: repository-level smoke QA and runtime readiness checks.
Goal: compact, AI-friendly troubleshooting ledger.

## Run Summary

- Overall status: `PARTIAL PASS`
- Passed checks: `6`
- Failed checks: `1`
- Blocked checks: `2`
- Primary blocker: missing `sv_ttk` runtime dependency in current Python environment.

## Checks Executed

| ID | Check | Command | Result | Notes |
|---|---|---|---|---|
| Q01 | Python syntax/compile sweep | `python -m compileall -q .` | PASS | No syntax errors across repo. |
| Q02 | App CLI sanity | `python main.py --help` | PASS | Entrypoint CLI loads and help prints. |
| Q03 | Diagnostic script CLI sanity | `python scripts/two_radio_diagnostic.py --help` | PASS | Arg parser and script import path valid. |
| Q04 | Onboarding generator integrity | `python scripts/generate_agent_onboarding_pack.py` | PASS | Generated artifacts successfully. |
| Q05 | APRS/Profile smoke (non-GUI) | inline python smoke assertions | PASS | Payload build/parse, chunking, profile coercion pass. |
| Q06 | JSON artifact validity | `json.load(AGENT_CONTEXT/AGENT_CODE_INDEX)` | PASS | Artifacts parse cleanly. |
| Q07 | GUI dependency import | `python -c "import sv_ttk"` | FAIL | `ModuleNotFoundError: No module named 'sv_ttk'`. |

## Findings (ordered by severity)

### 1) High - GUI runtime currently blocked in this environment

- Symptom: `ModuleNotFoundError: No module named 'sv_ttk'`
- Impact: `main.py` cannot fully launch GUI (`HamHatApp`) until dependency is installed.
- Affected path:
  - `app/app.py` imports `sv_ttk`
  - `requirements.txt` lists `sv-ttk>=2.5.5`
- Likely cause: active interpreter environment not aligned with `requirements.txt`.
- Fix:
  - `python -m pip install -r requirements.txt`
  - then verify: `python -c "import sv_ttk; print('ok')"`

### 2) Medium - No automated tests in repository

- Symptom: no `pytest`/`unittest` test suite discovered.
- Impact: regression detection depends on manual smoke and hardware-in-loop testing.
- Recommendation:
  - add minimal non-hardware tests for:
    - APRS payload builders/parsers (`aprs_modem.py`)
    - profile validation/coercion (`profile.py`)
    - message/thread logic (`comms_mgr.py`)

## Blocked / Not Executed

| ID | Check | Reason blocked | Prerequisite |
|---|---|---|---|
| B01 | Full GUI launch smoke (`python main.py`) | `sv_ttk` missing | Install requirements in active env |
| B02 | Hardware TX/RX validation | Requires SA818 radios + COM/audio devices | Connect hardware; run `two_radio_diagnostic.py` |

## AI Troubleshooting Routes

- App fails at startup:
  1. verify deps with `requirements.txt`
  2. run `python -c "import sv_ttk, serial, sounddevice"`
  3. inspect `main.py` and `app/app.py` imports/logging
- APRS decode issues:
  1. inspect `app/engine/aprs_modem.py` and `app/engine/aprs_engine.py`
  2. run one-shot decode path (`HamHatApp.one_shot_rx`)
  3. check optional SciPy availability for performance path
- Profile/load behavior:
  1. inspect `app/engine/models.py` and `app/engine/profile.py`
  2. validate tab `collect_profile`/`apply_profile` paths

## Re-run Checklist

1. `python -m pip install -r requirements.txt`
2. `python -m compileall -q .`
3. `python -c "import sv_ttk"`
4. `python main.py --help`
5. `python scripts/generate_agent_onboarding_pack.py`
6. If hardware present: run two-radio diagnostic with explicit COM/audio params.

## Change Log

- 2026-02-27: Initial QA baseline logged.

