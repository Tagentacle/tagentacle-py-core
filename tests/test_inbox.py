"""Tests for Inbox."""

from tagentacle_py_core import Inbox, TopicMode


def test_push_default_followup():
    inbox = Inbox()
    assert inbox.push("/chat/input", {"text": "hello"}) is True
    assert inbox.pending == 1


def test_push_collect_mode():
    inbox = Inbox()
    inbox.set_mode("/memory/latest", TopicMode.COLLECT)
    assert inbox.push("/memory/latest", {"data": "x"}) is False
    assert inbox.pending == 1


def test_drain_clears():
    inbox = Inbox()
    inbox.push("/a", {"x": 1})
    inbox.push("/b", {"x": 2})
    msgs = inbox.drain()
    assert len(msgs) == 2
    assert inbox.pending == 0
    assert msgs[0]["topic"] == "/a"
    assert msgs[1]["topic"] == "/b"


def test_drain_empty():
    inbox = Inbox()
    assert inbox.drain() == []


def test_mixed_modes():
    inbox = Inbox()
    inbox.set_mode("/chat/input", TopicMode.FOLLOWUP)
    inbox.set_mode("/memory/latest", TopicMode.COLLECT)

    triggers = []
    for topic in ["/chat/input", "/memory/latest", "/chat/input"]:
        triggers.append(inbox.push(topic, {"t": topic}))

    assert triggers == [True, False, True]
    assert inbox.pending == 3

    msgs = inbox.drain()
    assert [m["topic"] for m in msgs] == ["/chat/input", "/memory/latest", "/chat/input"]


def test_default_mode_collect():
    inbox = Inbox(default_mode=TopicMode.COLLECT)
    assert inbox.push("/unknown", {}) is False


def test_message_has_timestamp():
    inbox = Inbox()
    inbox.push("/test", {"data": 1})
    msg = inbox.drain()[0]
    assert "ts" in msg
    assert isinstance(msg["ts"], float)
