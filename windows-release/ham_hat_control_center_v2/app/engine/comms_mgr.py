#!/usr/bin/env python3
"""CommsManager: contacts, groups, and chat thread logic.

Pure Python — no Tkinter dependencies. All state changes happen here;
the UI registers callbacks to receive updates.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Callable, Optional

from .aprs_modem import (
    build_group_wire_text,
    build_intro_wire_text,
    split_aprs_text_chunks,
    split_text_for_group,
)
from .models import ChatMessage


class CommsManager:
    """Manages contacts, groups, chat history, and heard stations."""

    def __init__(self) -> None:
        self._contacts: list[str] = []
        self._groups: dict[str, list[str]] = {}
        self._heard: list[str] = []
        self._messages: list[ChatMessage] = []
        self._threads_unread: dict[str, int] = {}
        self._active_thread: str = ""
        self._last_direct_sender: str = ""
        self._intro_seen: set[str] = set()

        # Callbacks (called on the thread that triggers them)
        self._on_contacts_changed: Optional[Callable[[], None]] = None
        self._on_message_added: Optional[Callable[[ChatMessage], None]] = None
        self._on_heard_changed: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_contacts_changed(self, cb: Callable[[], None]) -> None:
        self._on_contacts_changed = cb

    def on_message_added(self, cb: Callable[[ChatMessage], None]) -> None:
        self._on_message_added = cb

    def on_heard_changed(self, cb: Callable[[], None]) -> None:
        self._on_heard_changed = cb

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    @property
    def contacts(self) -> list[str]:
        return list(self._contacts)

    def add_contact(self, call: str) -> bool:
        c = _norm_call(call)
        if c and c not in self._contacts:
            self._contacts.append(c)
            if self._on_contacts_changed:
                self._on_contacts_changed()
            return True
        return False

    def remove_contact(self, call: str) -> bool:
        c = _norm_call(call)
        if c in self._contacts:
            self._contacts.remove(c)
            if self._on_contacts_changed:
                self._on_contacts_changed()
            return True
        return False

    def ensure_contact(self, call: str) -> None:
        self.add_contact(call)

    def add_heard_to_contacts(self) -> None:
        changed = False
        for c in self._heard:
            if c and c not in self._contacts:
                self._contacts.append(c)
                changed = True
        if changed and self._on_contacts_changed:
            self._on_contacts_changed()

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    @property
    def groups(self) -> dict[str, list[str]]:
        return dict(self._groups)

    def set_group(self, name: str, members: list[str]) -> None:
        g = _norm_call(name)
        if g:
            self._groups[g] = [_norm_call(m) for m in members if _norm_call(m)]
            if self._on_contacts_changed:
                self._on_contacts_changed()

    def delete_group(self, name: str) -> None:
        g = _norm_call(name)
        if g in self._groups:
            del self._groups[g]
            if self._on_contacts_changed:
                self._on_contacts_changed()

    # ------------------------------------------------------------------
    # Heard stations
    # ------------------------------------------------------------------

    @property
    def heard(self) -> list[str]:
        return list(self._heard)

    def note_heard(self, call: str) -> None:
        c = _norm_call(call)
        if c and c not in self._heard:
            self._heard.append(c)
            if self._on_heard_changed:
                self._on_heard_changed()

    def clear_heard(self) -> None:
        self._heard.clear()
        if self._on_heard_changed:
            self._on_heard_changed()

    # ------------------------------------------------------------------
    # Chat messages
    # ------------------------------------------------------------------

    @property
    def messages(self) -> list[ChatMessage]:
        return list(self._messages)

    def add_message(self, msg: ChatMessage) -> None:
        self._messages.append(msg)
        if msg.direction == "RX" and msg.thread_key and msg.thread_key != self._active_thread:
            self._threads_unread[msg.thread_key] = self._threads_unread.get(msg.thread_key, 0) + 1
        if self._on_message_added:
            self._on_message_added(msg)

    def messages_for_thread(self, thread_key: str) -> list[ChatMessage]:
        return [m for m in self._messages if m.thread_key == thread_key]

    def all_thread_keys(self) -> list[str]:
        seen: dict[str, float] = {}
        for m in self._messages:
            if m.thread_key:
                seen[m.thread_key] = 0  # order by first appearance
        return list(seen.keys())

    def unread_for_thread(self, thread_key: str) -> int:
        return self._threads_unread.get(thread_key, 0)

    def set_active_thread(self, thread_key: str) -> None:
        self._active_thread = thread_key
        self._threads_unread.pop(thread_key, None)

    @property
    def active_thread(self) -> str:
        return self._active_thread

    @property
    def last_direct_sender(self) -> str:
        return self._last_direct_sender

    def set_last_direct_sender(self, call: str) -> None:
        self._last_direct_sender = call

    # ------------------------------------------------------------------
    # Wire text builders (used by UI to construct payloads)
    # ------------------------------------------------------------------

    def build_direct_chunks(self, text: str) -> list[str]:
        """Split text for direct APRS messaging."""
        return split_aprs_text_chunks(text)

    def build_group_chunks(self, group: str, text: str) -> list[str]:
        """Split text into group wire-format chunks (prefix overhead accounted)."""
        parts = split_text_for_group(text, group)
        total = len(parts)
        if total == 1:
            return [build_group_wire_text(group, parts[0])]
        return [build_group_wire_text(group, p, part=i + 1, total=total) for i, p in enumerate(parts)]

    def build_intro_payload(self, callsign: str, lat: float, lon: float, note: str) -> str:
        return build_intro_wire_text(callsign, lat, lon, note)

    # ------------------------------------------------------------------
    # Intro tracking
    # ------------------------------------------------------------------

    def should_process_intro(self, src_call: str, lat: float, lon: float, note: str) -> bool:
        key = f"{src_call}|{lat:.5f}|{lon:.5f}|{note}"
        if key in self._intro_seen:
            return False
        self._intro_seen.add(key)
        return True

    # ------------------------------------------------------------------
    # Thread key inference
    # ------------------------------------------------------------------

    def infer_thread_key(self, src: str, dst: str, text: str, local_calls: set[str]) -> str:
        """Return the thread key for a given packet, matching v1 logic."""
        from .aprs_modem import parse_group_wire_text
        gw = parse_group_wire_text(text)
        if gw:
            return f"GROUP:{gw[0]}"
        src_n = _norm_call(src)
        dst_n = _norm_call(dst)
        if dst_n in {_norm_call(c) for c in local_calls}:
            return src_n
        if src_n in {_norm_call(c) for c in local_calls}:
            return dst_n
        return src_n

    # ------------------------------------------------------------------
    # Serialisation (for profile save/load)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "contacts": list(self._contacts),
            "groups": {k: list(v) for k, v in self._groups.items()},
        }

    def from_dict(self, data: dict) -> None:
        self._contacts = [_norm_call(x) for x in data.get("contacts", []) if _norm_call(x)]
        raw_groups = data.get("groups", {})
        if isinstance(raw_groups, dict):
            self._groups = {
                _norm_call(k): [_norm_call(m) for m in v if _norm_call(m)]
                for k, v in raw_groups.items()
                if _norm_call(k)
            }
        if self._on_contacts_changed:
            self._on_contacts_changed()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_call(token: str) -> str:
    """Normalise a callsign to uppercase stripped form."""
    return token.strip().upper()
