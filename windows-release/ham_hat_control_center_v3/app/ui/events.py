#!/usr/bin/env python3
"""Typed event dataclasses for the engine→UI queue.

All engine worker threads post events here; the UI drains via after().
Using typed dataclasses instead of string tuples eliminates the fragile
string-parsing that caused bugs in v1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np

from ..engine.models import ChatMessage, DecodedPacket


@dataclass
class LogEvent:
    msg: str


@dataclass
class AprsLogEvent:
    msg: str


@dataclass
class ErrorEvent:
    title: str
    msg: str


@dataclass
class ConnectionEvent:
    connected: bool
    port: str = ""


@dataclass
class PacketEvent:
    packet: DecodedPacket
    position: Optional[tuple[float, float, str]] = None
    message: Optional[tuple[str, str, Optional[str]]] = None
    ack_id: Optional[str] = None
    group: Optional[tuple] = None
    intro: Optional[tuple] = None
    duplicate: bool = False


@dataclass
class MapPointEvent:
    lat: float
    lon: float
    label: str


@dataclass
class AudioPairEvent:
    out_idx: int
    in_idx: int


@dataclass
class InputDeviceEvent:
    in_idx: int


@dataclass
class InputLevelEvent:
    level: float


@dataclass
class OutputLevelEvent:
    level: float


@dataclass
class WaterfallEvent:
    samples: np.ndarray
    rate: int


@dataclass
class RxClipEvent:
    percent: float


@dataclass
class HeardStationEvent:
    call: str


@dataclass
class ChatMessageEvent:
    message: ChatMessage


@dataclass
class ContactsChangedEvent:
    pass


# Union type for the queue
AppEvent = Union[
    LogEvent,
    AprsLogEvent,
    ErrorEvent,
    ConnectionEvent,
    PacketEvent,
    MapPointEvent,
    AudioPairEvent,
    InputDeviceEvent,
    InputLevelEvent,
    OutputLevelEvent,
    WaterfallEvent,
    RxClipEvent,
    HeardStationEvent,
    ChatMessageEvent,
    ContactsChangedEvent,
]
