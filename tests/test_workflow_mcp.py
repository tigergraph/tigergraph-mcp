"""
Integration test: Example 1 workflow from docs/copilot_setup.md via MCP protocol.

Launches the tigergraph-mcp server as a subprocess and drives it through the
MCP stdio transport — the same way GitHub Copilot, Claude Code, or any
MCP-compatible agent would.

Workflow under test:
  1. Create graph with Person + Company vertices and Knows + Works_For edges
  2. Load data via add_nodes / add_edges (the "agent" approach)
  3. Verify vertex and edge counts
  4. Cleanup (drop graph)

Requirements:
  - A running TigerGraph instance (set TG_HOST, TG_USERNAME, TG_PASSWORD)
  - pip install tigergraph-mcp[dev]

Run:
    TG_HOST=http://192.168.11.11 pytest tests/test_workflow_mcp.py -v -s

Skip in CI (no live DB):
    pytest tests/ -v --ignore=tests/test_workflow_mcp.py
"""

import asyncio
import json
import os
import re
import sys
from datetime import timedelta

import pytest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Skip the entire module when no TG_HOST is configured (e.g. CI).
pytestmark = pytest.mark.skipif(
    not os.environ.get("TG_HOST"),
    reason="TG_HOST not set — skipping MCP integration tests",
)

GRAPH = "WorkflowTestGraph"
TIMEOUT = timedelta(seconds=30)

# ── CSV data from copilot_setup.md Example 1 ─────────────────────────

PERSONS = [
    {"id": "p1", "name": "Alice", "age": 30, "gender": "Female"},
    {"id": "p2", "name": "Bob", "age": 32, "gender": "Male"},
    {"id": "p3", "name": "Charlie", "age": 28, "gender": "Male"},
]

COMPANIES = [
    {"id": "c1", "name": "TigerGraph", "industry": "Technology"},
    {"id": "c2", "name": "Acme", "industry": "Manufacturing"},
]

KNOWS_EDGES = [
    {"source_type": "Person", "source_id": "p1", "target_type": "Person", "target_id": "p2", "since": "2020-01-01"},
    {"source_type": "Person", "source_id": "p2", "target_type": "Person", "target_id": "p3", "since": "2021-06-15"},
]

WORKS_FOR_EDGES = [
    {"source_type": "Person", "source_id": "p1", "target_type": "Company", "target_id": "c1", "role": "Engineer"},
    {"source_type": "Person", "source_id": "p2", "target_type": "Company", "target_id": "c1", "role": "Manager"},
    {"source_type": "Person", "source_id": "p3", "target_type": "Company", "target_id": "c2", "role": "Analyst"},
]

# ── Helpers ───────────────────────────────────────────────────────────

_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def _server_params():
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "tigergraph_mcp.main"],
        env={
            "HOME": os.environ["HOME"],
            "PATH": os.environ["PATH"],
            "TG_HOST": os.environ["TG_HOST"],
            "TG_USERNAME": os.environ.get("TG_USERNAME", "tigergraph"),
            "TG_PASSWORD": os.environ.get("TG_PASSWORD", "tigergraph"),
            "TG_GS_PORT": os.environ.get("TG_GS_PORT", "14240"),
            "TG_RESTPP_PORT": os.environ.get("TG_RESTPP_PORT", "9000"),
        },
    )


def parse(result):
    """Extract the JSON payload from a CallToolResult."""
    text = result.content[0].text
    m = _JSON_BLOCK.search(text)
    if m:
        return json.loads(m.group(1))
    return json.loads(text)


async def call(session, tool, params=None):
    return await session.call_tool(tool, params or {}, read_timeout_seconds=TIMEOUT)


def assert_ok(result, msg=""):
    payload = parse(result)
    assert payload["success"], f"Expected success: {msg or payload.get('error', payload.get('summary'))}"
    return payload


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_workflow():
    """End-to-end MCP workflow: create graph -> load data -> verify -> cleanup."""

    async with stdio_client(_server_params()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # ── 0. Verify server is alive ────────────────────────
            tools = await session.list_tools()
            assert len(tools.tools) > 0, "No tools found on the MCP server"

            # ── 0b. Cleanup from any prior failed run ────────────
            try:
                await call(session, "tigergraph__drop_graph", {"graph_name": GRAPH})
            except Exception:
                pass

            # ── 1. Create graph ──────────────────────────────────
            r = await call(session, "tigergraph__create_graph", {
                "graph_name": GRAPH,
                "vertex_types": [
                    {
                        "name": "Person",
                        "primary_id": "id",
                        "primary_id_type": "STRING",
                        "attributes": [
                            {"name": "name", "type": "STRING"},
                            {"name": "age", "type": "INT"},
                            {"name": "gender", "type": "STRING"},
                        ],
                    },
                    {
                        "name": "Company",
                        "primary_id": "id",
                        "primary_id_type": "STRING",
                        "attributes": [
                            {"name": "name", "type": "STRING"},
                            {"name": "industry", "type": "STRING"},
                        ],
                    },
                ],
                "edge_types": [
                    {
                        "name": "Knows",
                        "from_vertex": "Person",
                        "to_vertex": "Person",
                        "directed": False,
                        "attributes": [{"name": "since", "type": "STRING"}],
                    },
                    {
                        "name": "Works_For",
                        "from_vertex": "Person",
                        "to_vertex": "Company",
                        "directed": True,
                        "attributes": [{"name": "role", "type": "STRING"}],
                    },
                ],
            })
            p = assert_ok(r, "create_graph")
            assert p["data"]["vertex_type_count"] == 2
            assert p["data"]["edge_type_count"] == 2

            # ── 2. Verify schema ────────────────────────────────
            r = await call(session, "tigergraph__get_graph_schema", {"graph_name": GRAPH})
            p = assert_ok(r, "get_graph_schema")
            vtypes = {v["Name"] for v in p["data"]["schema"]["VertexTypes"]}
            etypes = {e["Name"] for e in p["data"]["schema"]["EdgeTypes"]}
            assert vtypes == {"Person", "Company"}
            assert etypes == {"Knows", "Works_For"}

            # ── 3. Load vertices ────────────────────────────────
            r = await call(session, "tigergraph__add_nodes", {
                "graph_name": GRAPH,
                "vertex_type": "Person",
                "vertices": PERSONS,
            })
            p = assert_ok(r, "add Person nodes")
            assert p["data"]["success_count"] == 3

            r = await call(session, "tigergraph__add_nodes", {
                "graph_name": GRAPH,
                "vertex_type": "Company",
                "vertices": COMPANIES,
            })
            p = assert_ok(r, "add Company nodes")
            assert p["data"]["success_count"] == 2

            # ── 4. Load edges ───────────────────────────────────
            r = await call(session, "tigergraph__add_edges", {
                "graph_name": GRAPH,
                "edge_type": "Knows",
                "edges": KNOWS_EDGES,
            })
            p = assert_ok(r, "add Knows edges")
            assert p["data"]["edge_count"] == 2

            r = await call(session, "tigergraph__add_edges", {
                "graph_name": GRAPH,
                "edge_type": "Works_For",
                "edges": WORKS_FOR_EDGES,
            })
            p = assert_ok(r, "add Works_For edges")
            assert p["data"]["edge_count"] == 3

            # ── 5. Verify counts (wait for data commit) ─────────
            await asyncio.sleep(3)

            r = await call(session, "tigergraph__get_vertex_count", {"graph_name": GRAPH})
            p = assert_ok(r, "get_vertex_count")
            assert p["data"]["total"] == 5
            assert p["data"]["counts_by_type"]["Person"] == 3
            assert p["data"]["counts_by_type"]["Company"] == 2

            r = await call(session, "tigergraph__get_edge_count", {"graph_name": GRAPH})
            p = assert_ok(r, "get_edge_count")
            assert p["data"]["total"] == 5
            assert p["data"]["counts_by_type"]["Knows"] == 2
            assert p["data"]["counts_by_type"]["Works_For"] == 3

            # ── 6. Cleanup ─────────────────────────────────────
            r = await call(session, "tigergraph__drop_graph", {"graph_name": GRAPH})
            assert_ok(r, "drop_graph")

            # Confirm it's gone.
            r = await call(session, "tigergraph__list_graphs")
            p = assert_ok(r, "list_graphs")
            assert GRAPH not in p["data"]["graphs"]
