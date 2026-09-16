"""Tests for tool annotations and for serving a subset of the tools."""

import unittest
from unittest import mock

from tigergraph_mcp import tool_filter
from tigergraph_mcp.tool_annotations import (
    DESTRUCTIVE,
    IDEMPOTENT,
    OPEN_WORLD,
    READ_ONLY,
    hints,
)
from tigergraph_mcp.tool_metadata import TOOL_METADATA
from tigergraph_mcp.tools import get_all_tools

ALL = get_all_tools(apply_filter=False)
NAMES = {t.name for t in ALL}


class TestClassificationIntegrity(unittest.TestCase):
    """A tool in the wrong set is a safety problem, not a cosmetic one."""

    def test_every_classified_name_is_a_real_tool(self):
        for group in (READ_ONLY, DESTRUCTIVE, IDEMPOTENT, OPEN_WORLD):
            self.assertEqual(group - NAMES, set())

    def test_read_only_and_destructive_do_not_overlap(self):
        self.assertEqual(READ_ONLY & DESTRUCTIVE, set())

    def test_every_tool_is_classified_one_way_or_the_other(self):
        # Anything not read-only is a write; it need not be destructive, but it
        # must not be silently absent from consideration.
        writes = NAMES - READ_ONLY
        self.assertTrue(writes)
        self.assertTrue(DESTRUCTIVE <= writes)

    def test_tools_that_remove_things_are_destructive(self):
        for name in NAMES:
            short = name.replace("tigergraph__", "")
            if short.startswith(("drop_", "delete_", "clear_")):
                self.assertIn(name, DESTRUCTIVE, f"{short} should be destructive")

    def test_tools_that_only_read_are_read_only(self):
        for name in NAMES:
            short = name.replace("tigergraph__", "")
            if short.startswith(("get_", "list_", "has_", "is_", "show_")):
                self.assertIn(name, READ_ONLY, f"{short} should be read-only")

    def test_arbitrary_query_text_is_treated_as_destructive(self):
        # What these do depends on the caller's text, so they are classified by
        # what they may do rather than what they usually do.
        for name in ("tigergraph__gsql", "tigergraph__run_query",
                     "tigergraph__run_installed_query"):
            self.assertIn(name, DESTRUCTIVE)
            self.assertNotIn(name, READ_ONLY)


class TestAnnotations(unittest.TestCase):

    def test_read_only_tool(self):
        a = hints("tigergraph__get_vertex_count")
        self.assertTrue(a["readOnlyHint"])
        self.assertFalse(a["destructiveHint"])
        self.assertTrue(a["idempotentHint"])

    def test_destructive_tool(self):
        a = hints("tigergraph__drop_graph")
        self.assertFalse(a["readOnlyHint"])
        self.assertTrue(a["destructiveHint"])

    def test_additive_write_is_not_destructive(self):
        a = hints("tigergraph__add_nodes")
        self.assertFalse(a["readOnlyHint"])
        self.assertFalse(a["destructiveHint"])

    def test_a_read_only_tool_is_never_destructive(self):
        for name in READ_ONLY:
            self.assertFalse(hints(name)["destructiveHint"], name)

    def test_llm_tools_are_open_world(self):
        self.assertTrue(hints("tigergraph__generate_gsql")["openWorldHint"])
        self.assertFalse(hints("tigergraph__list_graphs")["openWorldHint"])

    def test_hint_names_are_the_same_on_every_sdk(self):
        # 1.x names these fields in camelCase, 2.x in snake_case with camelCase
        # aliases; clients must see one spelling either way.
        self.assertEqual(
            set(hints("tigergraph__drop_graph")),
            {"title", "readOnlyHint", "destructiveHint", "idempotentHint",
             "openWorldHint"},
        )

    def test_titles_are_short_enough_for_a_prompt(self):
        for name in NAMES:
            self.assertLessEqual(len(hints(name)["title"]), 40, name)

    def test_every_served_tool_carries_annotations(self):
        for t in get_all_tools():
            self.assertIsNotNone(t.annotations, t.name)


class TestSelector(unittest.TestCase):

    def parse(self, spec):
        return tool_filter.parse_selector(spec, NAMES)

    def test_category(self):
        expected = {n for n, m in TOOL_METADATA.items() if m.category.value == "schema"}
        self.assertEqual(self.parse("schema"), expected & NAMES)

    def test_several_categories(self):
        self.assertEqual(self.parse("schema,query"),
                         self.parse("schema") | self.parse("query"))

    def test_read_only_capability(self):
        self.assertEqual(self.parse("read-only"), set(READ_ONLY))

    def test_destructive_capability(self):
        self.assertEqual(self.parse("destructive"), set(DESTRUCTIVE))

    def test_exact_tool_name(self):
        self.assertEqual(self.parse("tigergraph__list_graphs"),
                         {"tigergraph__list_graphs"})

    def test_tool_name_without_the_prefix(self):
        self.assertEqual(self.parse("list_graphs"), {"tigergraph__list_graphs"})

    def test_mixing_kinds(self):
        got = self.parse("schema,read-only,drop_query")
        self.assertIn("tigergraph__drop_query", got)
        self.assertIn("tigergraph__list_graphs", got)

    def test_whitespace_and_case_are_forgiven(self):
        self.assertEqual(self.parse(" Schema , QUERY "), self.parse("schema,query"))

    def test_unknown_selector_is_an_error(self):
        with self.assertRaises(ValueError) as ctx:
            self.parse("quries")
        self.assertIn("Unknown tool selector", str(ctx.exception))

    def test_unknown_selector_suggests_a_close_match(self):
        with self.assertRaises(ValueError) as ctx:
            self.parse("quries")
        self.assertIn("query", str(ctx.exception))

    def test_empty_tokens_are_skipped(self):
        self.assertEqual(self.parse("schema,,"), self.parse("schema"))


class TestSelect(unittest.TestCase):

    def names(self, **kw):
        return {t.name for t in tool_filter.select(ALL, **kw)}

    def test_no_selection_serves_everything(self):
        self.assertEqual(self.names(), NAMES)

    def test_allow_narrows(self):
        self.assertEqual(self.names(allowed="read-only"), set(READ_ONLY))

    def test_block_removes(self):
        got = self.names(blocked="destructive")
        self.assertEqual(got, NAMES - DESTRUCTIVE)

    def test_block_applies_after_allow(self):
        got = self.names(allowed="schema", blocked="drop_graph")
        self.assertNotIn("tigergraph__drop_graph", got)
        self.assertIn("tigergraph__list_graphs", got)

    def test_blocking_everything_allowed_leaves_nothing(self):
        self.assertEqual(self.names(allowed="schema", blocked="schema"), set())

    def test_order_of_the_result_follows_the_registry(self):
        filtered = tool_filter.select(ALL, allowed="read-only")
        self.assertEqual([t.name for t in filtered],
                         [t.name for t in ALL if t.name in READ_ONLY])


class TestConfiguredSelection(unittest.TestCase):

    def setUp(self):
        self.addCleanup(tool_filter.configure, None, None)

    def test_reads_the_environment(self):
        with mock.patch.dict("os.environ", {"TG_ALLOWED_TOOLS": "schema"}, clear=False):
            tool_filter.configure()
        self.assertEqual(tool_filter.configured()[0], "schema")

    def test_arguments_win_over_the_environment(self):
        with mock.patch.dict("os.environ", {"TG_ALLOWED_TOOLS": "schema"}, clear=False):
            tool_filter.configure(allowed="query")
        self.assertEqual(tool_filter.configured()[0], "query")

    def test_applied_to_the_served_list(self):
        tool_filter.configure(allowed="schema")
        self.assertEqual({t.name for t in get_all_tools()},
                         tool_filter.parse_selector("schema", NAMES))

    def test_unfiltered_list_ignores_the_selection(self):
        tool_filter.configure(allowed="schema")
        self.assertEqual({t.name for t in get_all_tools(apply_filter=False)}, NAMES)


class TestSessionNarrowing(unittest.TestCase):
    """A session may restrict itself further; it must never gain a tool the
    deployment withheld."""

    def setUp(self):
        self.addCleanup(tool_filter.configure, None, None)

    def apply(self, session_spec):
        token = tool_filter.set_session_selector(session_spec)
        try:
            return {t.name for t in tool_filter.apply(ALL)}
        finally:
            tool_filter.reset_session_selector(token)

    def test_narrows_within_what_is_configured(self):
        tool_filter.configure(blocked="destructive")
        got = self.apply("read-only")
        self.assertEqual(got, set(READ_ONLY))

    def test_cannot_reach_a_blocked_tool(self):
        tool_filter.configure(blocked="destructive")
        self.assertEqual(self.apply("destructive"), set())

    def test_cannot_reach_a_tool_outside_the_allow_list(self):
        tool_filter.configure(allowed="schema")
        self.assertEqual(self.apply("vector"), set())

    def test_no_session_selector_leaves_the_configuration_alone(self):
        tool_filter.configure(blocked="destructive")
        self.assertEqual(self.apply(None), NAMES - DESTRUCTIVE)


class TestWithheldToolsCannotBeDispatched(unittest.IsolatedAsyncioTestCase):
    """Withholding a tool must hold at dispatch, not just in the listing.

    Filtering the advertised list alone makes the selection a menu rather than
    a restriction: an agent that already knows a tool name -- from another
    deployment, its training, or a previous session -- can call it directly.
    A deployment that starts with --blocked-tools destructive believes those
    tools are unreachable.
    """

    TOOL = "tigergraph__get_data_source_types"

    def setUp(self):
        prior = tool_filter.configured()
        self.addCleanup(
            lambda: tool_filter.configure(allowed=prior[0], blocked=prior[1])
        )

    async def call(self):
        from tigergraph_mcp.server import MCPServer

        result = await MCPServer()._handle_call_tool(self.TOOL, {})
        return result[0].text

    async def test_a_blocked_tool_is_refused_when_called_directly(self):
        tool_filter.configure(blocked="get_data_source_types")
        text = await self.call()
        self.assertIn('"success": false', text)
        self.assertIn("not available", text)

    async def test_a_tool_outside_the_allow_list_is_refused(self):
        tool_filter.configure(allowed="schema")
        self.assertIn('"success": false', await self.call())

    async def test_a_served_tool_still_works(self):
        # The guard must not refuse what the deployment does offer.
        tool_filter.configure(allowed="loading")
        self.assertIn('"success": true', await self.call())

    async def test_an_unfiltered_server_serves_everything(self):
        tool_filter.configure()
        self.assertIn('"success": true', await self.call())

    async def test_the_refusal_does_not_name_the_configuration(self):
        # How the deployment was configured is not the caller's business.
        tool_filter.configure(blocked="get_data_source_types")
        text = await self.call()
        for leak in ("TG_ALLOWED_TOOLS", "TG_BLOCKED_TOOLS",
                     "--allowed-tools", "--blocked-tools"):
            self.assertNotIn(leak, text)

    async def test_a_session_narrowed_tool_is_refused(self):
        # The X-TG-Tools header narrows one session; that must bind dispatch
        # too, which is the case that matters most for a shared HTTP server.
        tool_filter.configure()
        token = tool_filter.set_session_selector("schema")
        try:
            self.assertIn('"success": false', await self.call())
        finally:
            tool_filter.reset_session_selector(token)

    async def test_the_narrowing_ends_with_the_session(self):
        tool_filter.configure()
        token = tool_filter.set_session_selector("schema")
        tool_filter.reset_session_selector(token)
        self.assertIn('"success": true', await self.call())

    async def test_an_unknown_tool_is_still_reported_as_unknown(self):
        from tigergraph_mcp.server import MCPServer

        tool_filter.configure()
        result = await MCPServer()._handle_call_tool("tigergraph__nope", {})
        self.assertIn("Unknown tool", result[0].text)


class TestWithheldToolsAreNotDescribed(unittest.IsolatedAsyncioTestCase):
    """Discovery must not work around the selection either."""

    TOOL = "tigergraph__get_data_source_types"

    def setUp(self):
        prior = tool_filter.configured()
        self.addCleanup(
            lambda: tool_filter.configure(allowed=prior[0], blocked=prior[1])
        )

    async def info(self):
        from tigergraph_mcp.tools.discovery_tools import get_tool_info

        return (await get_tool_info(tool_name=self.TOOL))[0].text

    async def test_a_withheld_tool_is_not_described(self):
        tool_filter.configure(blocked="get_data_source_types")
        self.assertIn("not found", await self.info())

    async def test_a_served_tool_is_still_described(self):
        tool_filter.configure()
        self.assertNotIn("not found", await self.info())

    async def test_discovery_omits_withheld_tools(self):
        from tigergraph_mcp.tools.discovery_tools import discover_tools

        tool_filter.configure(blocked="get_data_source_types")
        text = (await discover_tools(task_description="list data source types"))[0].text
        self.assertNotIn("get_data_source_types", text)


class TestServedNames(unittest.TestCase):

    def setUp(self):
        prior = tool_filter.configured()
        self.addCleanup(
            lambda: tool_filter.configure(allowed=prior[0], blocked=prior[1])
        )

    def test_served_names_match_the_advertised_list(self):
        # The guard and the listing must not drift apart.
        tool_filter.configure(allowed="read-only")
        self.assertEqual(
            tool_filter.served_names(),
            {t.name for t in get_all_tools()},
        )

    def test_is_served_agrees_with_served_names(self):
        tool_filter.configure(allowed="schema")
        served = tool_filter.served_names()
        for name in NAMES:
            self.assertEqual(tool_filter.is_served(name), name in served, name)


if __name__ == "__main__":
    unittest.main()
