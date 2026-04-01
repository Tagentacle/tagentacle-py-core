"""Tests for LifecycleNode lifecycle event publishing."""

import pytest
from unittest.mock import AsyncMock

from tagentacle_py_core import LifecycleNode


@pytest.fixture
def node():
    return LifecycleNode("test_node")


def _make_connected(node):
    """Simulate a connected node by setting _connected and mocking _send_json."""
    node._connected = True
    node._send_json = AsyncMock()
    return node


# --- Event publishing on transitions ---


@pytest.mark.asyncio
async def test_configure_publishes_event(node):
    _make_connected(node)
    await node.configure()

    calls = [c.args[0] for c in node._send_json.call_args_list]
    event_msg = [
        c
        for c in calls
        if c.get("op") == "publish" and c.get("topic") == "/tagentacle/node_events"
    ]
    assert len(event_msg) == 1
    payload = event_msg[0]["payload"]
    assert payload == {
        "event": "lifecycle_transition",
        "node_id": "test_node",
        "prev_state": "unconfigured",
        "state": "inactive",
    }


@pytest.mark.asyncio
async def test_activate_publishes_event(node):
    _make_connected(node)
    await node.configure()
    node._send_json.reset_mock()

    await node.activate()

    calls = [c.args[0] for c in node._send_json.call_args_list]
    event_msg = [
        c
        for c in calls
        if c.get("op") == "publish" and c.get("topic") == "/tagentacle/node_events"
    ]
    assert len(event_msg) == 1
    assert event_msg[0]["payload"]["prev_state"] == "inactive"
    assert event_msg[0]["payload"]["state"] == "active"


@pytest.mark.asyncio
async def test_deactivate_publishes_event(node):
    _make_connected(node)
    await node.configure()
    await node.activate()
    node._send_json.reset_mock()

    await node.deactivate()

    calls = [c.args[0] for c in node._send_json.call_args_list]
    event_msg = [
        c
        for c in calls
        if c.get("op") == "publish" and c.get("topic") == "/tagentacle/node_events"
    ]
    assert len(event_msg) == 1
    assert event_msg[0]["payload"]["prev_state"] == "active"
    assert event_msg[0]["payload"]["state"] == "inactive"


@pytest.mark.asyncio
async def test_shutdown_publishes_event(node):
    _make_connected(node)
    await node.configure()
    await node.activate()
    node._send_json.reset_mock()

    await node.shutdown()

    calls = [c.args[0] for c in node._send_json.call_args_list]
    event_msg = [
        c
        for c in calls
        if c.get("op") == "publish" and c.get("topic") == "/tagentacle/node_events"
    ]
    assert len(event_msg) == 1
    assert event_msg[0]["payload"]["prev_state"] == "active"
    assert event_msg[0]["payload"]["state"] == "finalized"


# --- Payload structure ---


@pytest.mark.asyncio
async def test_event_payload_has_required_fields(node):
    _make_connected(node)
    await node.configure()

    calls = [c.args[0] for c in node._send_json.call_args_list]
    event_msg = [
        c
        for c in calls
        if c.get("op") == "publish" and c.get("topic") == "/tagentacle/node_events"
    ]
    payload = event_msg[0]["payload"]
    assert set(payload.keys()) == {"event", "node_id", "prev_state", "state"}


# --- Best-effort behavior ---


@pytest.mark.asyncio
async def test_no_event_when_disconnected(node):
    """Events should NOT be published when node is not connected."""
    assert not node._connected
    await node.configure()
    # No error raised, state transition still works
    assert node.state.value == "inactive"


@pytest.mark.asyncio
async def test_publish_failure_does_not_break_transition(node):
    """If _send_json raises, the state transition should still complete."""
    _make_connected(node)
    node._send_json = AsyncMock(side_effect=ConnectionError("lost connection"))

    # configure should still succeed despite publish failure
    await node.configure()
    assert node.state.value == "inactive"
