"""Tests for MCP SDK compatibility across the 1.x and 2.x handler APIs.

The 2.0 SDK replaced the ``@server.list_tools()`` / ``@server.call_tool()``
decorators with ``on_list_tools`` / ``on_call_tool`` constructor callbacks that
receive a ServerRequestContext and return a result object. ``MCPServer``
registers whichever style the installed SDK exposes.

The adapters are exercised on both generations: the result and params types
they use exist in 1.x as well, so running under 1.x still covers the 2.x path.
"""

import os
import time
import unittest
from unittest import mock

import mcp.server as _mcp_server
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult

from tigergraph_mcp.connection_manager import (
    SessionConnectionManager,
    reset_pending_credentials,
    set_pending_credentials,
)
from tigergraph_mcp.server import MCPServer, _SDK_HAS_DECORATORS
from tigergraph_mcp.tool_names import TigerGraphToolName

SDK_HAS_DECORATORS = hasattr(_mcp_server.Server, "list_tools")

# A tool that answers from the local registry, so no TigerGraph connection is
# needed to prove the dispatch path works.
LOCAL_TOOL = TigerGraphToolName.GET_DATA_SOURCE_TYPES


class TestCapabilityProbe(unittest.TestCase):

    def test_probe_matches_the_installed_sdk(self):
        self.assertEqual(_SDK_HAS_DECORATORS, SDK_HAS_DECORATORS)

    def test_probe_does_not_read_a_version_string(self):
        # Feature detection must survive a backport or a fork whose version
        # number says nothing useful.
        self.assertIsInstance(_SDK_HAS_DECORATORS, bool)


class TestServerConstruction(unittest.TestCase):

    def test_server_builds_in_stdio_mode(self):
        self.assertIsNotNone(MCPServer(multi_session=False).server)

    def test_server_builds_in_multi_session_mode(self):
        self.assertIsNotNone(MCPServer(multi_session=True).server)

    def test_handlers_are_registered(self):
        server = MCPServer().server
        if SDK_HAS_DECORATORS:
            from mcp.types import CallToolRequest, ListToolsRequest

            self.assertIn(ListToolsRequest, server.request_handlers)
            self.assertIn(CallToolRequest, server.request_handlers)
        else:
            self.assertIsNotNone(server.get_request_handler("tools/list"))
            self.assertIsNotNone(server.get_request_handler("tools/call"))


class TestSharedHandlers(unittest.IsolatedAsyncioTestCase):

    async def test_list_tools_returns_the_registry(self):
        tools = await MCPServer()._handle_list_tools()
        self.assertTrue(tools)
        self.assertIn(LOCAL_TOOL, [t.name for t in tools])

    async def test_call_tool_returns_content(self):
        result = await MCPServer()._handle_call_tool(LOCAL_TOOL, {})
        self.assertTrue(result)
        self.assertIn("snowflake", result[0].text)

    async def test_unknown_tool_is_reported_not_raised(self):
        result = await MCPServer()._handle_call_tool("tigergraph__no_such_tool", {})
        self.assertIn("Unknown tool", result[0].text)


class TestVersion2Adapters(unittest.IsolatedAsyncioTestCase):
    """The 2.x callbacks, exercised regardless of the installed SDK."""

    async def test_on_list_tools_wraps_the_tool_list(self):
        result = await MCPServer()._on_list_tools(None, None)
        self.assertIsInstance(result, ListToolsResult)
        self.assertIn(LOCAL_TOOL, [t.name for t in result.tools])

    async def test_on_call_tool_wraps_the_content(self):
        result = await MCPServer()._on_call_tool(
            None, CallToolRequestParams(name=LOCAL_TOOL, arguments={})
        )
        self.assertIsInstance(result, CallToolResult)
        self.assertEqual(len(result.content), 1)

    async def test_on_call_tool_tolerates_absent_arguments(self):
        result = await MCPServer()._on_call_tool(
            None, CallToolRequestParams(name=LOCAL_TOOL)
        )
        self.assertIsInstance(result, CallToolResult)

    async def test_on_call_tool_does_not_flag_success_as_an_error(self):
        result = await MCPServer()._on_call_tool(
            None, CallToolRequestParams(name=LOCAL_TOOL, arguments={})
        )
        # Field name differs between SDK generations; both default to false.
        is_error = getattr(result, "is_error", None)
        if is_error is None:
            is_error = getattr(result, "isError", None)
        self.assertFalse(is_error)


class TestSessionLookup(unittest.IsolatedAsyncioTestCase):
    """Session resolution has to work whether the SDK supplies the session on
    the server (1.x) or hands it to the handler (2.x)."""

    async def test_stdio_mode_has_no_session_manager(self):
        server = MCPServer(multi_session=False)
        self.assertIsNone(await server._session_manager_for_current_request())

    async def test_missing_session_is_not_an_error(self):
        server = MCPServer(multi_session=True)
        self.assertIsNone(await server._session_manager_for_current_request())

    async def test_explicit_session_creates_a_manager(self):
        server = MCPServer(multi_session=True)
        session = object()
        manager = await server._session_manager_for_current_request(session)
        self.assertIsNotNone(manager)

    async def test_same_session_reuses_its_manager(self):
        server = MCPServer(multi_session=True)
        session = object()
        first = await server._session_manager_for_current_request(session)
        second = await server._session_manager_for_current_request(session)
        self.assertIs(first, second)

    async def test_distinct_sessions_are_isolated(self):
        server = MCPServer(multi_session=True)
        # Managers are keyed by id(session), so both sessions must stay
        # referenced for the duration of the test.
        session_a, session_b = object(), object()
        first = await server._session_manager_for_current_request(session_a)
        second = await server._session_manager_for_current_request(session_b)
        self.assertIsNot(first, second)


class TestIdleSessionSweeper(unittest.IsolatedAsyncioTestCase):
    """MCP gives no "session closed" signal, and some clients open a session
    per tool call, so idle pools must be reclaimed or they accumulate."""

    def setUp(self):
        self.server = MCPServer(multi_session=True)

    def _add_session(self, key, age_seconds):
        cm = SessionConnectionManager()
        cm.close_all = mock.AsyncMock()
        self.server._session_managers[key] = cm
        self.server._session_last_used[key] = time.monotonic() - age_seconds
        return cm

    async def test_idle_session_is_reclaimed(self):
        cm = self._add_session(1, age_seconds=10_000)
        reclaimed = await self.server.sweep_idle_sessions()
        self.assertEqual(reclaimed, 1)
        self.assertNotIn(1, self.server._session_managers)
        cm.close_all.assert_awaited_once()

    async def test_recently_used_session_is_kept(self):
        cm = self._add_session(1, age_seconds=1)
        self.assertEqual(await self.server.sweep_idle_sessions(), 0)
        self.assertIn(1, self.server._session_managers)
        cm.close_all.assert_not_awaited()

    async def test_only_the_idle_ones_go(self):
        self._add_session(1, age_seconds=10_000)
        self._add_session(2, age_seconds=0)
        await self.server.sweep_idle_sessions()
        self.assertEqual(list(self.server._session_managers), [2])

    async def test_zero_timeout_disables_reclaiming(self):
        self._add_session(1, age_seconds=10_000)
        with mock.patch.dict(os.environ, {"TG_HTTP_SESSION_IDLE_TIMEOUT": "0"}):
            self.assertEqual(await self.server.sweep_idle_sessions(), 0)
        self.assertIn(1, self.server._session_managers)

    async def test_timestamps_are_dropped_with_the_session(self):
        self._add_session(1, age_seconds=10_000)
        await self.server.sweep_idle_sessions()
        self.assertNotIn(1, self.server._session_last_used)

    async def test_a_failing_close_does_not_stop_the_sweep(self):
        bad = self._add_session(1, age_seconds=10_000)
        bad.close_all = mock.AsyncMock(side_effect=RuntimeError("boom"))
        self._add_session(2, age_seconds=10_000)
        self.assertEqual(await self.server.sweep_idle_sessions(), 2)
        self.assertEqual(self.server._session_managers, {})

    async def test_a_swept_session_is_rebuilt_on_next_use(self):
        # Sweeping must not break a session that becomes active again: the
        # next request re-seeds the pool from its established credentials.
        self._add_session(1, age_seconds=10_000)
        await self.server.sweep_idle_sessions()
        session = object()
        token = set_pending_credentials({
            "profile": "default", "host": "http://tg",
            "username": "u", "password": "p",
        })
        try:
            cm = await self.server._session_manager_for_current_request(session)
        finally:
            reset_pending_credentials(token)
        self.assertIsNotNone(cm)
        self.assertIn("default", cm._connection_pool)

    async def test_shutdown_clears_everything(self):
        self._add_session(1, age_seconds=0)
        await self.server.aclose_session_managers()
        self.assertEqual(self.server._session_managers, {})
        self.assertEqual(self.server._session_last_used, {})


if __name__ == "__main__":
    unittest.main()
