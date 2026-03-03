# HAM HAT Control Center v2 — QA Findings

**Date reviewed:** 2026-02-26
**Version:** 4.0 (VERSION file) / v3 app directory
**Reviewer:** Claude Code static analysis

---

## Original Bug Fixes — ALL COMPLETE ✅

| ID | Severity | Summary | Status |
|----|----------|---------|--------|
| BUG-01 | CRITICAL | Tabs received `AppState` instead of `HamHatApp` — startup crash | ✅ Fixed |
| BUG-02 | CRITICAL | `export_profile()` never wrote anything | ✅ Fixed |
| BUG-03 | CRITICAL | `import_profile()` event silently discarded | ✅ Fixed |
| BUG-04 | HIGH | `_ApplyProfileEvt` dead code | ✅ Fixed |
| BUG-05 | HIGH | Multi-chunk APRS message IDs all truncated to same value | ✅ Fixed |
| BUG-06 | HIGH | `set_input_level` and `set_rx_clip` raced on same `rx_clip_var` | ✅ Fixed |
| BUG-07 | HIGH | Reliable send from CommsTab silently fell back to fire-and-forget | ✅ Fixed |
| BUG-08 | MEDIUM | Status bar RX label never updated (always "RX: —") | ✅ Fixed |
| BUG-09 | MEDIUM | `_seen_msgs` / `_seen_direct_ids` accessed from two threads without lock | ✅ Fixed |
| BUG-10 | LOW | `apply_tail` bypassed `RadioController` lock | ✅ Fixed |
| BUG-11 | MEDIUM | `auto_detect_rx` never populated the OS mic level spinner | ✅ Fixed |
| BUG-13 | LOW | Window title said "v3" | ✅ Fixed |
| BUG-14 | LOW | `_on_close` called `_get_current_profile()` twice | ✅ Fixed |
| BUG-15 | LOW | No visual indicator that RX monitor was running | ✅ Fixed |
| BUG-18 | LOW | `BoundedLog.append()` silently failed on `state="disabled"` widgets | ✅ Fixed |

---

## APRS Modem Analysis — Findings

The following were identified by a thorough review of
[app/engine/aprs_modem.py](app/engine/aprs_modem.py) and
[app/engine/aprs_engine.py](app/engine/aprs_engine.py).
They are ordered by impact.

---

### MODEM-01 · `afsk_from_nrzi` encoder is only partially vectorized

**File:** [app/engine/aprs_modem.py](app/engine/aprs_modem.py#L106-L143)
**Severity:** MEDIUM — unnecessary CPU overhead on every TX

The outer loop in `afsk_from_nrzi` iterates over each NRZI bit in Python:

```python
for bit_idx, level in enumerate(nrzi):          # ← Python loop
    freq = MARK if level else SPACE
    t = np.arange(n, dtype=np.float64)           # ← small alloc per bit
    out[s_idx: s_idx + n] = np.sin(phase + ...)
```

For a typical 200-bit APRS frame at 48 kHz/1200 baud (`sps ≈ 40`), this
performs **200 separate numpy array allocations and trigonometric calls**.
A fully vectorized approach computes the full per-sample frequency array
with `np.repeat(freqs, sample_counts)`, accumulates phase with `np.cumsum`,
and calls `np.sin` once over the entire output — eliminating the Python loop.

**Fix:** Pre-compute frequency per sample with `np.repeat`, build a
cumulative-phase array with `np.cumsum`, then call `np.sin` once.

---

### MODEM-02 · TX writes every packet to a WAV file on disk; files are never deleted

**File:** [app/engine/aprs_engine.py](app/engine/aprs_engine.py#L218-L231)
**Severity:** MEDIUM — disk I/O latency on every TX; unbounded file growth

`_do_tx` writes `aprs_tx_N_TIMESTAMP.wav` for every TX attempt:

```python
wav_path = self._audio_dir / f"aprs_tx_{attempt}_{ts}.wav"
write_aprs_wav(wav_path, ...)
self._audio.play_with_ptt_blocking(wav_path, ...)
```

These files are **never deleted**. After many TX sessions `audio_out/`
accumulates indefinitely. The write-then-read pattern also adds a disk
round-trip of latency before PTT can be asserted.

`sounddevice.play()` accepts a NumPy array directly; the WAV file is only
needed for the subprocess WASAPI workaround. The TX subprocess
(`tx_wav_worker.py`) could accept a temp path and auto-delete after play,
or the audio data could be piped via stdin.

**Fix:** Delete TX WAV files after successful playback. Or write to a
fixed-name temp path (e.g., `aprs_tx_temp.wav`) that is overwritten each time.

---

### MODEM-03 · FIR filter kernels recomputed on every RX chunk

**File:** [app/engine/aprs_modem.py](app/engine/aprs_modem.py#L510-L556)
**Severity:** MEDIUM — 5 redundant sinc/hamming kernel computations per chunk

`_lowpass_kernel(rate, cutoff, taps)` is called fresh every RX chunk:

- `_preprocess_samples` → 2 calls (700 Hz + 2600 Hz, 101 taps each)
- `_afsk_discriminator` → 1 call per tone pair (800 Hz, 81 taps) × 3 pairs = 3 calls

Total: **5 kernel computations per chunk**, each involving `np.sinc`,
`np.hamming`, and division. The inputs (`rate`, `cutoff`, `taps`) never
change at runtime. These should be computed once and cached
(e.g., as module-level constants keyed by parameters, or precomputed in
`decode_ax25_from_samples`).

**Fix:** Cache kernels as `functools.lru_cache`-decorated or module-level
precomputed constants. The three distinct kernels (700 Hz/101t, 2600 Hz/101t,
800 Hz/81t) are fixed for the lifetime of the process.

---

### MODEM-04 · Brute-force timing/inversion/tone search — up to 1680 decode attempts per chunk

**File:** [app/engine/aprs_modem.py](app/engine/aprs_modem.py#L355-L388)
**Severity:** HIGH — primary RX CPU bottleneck

```python
for mark_hz, space_hz in tone_pairs:        # 3 pairs
    demod = _afsk_discriminator(...)
    for invert in (False, True):             # 2 polarities
        for sps in sps_candidates:           # 7 drift values
            max_off = int(round(sps))        # ~40 offsets
            for offset in range(max_off):
                levels = _extract_nrzi_levels(...)
                bits = _nrzi_to_bits(levels) # pure Python
                for frame in _extract_hdlc_frames(bits):  # pure Python
                    ...
```

Worst case: **3 × 2 × 7 × 40 = 1680 decode attempts** per chunk.
Each attempt runs `_nrzi_to_bits` and `_extract_hdlc_frames` in pure
Python over a ~38,400-bit stream (8s at 48 kHz/1200 baud).

The standard solution is a **Phase-Locked Loop (PLL)** for clock recovery:
a single O(n) pass that adapts to timing drift dynamically, used in every
production APRS decoder (Direwolf, multimon-ng, AGWPE). A PLL eliminates
the need for the 7-drift × 40-offset brute-force search, reducing the
outer loop to **3 × 2 = 6** passes.

**Fix:** Implement a simple Gardner or early-late gate PLL for clock recovery,
replacing the 7 × 40 timing search with a single adaptive pass.

---

### MODEM-05 · `np.convolve` used for large FIR convolutions; `fftconvolve` would be ~20× faster

**File:** [app/engine/aprs_modem.py](app/engine/aprs_modem.py#L523-L556)
**Severity:** MEDIUM — wasted CPU on each RX chunk decode

```python
lp_lo = np.convolve(x, _lowpass_kernel(rate, 700.0, 101), mode="same")
x = np.convolve(x, _lowpass_kernel(rate, 2600.0, 101), mode="same")
...
mark_bb = np.convolve(mark_mix, lpf, mode="same")
space_bb = np.convolve(space_mix, lpf, mode="same")
```

`np.convolve` is a direct O(n×k) algorithm. For 8s × 48 kHz = 384,000
samples with 101-tap filters, each call is ≈ 38 M multiply-adds.
There are **5 such convolutions per chunk** (2 in preprocess + 3 × 2 in
discriminator). `scipy.signal.fftconvolve` or `oaconvolve` uses FFT
overlap-add, which is O(n log n) — roughly **20× faster** for this array
size.

**Fix:** Replace `np.convolve(..., mode="same")` with
`scipy.signal.fftconvolve(..., mode="same")` (already an optional dep
via scipy) or `np.fft`-based overlap-add for the preprocess step.

---

### MODEM-06 · Pure Python list operations dominate bit-stream decoding

**File:** [app/engine/aprs_modem.py](app/engine/aprs_modem.py#L571-L634)
**Severity:** HIGH — major slowdown inside the 1680-attempt loop

The following are pure Python list operations called inside every decode
attempt over a ~38,400-bit stream:

| Function | What it does | Vectorizable with |
|---|---|---|
| `_nrzi_to_bits` | Transition → bit (38K Python iters) | `np.diff` + comparison |
| `_extract_hdlc_frames` | Flag search (38K × 8 comparisons) | `np.lib.stride_tricks` |
| `_bits_to_bytes_lsb` | Bit array → bytes (nested loop) | `np.packbits` |
| `_remove_bit_stuffing` | Walk bits, remove stuffed zeros | Numpy or Cython |

`_nrzi_to_bits` can become:
```python
arr = np.asarray(levels, dtype=np.int8)
bits = np.ones(len(arr), dtype=np.int8)
bits[1:] = (arr[1:] == arr[:-1]).astype(np.int8)
```

`_bits_to_bytes_lsb` can become:
```python
np.packbits(bits[:n], bitorder="little")
```

**Fix:** Convert all four functions to numpy operations. Combined with
MODEM-04's PLL fix, this turns the decoder from an O(n × 1680) Python
loop into a near-constant number of vectorized numpy passes.

---

### MODEM-07 · `crc16_x25` uses a nested Python bit loop; a lookup table is 8× faster

**File:** [app/engine/aprs_modem.py](app/engine/aprs_modem.py#L395-L404)
**Severity:** LOW — called on every frame during TX build and all 1680 RX decode attempts

```python
def crc16_x25(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:      # outer loop
        crc ^= byte
        for _ in range(8): # inner loop — 8 Python iters per byte
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return (~crc) & 0xFFFF
```

A 256-entry precomputed lookup table reduces this to O(n) with no inner
loop and no branching:

```python
_CRC16_TABLE = [...]   # precomputed at module load

def crc16_x25(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc = (crc >> 8) ^ _CRC16_TABLE[(crc ^ byte) & 0xFF]
    return (~crc) & 0xFFFF
```

**Fix:** Add a 256-entry precomputed CRC table at module level.

---

### MODEM-08 · Decoder only handles uncompressed APRS position formats — compressed is common

**File:** [app/engine/aprs_modem.py](app/engine/aprs_modem.py#L304-L319)
**Severity:** HIGH — silent decode failure for a large portion of live APRS traffic

`parse_aprs_position_info` only handles the uncompressed fixed-width
format (`DDMM.hhN/DDDMM.hhW`). It returns `None` for:

- **Compressed position** (base-91 encoding in 4+4 bytes) — very common
  on modern APRS networks; reduces packet size for digipeater reliability
- **Mic-E encoding** (lat/lon encoded in destination address field) — used
  by most Kenwood/Yaesu HTs and a significant fraction of APRS traffic
- **DAO extension** (sub-meter precision addendum)

On a live APRS-IS feed, roughly 30–50% of position packets use compressed
or Mic-E encoding. These will decode as messages with no map point.

**Fix:** Add compressed position parsing (base-91 decode from `!/{` and
`=/` patterns) and Mic-E parsing per the APRS 1.01 specification.

---

### MODEM-09 · `_extract_hdlc_frames` tests all consecutive flag pairs, including preamble noise

**File:** [app/engine/aprs_modem.py](app/engine/aprs_modem.py#L583-L601)
**Severity:** LOW — wastes iterations on preamble flags

```python
flags = [i for i in range(len(bits) - 7) if bits[i:i + 8] == FLAG_BITS]
for i in range(len(flags) - 1):
    start = flags[i] + 8
    end   = flags[i + 1]
    if end <= start:
        continue
    frame_bits = _remove_bit_stuffing(bits[start:end])
```

With a 120-flag preamble, `flags` will contain 120 consecutive entries
all separated by 8 bits, producing 119 consecutive zero-length candidate
frame extractions before reaching the actual frame. These are cheaply
rejected by `len(frame) >= 17`, but the bit-stuffing walk still runs on
each empty window.

**Fix:** Collapse consecutive flag runs first — find preamble start
(first flag) and preamble end (last flag before data), then extract only
frames between preamble/postamble boundaries.

---

### MODEM-10 · No Automatic Gain Control (AGC) — static `trim_db` requires manual tuning

**File:** [app/engine/aprs_engine.py](app/engine/aprs_engine.py#L424-L427)
**Severity:** MEDIUM — UX / decode reliability

The RX pipeline applies a fixed user-configured `trim_db` gain, then
`_preprocess_samples` normalizes to peak amplitude. This means the
`trim_db` setting primarily acts as a gate: signals quieter than the
`trim_db` floor are attenuated before the peak normalizer can act on them.

A simple **per-chunk RMS-based AGC** (scale the chunk to target RMS of
0.1 linear before peak normalization) would remove the need for the user
to tune `trim_db` at all and improve decode probability on signals with
varying strength.

**Fix:** In `_rx_loop` after capture, apply a simple RMS normalizer:
`gain = target_rms / (rms + epsilon); mono = np.clip(mono * gain, -1, 1)`.
Keep `trim_db` as an override for special cases.

---

### MODEM-11 · 8-second minimum RX chunk on Windows eliminates real-time decoding

**File:** [app/engine/aprs_engine.py](app/engine/aprs_engine.py#L399-L409)
**Severity:** HIGH — user experience / capture latency

On Windows, `capture_compatible` spawns a new `capture_wav_worker.py`
subprocess for each chunk. Python interpreter startup + sounddevice
initialization + WASAPI negotiation adds 0.5–2 s overhead per chunk,
making chunks shorter than 8 s unreliable. The floor is hardcoded:

```python
_WIN_MIN_CHUNK_S = 8.0
```

A packet arriving 1 second into an 8-second window is not decoded for
up to 7 more seconds. If the packet falls across a chunk boundary, it
may not be decoded until the next overlap cycle (up to 16 s later).

The root cause is Windows WASAPI thread affinity (some APIs require
COM init/teardown on the same thread). Alternatives:
- Use a **persistent dedicated capture thread** initialized at startup,
  bypassing the subprocess overhead entirely. `sounddevice` works on
  non-main threads if `PortAudio` is initialized on that thread.
- Use `pyaudio` which provides its own WASAPI path without subprocess.

**Fix:** Initialize a persistent background capture thread at `start_rx_monitor`
time and feed audio chunks from it via a `queue.Queue`, eliminating the
subprocess spawn overhead and the 8-second floor.

---

### MODEM-12 · No squelch-based capture gating — DSP runs on silence

**File:** [app/engine/aprs_engine.py](app/engine/aprs_engine.py#L398-L461)
**Severity:** LOW — CPU waste on idle channel

The RX monitor sets the SA818 to `squelch=0` (open squelch) and captures
audio continuously. Decoding is attempted on every chunk even during
dead-air silence. A simple **energy gate** — checking chunk RMS against
a noise floor threshold before running `decode_ax25_from_samples` —
would skip the expensive DSP pipeline on silent chunks.

The SA818 COS (Carrier Operated Squelch) pin is not wired to the
software in the current design. An energy-based software gate is the
practical alternative.

**Fix:** In `_rx_loop`, compute chunk RMS after capture. If below a
configurable noise threshold (e.g., `< 0.005` linear), skip
`decode_ax25_from_samples` and continue to the next chunk.

---

### MODEM-13 · `_seen_msgs` dedup key is the full packet text — large string keys in dict

**File:** [app/engine/aprs_engine.py](app/engine/aprs_engine.py#L441-L453)
**Severity:** LOW — memory efficiency

The dedup dictionary key is `pkt.text` — the full TNC2-format string
(e.g., `VA7AYG-00>APRS,WIDE1-1::VA7AYG-00 :Hello World{00001`),
which can be 100+ characters. For a busy digipeater node, 600 such
strings in `_seen_msgs` means potentially 60,000+ characters held in
memory as dict keys.

**Fix:** Use `hash(pkt.text)` (Python's built-in 64-bit hash) or a
short prefix + length as the dedup key. Add a secondary equality check
on hash collision.

---

### MODEM-14 · No integration with established APRS modem software (Direwolf / multimon-ng)

**Severity:** MEDIUM — decode performance ceiling

[Direwolf](https://github.com/wb2osz/direwolf) is an open-source,
highly optimized APRS software TNC written in C. It implements:

- Multiple simultaneous passband filters (2 decoder instances, different
  center frequencies) for better noise immunity
- Full compressed, Mic-E, and DAO position decoding
- AGWPE / KISS protocol for pipe-based integration
- Consistently higher decode rates than Python-based implementations
  on comparable hardware

The current pure-Python modem works and has zero external dependencies,
which is its primary advantage. For production amateur radio use,
Direwolf as an optional backend (when installed) would dramatically
improve decode reliability, especially for weak/noisy signals.

**Fix:** Add an optional `Direwolf`-backed `RxBackend` that reads KISS
frames from a Direwolf TCP port or named pipe. Fall back to the built-in
Python modem if Direwolf is not installed. Keep the Python modem as the
default for zero-dependency operation.

---

### MODEM-15 · TX preamble default of 240 flags ≈ 1.6 seconds is very long

**File:** [app/app_state.py](app/app_state.py) — `aprs_preamble_var = tk.StringVar(value="240")`
**Severity:** LOW — over-the-air spectrum waste; limits throughput

At 1200 baud, 240 × 8 bits / 1200 = **1.6 seconds of preamble flags**
before the actual frame. The APRS specification recommends 300 ms
(≈ 45 flags). While a longer preamble improves reliability with PTT
radios that have slow key-up times, 1.6 s is excessive for most SA818
deployments and wastes channel time.

A configurable default of 60–80 flags (400–530 ms) balances SA818
key-up time against channel efficiency. The field is already user-editable;
only the default needs adjustment.

**Fix:** Change the `aprs_preamble_var` default from `"240"` to `"60"`.
Update the `AppProfile` default accordingly in
[app/engine/models.py](app/engine/models.py).

---

## QA Checklist — Features Verified (Static Analysis)

| Feature | Status | Notes |
|---------|--------|-------|
| SA818 AT command encoding | ✅ Correct | CTCSS/DCS/frequency validation solid |
| AX.25 UI frame builder | ✅ Correct | LSB-first, bit stuffing correct |
| NRZI encode/decode | ✅ Correct | Standard implementation |
| CRC-16 X.25 | ✅ Correct | Single definition in aprs_modem.py |
| AFSK vectorized encoder | ⚠️ Partial | Bit-level loop still in Python (MODEM-01) |
| AFSK decoder | ⚠️ Slow | Brute-force timing search (MODEM-04/06) |
| Compressed position parse | ❌ Missing | Only uncompressed format (MODEM-08) |
| Mic-E position parse | ❌ Missing | See MODEM-08 |
| Dedup logic | ✅ Correct | OrderedDict time-pruning, now thread-safe |
| Profile load/save JSON | ✅ Correct | All fields validated with safe defaults |
| push/pop radio config | ✅ Correct | Try/finally in TX worker restores config |
| PTT timing | ✅ Correct | pre/post delay with configurable line polarity |
| Audio device auto-select | ✅ Correct | USB hint → single USB → shared token → lowest pair |
| Subprocess WAV workers | ✅ Correct | WASAPI thread-affinity workaround |
| Reliable messaging ACK | ✅ Correct | Condition variable, retry loop, 5-char ID |
| Auto-ACK dispatch | ✅ Correct | Separate short-lived thread, no RX lock contention |
| Group wire format | ✅ Correct | Prefix overhead subtracted from body limit |
| Intro wire format | ✅ Correct | Regex validated, lat/lon range checked |
| TTS shell injection | ✅ Safe | Single-quote escape before PS execution |
| Profile import/export | ✅ Fixed | BUG-02/03/04 |
| All tab button actions | ✅ Fixed | BUG-01 |
| RX clip indicator | ✅ Fixed | BUG-06 |
| Reliable send from Comms | ✅ Fixed | BUG-07 |
| Multi-chunk message IDs | ✅ Fixed | BUG-05 |
