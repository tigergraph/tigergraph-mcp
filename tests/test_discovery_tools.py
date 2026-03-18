"""Tests for tigergraph_mcp.tools.discovery_tools."""

import unittest

from tests.mcp import MCPToolTestBase
from tigergraph_mcp.tools.discovery_tools import (
    discover_tools,
    get_workflow,
    get_tool_info,
)


class TestDiscoverTools(MCPToolTestBase):

    async def test_finds_relevant_tools(self):
        result = await discover_tools(task_description="create a graph with vertices")
        resp = self.assert_success(result)
        self.assertIn("recommended_tools", resp["data"])

    async def test_no_match(self):
        result = await discover_tools(task_description="xyzzy nonsense gibberish")
        resp = self.assert_success(result)
        self.assertNotIn("recommended_tools", resp.get("data", {}))

    async def test_category_filter(self):
        result = await discover_tools(
            task_description="schema vertex edge",
            category="schema",
        )
        resp = self.assert_success(result)
        if "recommended_tools" in resp.get("data", {}):
            for tool in resp["data"]["recommended_tools"]:
                self.assertEqual(tool["category"], "schema")

    async def test_limit(self):
        result = await discover_tools(
            task_description="graph query data loading",
            limit=2,
        )
        resp = self.assert_success(result)
        if "recommended_tools" in resp.get("data", {}):
            self.assertLessEqual(len(resp["data"]["recommended_tools"]), 2)


class TestGetWorkflow(MCPToolTestBase):

    async def test_valid_workflow(self):
        result = await get_workflow(workflow_type="setup_connection")
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["workflow_type"], "setup_connection")
        self.assertIn("steps", resp["data"])

    async def test_unknown_workflow(self):
        result = await get_workflow(workflow_type="nonexistent_workflow")
        resp = self.assert_success(result)
        self.assertIn("available_workflows", resp["data"])


class TestGetToolInfo(MCPToolTestBase):

    async def test_valid_tool(self):
        result = await get_tool_info(tool_name="tigergraph__show_graph_details")
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["tool_name"], "tigergraph__show_graph_details")
        self.assertIn("use_cases", resp["data"])

    async def test_unknown_tool(self):
        result = await get_tool_info(tool_name="tigergraph__nonexistent")
        resp = self.assert_success(result)
        self.assertIn("not found", resp["summary"].lower())


if __name__ == "__main__":
    unittest.main()
