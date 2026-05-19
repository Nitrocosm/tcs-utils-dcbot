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
    msg = json.dumps(
        {"op": 0, "t": "GUILD_JOIN_REQUEST_CREATE", "d": {"guild_id": str(TARGET_GUILD)}}
    )
    with patch(
        "cogs.server_events._on_join_request_create", new_callable=AsyncMock
    ) as mock_handler:
        asyncio.run(cog.on_socket_raw_receive(msg))
    mock_handler.assert_awaited_once()


def test_other_guilds_are_ignored(cog):
    msg = json.dumps(
        {"op": 0, "t": "GUILD_JOIN_REQUEST_CREATE", "d": {"guild_id": "99999999999999"}}
    )
    with patch(
        "cogs.server_events._on_join_request_create", new_callable=AsyncMock
    ) as mock_handler:
        asyncio.run(cog.on_socket_raw_receive(msg))
    mock_handler.assert_not_called()


def test_non_dispatch_opcodes_are_ignored(cog):
    msg = json.dumps(
        {"op": 11, "t": "GUILD_JOIN_REQUEST_CREATE", "d": {}}  # HEARTBEAT_ACK
    )
    with patch(
        "cogs.server_events._on_join_request_create", new_callable=AsyncMock
    ) as mock_handler:
        asyncio.run(cog.on_socket_raw_receive(msg))
    mock_handler.assert_not_called()


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
    with patch(
        "cogs.server_events._on_join_request_create", new_callable=AsyncMock
    ) as mock_handler:
        asyncio.run(cog.on_socket_raw_receive(msg))
    mock_handler.assert_not_called()
