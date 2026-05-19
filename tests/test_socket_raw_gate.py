"""Phase 6.2 — on_socket_raw_receive substring gate.

The handler only cares about ``GUILD_JOIN_REQUEST_CREATE`` and
``GUILD_JOIN_REQUEST_DELETE``. Every other gateway packet (MESSAGE_CREATE,
TYPING_START, VOICE_STATE_UPDATE, ...) should bail out before we pay for
``json.loads`` — that's the whole point of the gate.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.server_events import ServerEventsCog
from modules.config import TARGET_GUILD


@pytest.fixture
def cog():
    return ServerEventsCog(MagicMock())


def test_unrelated_packets_are_not_parsed(cog):
    msg = '{"op": 0, "t": "MESSAGE_CREATE", "d": {"content": "hi"}}'
    with patch("cogs.server_events.json.loads") as mock_loads:
        asyncio.run(cog.on_socket_raw_receive(msg))
    mock_loads.assert_not_called()


def test_bytes_payloads_are_skipped(cog):
    with patch("cogs.server_events.json.loads") as mock_loads:
        asyncio.run(cog.on_socket_raw_receive(b'{"t": "GUILD_JOIN_REQUEST_CREATE"}'))
    mock_loads.assert_not_called()


def test_join_request_create_is_dispatched(cog):
    """Verifies the gate lets matching packets through to the inner handler,
    which calls ``general.send``. We assert against ``modules.general.send``
    (the actual side effect boundary) rather than patching the inner helper —
    ``bot.load_extension`` in earlier tests overwrites
    ``sys.modules['cogs.server_events']`` with a new module instance, so
    patching ``cogs.server_events._on_join_request_create`` misses the bound
    method's ``__globals__`` (which points at the original module dict)."""
    msg = json.dumps(
        {"op": 0, "t": "GUILD_JOIN_REQUEST_CREATE", "d": {"guild_id": str(TARGET_GUILD)}}
    )
    with patch("modules.general.send", new_callable=AsyncMock) as mock_send:
        asyncio.run(cog.on_socket_raw_receive(msg))
    mock_send.assert_awaited()


def test_other_guilds_are_ignored(cog):
    msg = json.dumps(
        {"op": 0, "t": "GUILD_JOIN_REQUEST_CREATE", "d": {"guild_id": "99999999999999"}}
    )
    with patch("modules.general.send", new_callable=AsyncMock) as mock_send:
        asyncio.run(cog.on_socket_raw_receive(msg))
    mock_send.assert_not_called()


def test_non_dispatch_opcodes_are_ignored(cog):
    msg = json.dumps(
        {"op": 11, "t": "GUILD_JOIN_REQUEST_CREATE", "d": {}}  # HEARTBEAT_ACK
    )
    with patch("modules.general.send", new_callable=AsyncMock) as mock_send:
        asyncio.run(cog.on_socket_raw_receive(msg))
    mock_send.assert_not_called()


def test_malformed_json_bails_silently(cog):
    # contains the substring so it passes the gate, then fails json parsing.
    msg = '{"t": "GUILD_JOIN_REQUEST_CREATE" malformed json'
    asyncio.run(cog.on_socket_raw_receive(msg))  # must not raise


def test_substring_false_positive_is_caught_by_event_type_check(cog):
    """A user message containing the literal substring should still
    pass the cheap gate, but bail at the event_type check inside."""
    msg = json.dumps(
        {
            "op": 0,
            "t": "MESSAGE_CREATE",
            "d": {"content": "i love GUILD_JOIN_REQUEST_CREATE memes"},
        }
    )
    with patch("modules.general.send", new_callable=AsyncMock) as mock_send:
        asyncio.run(cog.on_socket_raw_receive(msg))
    mock_send.assert_not_called()
