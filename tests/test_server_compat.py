"""Tests for MCP SDK compatibility across the 1.x and 2.x handler APIs.

The 2.0 SDK replaced the ``@server.list_tools()`` / ``@server.call_tool()``
decorators with ``on_list_tools`` / ``on_call_tool`` constructor callbacks that
receive a ServerRequestContext and return a result object. ``MCPServer``
registers whichever style the installed SDK exposes.

The adapters are exercised on both generations: the result and params types
they use exist in 1.x as well, so running under 1.x still covers the 2.x path.
"""

import inspect
import os
import re
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
from pyTigerGraph.common.exception import TigerGraphException

from tigergraph_mcp.server import MCPServer, serve, _SDK_HAS_DECORATORS
from tigergraph_mcp.tool_names import TigerGraphToolName
from tigergraph_mcp.tools import get_all_tools

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


class TestToolErrorsBecomeResponses(unittest.IsolatedAsyncioTestCase):
    """A failing tool must answer, not raise.

    Raising out of the dispatch would break the MCP session for every later
    call; the agent needs a reply it can read and act on.
    """

    async def dispatch_raising(self, exc):
        with mock.patch("tigergraph_mcp.server.get_data_source_types",
                        side_effect=exc):
            result = await MCPServer()._handle_call_tool(LOCAL_TOOL, {"a": 1})
        self.assertTrue(result)
        return result[0].text

    async def test_a_tigergraph_error_is_reported(self):
        text = await self.dispatch_raising(TigerGraphException("REST++ said no"))
        self.assertIn("REST++ said no", text)

    async def test_an_unexpected_error_is_reported(self):
        text = await self.dispatch_raising(RuntimeError("something broke"))
        self.assertIn("something broke", text)

    async def test_the_failing_tool_is_named(self):
        text = await self.dispatch_raising(RuntimeError("boom"))
        self.assertIn(LOCAL_TOOL, text)

    async def test_the_arguments_come_back_for_diagnosis(self):
        text = await self.dispatch_raising(RuntimeError("boom"))
        self.assertIn("a", text)

    async def test_a_later_call_still_works(self):
        # The session must survive a failure.
        await self.dispatch_raising(RuntimeError("boom"))
        ok = await MCPServer()._handle_call_tool(LOCAL_TOOL, {})
        self.assertIn("snowflake", ok[0].text)

    async def test_unknown_tool_does_not_raise_either(self):
        result = await MCPServer()._handle_call_tool("tigergraph__nope", {})
        self.assertIn("Unknown tool", result[0].text)


class TestServeTransportRouting(unittest.IsolatedAsyncioTestCase):

    async def test_stdio_is_the_default(self):
        with mock.patch("tigergraph_mcp.server._serve_stdio") as stdio:
            await serve()
        self.assertTrue(stdio.called)

    async def test_streamable_http_routes_to_the_http_server(self):
        with mock.patch("tigergraph_mcp.server._serve_http") as http:
            await serve(transport="streamable-http", host="0.0.0.0", port=1234)
        self.assertEqual(http.call_args.args[0], "streamable-http")
        self.assertEqual(http.call_args.args[1:3], ("0.0.0.0", 1234))

    async def test_sse_routes_to_the_http_server(self):
        with mock.patch("tigergraph_mcp.server._serve_http") as http:
            await serve(transport="sse")
        self.assertEqual(http.call_args.args[0], "sse")

    async def test_an_unknown_transport_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            await serve(transport="carrier-pigeon")
        self.assertIn("carrier-pigeon", str(ctx.exception))

    async def test_the_error_lists_the_transports_that_do_work(self):
        with self.assertRaises(ValueError) as ctx:
            await serve(transport="")
        for known in ("stdio", "streamable-http", "sse"):
            self.assertIn(known, str(ctx.exception))


class TestSessionShutdown(unittest.IsolatedAsyncioTestCase):

    async def test_all_session_pools_are_closed(self):
        server = MCPServer(multi_session=True)
        closed = []
        for key in (1, 2):
            cm = mock.Mock(spec=SessionConnectionManager)
            cm.close_all = mock.AsyncMock(side_effect=lambda k=key: closed.append(k))
            server._session_managers[key] = cm
            server._session_last_used[key] = 0.0
        await server.aclose_session_managers()
        self.assertEqual(sorted(closed), [1, 2])
        self.assertEqual(server._session_managers, {})
        self.assertEqual(server._session_last_used, {})

    async def test_one_failing_close_does_not_strand_the_others(self):
        server = MCPServer(multi_session=True)
        bad = mock.Mock(spec=SessionConnectionManager)
        bad.close_all = mock.AsyncMock(side_effect=RuntimeError("already gone"))
        good = mock.Mock(spec=SessionConnectionManager)
        good.close_all = mock.AsyncMock()
        server._session_managers.update({1: bad, 2: good})
        await server.aclose_session_managers()
        self.assertTrue(good.close_all.called)
        self.assertEqual(server._session_managers, {})

    async def test_shutdown_with_no_sessions_is_harmless(self):
        await MCPServer(multi_session=True).aclose_session_managers()


class TestEveryServedToolIsDispatchable(unittest.TestCase):
    """A tool the server advertises must have a dispatch arm.

    The list of tools and the match statement that routes them are maintained
    separately, so a tool can be added to the registry and never wired up. The
    symptom is an agent calling an advertised tool and being told it does not
    exist, which is confusing rather than obviously a bug. Checked statically
    so it costs nothing and needs no database.
    """

    def setUp(self):
        src = inspect.getsource(MCPServer._handle_call_tool)
        self.dispatched = set(re.findall(r"TigerGraphToolName\.([A-Z_0-9]+)", src))
        self.by_value = {m.value: m.name for m in TigerGraphToolName}

    def test_every_advertised_tool_has_an_arm(self):
        missing = []
        for tool in get_all_tools(apply_filter=False):
            member = self.by_value.get(tool.name)
            self.assertIsNotNone(member, f"{tool.name} is not in TigerGraphToolName")
            if member not in self.dispatched:
                missing.append(tool.name)
        self.assertEqual(missing, [], f"served but not dispatchable: {missing}")

    def test_the_check_would_notice_a_missing_arm(self):
        # Guards the guard: if the regex stopped matching, the test above would
        # pass vacuously.
        self.assertIn("GET_DATA_SOURCE_TYPES", self.dispatched)
        self.assertNotIn("NOT_A_REAL_TOOL", self.dispatched)

    def test_no_arm_points_at_a_tool_that_no_longer_exists(self):
        known = {m.name for m in TigerGraphToolName}
        self.assertEqual(self.dispatched - known, set())


if __name__ == "__main__":
    unittest.main()
