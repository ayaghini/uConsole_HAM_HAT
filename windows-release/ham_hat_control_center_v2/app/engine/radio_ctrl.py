#!/usr/bin/env python3
"""RadioController: thread-safe radio state manager with save/restore.

Wraps SA818Client and adds:
- Saved/restore radio config so TX and RX operations can change params and
  put them back when done.
- Auto-connect on probe.
- Connection event callbacks (called on calling thread — caller must marshal
  to UI thread if needed).
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from .models import RadioConfig
from .sa818_client import SA818Client, SA818Error


class RadioController:
    def __init__(self) -> None:
        self._client = SA818Client()
        self._lock = threading.RLock()
        self._config_stack: list[RadioConfig] = []  # LIFO; replaces single _saved_config slot
        self._current_config: Optional[RadioConfig] = None
        self._on_connect_cb: Optional[Callable[[str], None]] = None
        self._on_disconnect_cb: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------
    # Callbacks (registered by UI; must be called on worker thread)
    # ------------------------------------------------------------------

    def set_on_connect(self, cb: Callable[[str], None]) -> None:
        self._on_connect_cb = cb

    def set_on_disconnect(self, cb: Callable[[], None]) -> None:
        self._on_disconnect_cb = cb

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._client.connected

    @property
    def client(self) -> SA818Client:
        return self._client

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, port: str, baud: int = 9600, timeout: float = 2.0) -> None:
        with self._lock:
            self._client.connect(port, baud=baud, timeout=timeout)
            self._config_stack.clear()
            self._current_config = None
        if self._on_connect_cb:
            self._on_connect_cb(port)

    def disconnect(self) -> None:
        with self._lock:
            self._config_stack.clear()
            self._current_config = None
            self._client.disconnect()
        if self._on_disconnect_cb:
            self._on_disconnect_cb()

    def probe_and_connect(self, port: str, baud: int = 9600, timeout: float = 0.8) -> tuple[bool, str]:
        """Probe port; if SA818 found, connect and return (True, version)."""
        ok, detail = SA818Client.probe(port, baud=baud, timeout=timeout)
        if ok:
            try:
                self.connect(port, baud=baud, timeout=2.0)
                return True, detail
            except SA818Error as exc:
                return False, str(exc)
        return False, detail

    # ------------------------------------------------------------------
    # Radio config with save/restore
    # ------------------------------------------------------------------

    def apply_config(self, cfg: RadioConfig) -> str:
        """Apply radio config and remember it as current."""
        with self._lock:
            reply = self._client.set_radio(cfg)
            self._current_config = cfg.clone()
            return reply

    def push_config(self, cfg: RadioConfig) -> str:
        """Push current config onto the stack, then apply cfg.

        Stack-safe (LIFO): nested push/pop calls are supported, so RX monitor
        and TX/auto-ACK can each push/pop without clobbering each other.
        Use pop_config() to restore.
        """
        with self._lock:
            if self._current_config is not None:
                self._config_stack.append(self._current_config.clone())
            reply = self._client.set_radio(cfg)
            self._current_config = cfg.clone()
            return reply

    def pop_config(self) -> Optional[str]:
        """Restore most recently pushed config (LIFO). Returns reply or None if stack empty."""
        with self._lock:
            if not self._config_stack:
                return None
            cfg = self._config_stack.pop()
            try:
                reply = self._client.set_radio(cfg)
                self._current_config = cfg.clone()
                return reply
            except Exception:
                return None

    def has_saved_config(self) -> bool:
        with self._lock:
            return bool(self._config_stack)

    # ------------------------------------------------------------------
    # Delegated SA818 commands
    # ------------------------------------------------------------------

    def set_volume(self, level: int) -> str:
        with self._lock:
            return self._client.set_volume(level)

    def set_filters(self, disable_emphasis: bool, disable_highpass: bool, disable_lowpass: bool) -> str:
        with self._lock:
            return self._client.set_filters(disable_emphasis, disable_highpass, disable_lowpass)

    def set_tail(self, open_tail: bool) -> str:
        with self._lock:
            return self._client.set_tail(open_tail)

    def version(self) -> str:
        with self._lock:
            return self._client.version()

    def set_ptt(self, enabled: bool, line: str = "RTS", active_high: bool = True) -> None:
        with self._lock:
            self._client.set_ptt(enabled, line=line, active_high=active_high)

    def release_ptt(self, line: str = "RTS", active_high: bool = True) -> None:
        """Release PTT without raising."""
        try:
            with self._lock:
                if self._client.connected:
                    self._client.set_ptt(False, line=line, active_high=active_high)
        except Exception:
            pass
