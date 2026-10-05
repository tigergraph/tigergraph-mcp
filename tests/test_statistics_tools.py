"""Tests for tigergraph_mcp.tools.statistics_tools."""

import unittest
from unittest.mock import patch

from tests.mcp import MCPToolTestBase
from tigergraph_mcp.tools.statistics_tools import (
    get_edge_count,
    get_node_degree,
    get_vertex_count,
)

PATCH_TARGET = "tigergraph_mcp.tools.statistics_tools.get_connection"


class TestGetVertexCount(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_single_type(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getVertexCount.return_value = 42

        result = await get_vertex_count(vertex_type="Person")
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["count"], 42)
        self.assertEqual(resp["data"]["vertex_type"], "Person")

    @patch(PATCH_TARGET)
    async def test_all_types(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getVertexTypes.return_value = ["Person", "Product"]
        self.mock_conn.getVertexCount.side_effect = [100, 50]

        result = await get_vertex_count()
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["total"], 150)
        self.assertEqual(resp["data"]["counts_by_type"]["Person"], 100)
        self.assertEqual(resp["data"]["counts_by_type"]["Product"], 50)

    @patch(PATCH_TARGET)
    async def test_exception(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getVertexCount.side_effect = Exception("not found")

        result = await get_vertex_count(vertex_type="Bad")
        self.assert_error(result)


class TestGetEdgeCount(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_single_type(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getEdgeCount.return_value = 200

        result = await get_edge_count(edge_type="FOLLOWS")
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["count"], 200)

    @patch(PATCH_TARGET)
    async def test_all_types(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getEdgeTypes.return_value = ["FOLLOWS", "PURCHASED"]
        self.mock_conn.getEdgeCount.side_effect = [200, 80]

        result = await get_edge_count()
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["total"], 280)


class TestGetNodeDegree(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_outgoing(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runInterpretedQuery.return_value = [{"outgoing": 5}]

        result = await get_node_degree(
            vertex_type="Person", vertex_id="u1", direction="outgoing"
        )
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["outgoing_degree"], 5)
        self.assertEqual(resp["data"]["total_degree"], 5)

    @patch(PATCH_TARGET)
    async def test_incoming(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runInterpretedQuery.return_value = [{"incoming": 3}]

        result = await get_node_degree(
            vertex_type="Person", vertex_id="u1", direction="incoming"
        )
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["incoming_degree"], 3)

    @patch(PATCH_TARGET)
    async def test_both(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runInterpretedQuery.return_value = [
            {"outgoing": 5, "incoming": 3}
        ]

        result = await get_node_degree(
            vertex_type="Person", vertex_id="u1", direction="both"
        )
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["total_degree"], 8)

    @patch(PATCH_TARGET)
    async def test_with_edge_type(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runInterpretedQuery.return_value = [{"outgoing": 2}]

        result = await get_node_degree(
            vertex_type="Person",
            vertex_id="u1",
            edge_type="FOLLOWS",
            direction="outgoing",
        )
        query_arg = self.mock_conn.runInterpretedQuery.call_args[0][0]
        self.assertIn("FOLLOWS", query_arg)

    @patch(PATCH_TARGET)
    async def test_vertex_id_is_escaped(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runInterpretedQuery.return_value = [{"outgoing": 0, "incoming": 0}]

        await get_node_degree(vertex_type="Person", vertex_id='x"); PRINT 1; //')
        query_arg = self.mock_conn.runInterpretedQuery.call_args[0][0]
        self.assertIn('to_vertex("x\\"); PRINT 1; //", "Person")', query_arg)

    @patch(PATCH_TARGET)
    async def test_multiple_edge_types(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runInterpretedQuery.return_value = [{"outgoing": 0, "incoming": 0}]

        await get_node_degree(vertex_type="Person", vertex_id="u1", edge_type="FOLLOWS|LIKES")
        query_arg = self.mock_conn.runInterpretedQuery.call_args[0][0]
        self.assertIn('outdegree(["FOLLOWS", "LIKES"])', query_arg)
        self.assertIn("((FOLLOWS|LIKES):e)", query_arg)

    @patch(PATCH_TARGET)
    async def test_invalid_type_rejected_before_running(self, mock_gc):
        mock_gc.return_value = self.mock_conn

        for kwargs in ({"vertex_type": 'Person")'}, {"vertex_type": "Person", "edge_type": 'A", "B'}):
            result = await get_node_degree(vertex_id="u1", **kwargs)
            self.assert_error(result)
        self.mock_conn.runInterpretedQuery.assert_not_called()


class TestProfilePropagation(MCPToolTestBase):
    """Verify profile is forwarded to get_connection for statistics tools."""

    @patch(PATCH_TARGET)
    async def test_get_vertex_count_with_profile(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getVertexCount.return_value = 10

        result = await get_vertex_count(vertex_type="Person", profile="staging")
        self.assert_success(result)
        mock_gc.assert_called_with(profile="staging", graph_name=None)

    @patch(PATCH_TARGET)
    async def test_get_edge_count_with_profile(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getEdgeCount.return_value = 50

        result = await get_edge_count(edge_type="FOLLOWS", profile="analytics")
        self.assert_success(result)
        mock_gc.assert_called_with(profile="analytics", graph_name=None)


if __name__ == "__main__":
    unittest.main()
