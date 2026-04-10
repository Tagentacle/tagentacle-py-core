"""Inbox: Agent-local message buffer with per-topic attention levels.

Bus subscribe stays binary (ROS-style). Attention levels are purely
Agent-local — the bus/broker knows nothing about them.
"""

from __future__ import annotations

import time
from enum import Enum


class TopicMode(str, Enum):
    """How an incoming message on a given topic affects the inference cycle."""

    FOLLOWUP = "followup"  # Buffer + trigger next inference cycle
    COLLECT = "collect"  # Buffer silently, do not trigger


class Inbox:
    """Agent-local message buffer with optional per-topic attention levels.

    >>> inbox = Inbox()
    >>> inbox.set_mode("/chat/input", TopicMode.FOLLOWUP)
    >>> inbox.set_mode("/memory/latest", TopicMode.COLLECT)
    >>> should_trigger = inbox.push("/chat/input", {"text": "hello"})
    >>> assert should_trigger is True
    >>> should_trigger = inbox.push("/memory/latest", {"snapshot": "..."})
    >>> assert should_trigger is False
    >>> msgs = inbox.drain()
    >>> assert len(msgs) == 2
    """

    def __init__(self, *, default_mode: TopicMode = TopicMode.FOLLOWUP) -> None:
        self._unread: list[dict] = []
        self._modes: dict[str, TopicMode] = {}
        self._default_mode = default_mode

    def set_mode(self, topic: str, mode: TopicMode) -> None:
        """Set the attention level for a topic."""
        self._modes[topic] = mode

    def push(self, topic: str, msg: dict) -> bool:
        """Buffer a message. Returns True if it should trigger inference."""
        self._unread.append({"topic": topic, "ts": time.monotonic(), **msg})
        return self._modes.get(topic, self._default_mode) == TopicMode.FOLLOWUP

    def drain(self) -> list[dict]:
        """Return and clear all unread messages."""
        msgs = self._unread.copy()
        self._unread.clear()
        return msgs

    @property
    def pending(self) -> int:
        """Number of unread messages."""
        return len(self._unread)
