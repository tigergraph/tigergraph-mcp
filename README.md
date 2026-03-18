# tigergraph-mcp

Model Context Protocol (MCP) server for TigerGraph — lets AI agents interact with TigerGraph through the MCP standard. All tools use pyTigerGraph's async APIs for optimal performance.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
  - [Running the MCP Server](#running-the-mcp-server)
  - [Configuration](#configuration)
  - [Multiple Connection Profiles](#multiple-connection-profiles)
  - [Using with Existing Connection](#using-with-existing-connection)
- [Client Examples](#client-examples)
  - [Using MultiServerMCPClient](#using-multiserverMCPclient)
  - [Using MCP Client SDK Directly](#using-mcp-client-sdk-directly)
- [Available Tools](#available-tools)
- [LLM-Friendly Features](#llm-friendly-features)
  - [Structured Responses](#structured-responses)
  - [Rich Tool Descriptions](#rich-tool-descriptions)
  - [Token Optimization](#token-optimization)
  - [Tool Discovery](#tool-discovery)
- [Notes](#notes)

## Installation

```bash
pip install tigergraph-mcp
```

This installs:
- `pyTigerGraph>=2.0.1` — the TigerGraph Python SDK
- `mcp>=1.0.0` — the MCP SDK
- `pydantic>=2.0.0` — for data validation
- `click` — for the CLI entry point
- `python-dotenv>=1.0.0` — for loading `.env` files

To enable the `tigergraph__generate_gsql` and `tigergraph__generate_cypher` tools (LLM-powered query generation):

```bash
pip install "tigergraph-mcp[llm]"
```

> **Migrating from `pyTigerGraph[mcp]`?** `pip install pyTigerGraph[mcp]` now installs `tigergraph-mcp` automatically. Update your imports from `pyTigerGraph.mcp` to `tigergraph_mcp`.

## Usage

### Running the MCP Server

```bash
tigergraph-mcp
```

With a custom `.env` file:

```bash
tigergraph-mcp --env-file /path/to/.env
```

With verbose logging:

```bash
tigergraph-mcp -v    # INFO level
tigergraph-mcp -vv   # DEBUG level
```

Or programmatically:

```python
from tigergraph_mcp import serve
import asyncio

asyncio.run(serve())
```

### Configuration

The MCP server reads connection configuration from environment variables. You can set these either directly or in a `.env` file.

#### Using a .env File (Recommended)

Create a `.env` file in your project directory:

```bash
# .env — Username/Password authentication
TG_HOST=http://localhost
TG_GRAPHNAME=MyGraph  # Optional — can be omitted if the database has multiple graphs
TG_USERNAME=tigergraph
TG_PASSWORD=tigergraph
TG_RESTPP_PORT=9000
TG_GS_PORT=14240
```

Or use an API token instead of username/password:

```bash
# .env — API Token authentication
TG_HOST=http://localhost
TG_GRAPHNAME=MyGraph
TG_API_TOKEN=your_api_token_here
```

When `TG_API_TOKEN` (or `TG_JWT_TOKEN`) is set, the server uses token-based authentication (`Authorization: Bearer <token>`) and ignores username/password. You can obtain a token via `pyTigerGraph`'s `getToken()` method or from the TigerGraph Admin Portal.

The server loads the `.env` file automatically. Environment variables take precedence over `.env` values.

#### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TG_HOST` | `http://127.0.0.1` | TigerGraph host |
| `TG_GRAPHNAME` | _(empty)_ | Graph name (optional) |
| `TG_USERNAME` | `tigergraph` | Username |
| `TG_PASSWORD` | `tigergraph` | Password |
| `TG_SECRET` | _(empty)_ | GSQL secret (optional) |
| `TG_API_TOKEN` | _(empty)_ | API token (optional) |
| `TG_JWT_TOKEN` | _(empty)_ | JWT token (optional) |
| `TG_RESTPP_PORT` | `9000` | REST++ port |
| `TG_GS_PORT` | `14240` | GSQL port |
| `TG_SSL_PORT` | `443` | SSL port |
| `TG_TGCLOUD` | `false` | Whether using TigerGraph Cloud |
| `TG_CERT_PATH` | _(empty)_ | Path to certificate (optional) |

### Multiple Connection Profiles

Define named profiles in your `.env` to work with multiple TigerGraph environments without changing any code.

#### Defining profiles

Each named profile uses a `<PROFILE>_` prefix on the standard `TG_*` variables. Only variables that differ from the default need to be set.

```bash
# .env

# Default profile (no prefix) — password auth
TG_HOST=http://localhost
TG_USERNAME=tigergraph
TG_PASSWORD=tigergraph
TG_GRAPHNAME=MyGraph

# Staging profile — token auth
STAGING_TG_HOST=https://staging.example.com
STAGING_TG_API_TOKEN=staging_token_here
STAGING_TG_TGCLOUD=true

# Production profile — password auth
PROD_TG_HOST=https://prod.example.com
PROD_TG_USERNAME=admin
PROD_TG_PASSWORD=prod_secret
PROD_TG_GRAPHNAME=ProdGraph
PROD_TG_TGCLOUD=true
```

Profiles are discovered automatically at startup. Any variable matching `<PROFILE>_TG_HOST` registers a new profile. Values not set for a named profile fall back to the default profile's values.

#### Selecting the active profile

```bash
# Switch to staging for this run
TG_PROFILE=staging tigergraph-mcp

# Or set permanently in .env
TG_PROFILE=prod
```

If `TG_PROFILE` is not set, the default profile is used.

### Using with Existing Connection

```python
from pyTigerGraph import AsyncTigerGraphConnection
from tigergraph_mcp import ConnectionManager

async with AsyncTigerGraphConnection(
    host="http://localhost",
    graphname="MyGraph",
    username="tigergraph",
    password="tigergraph",
) as conn:
    ConnectionManager.set_default_connection(conn)
    # ... run MCP tools ...
# HTTP connection pool is released on exit
```

## Client Examples

### Using MultiServerMCPClient

```python
from langchain_mcp_adapters import MultiServerMCPClient
from pathlib import Path
from dotenv import dotenv_values
import asyncio

env_dict = dotenv_values(dotenv_path=Path(".env").expanduser().resolve())

client = MultiServerMCPClient(
    {
        "tigergraph-mcp": {
            "transport": "stdio",
            "command": "tigergraph-mcp",
            "args": ["-vv"],
            "env": env_dict,
        },
    }
)

tools = asyncio.run(client.get_tools())
```

### Using MCP Client SDK Directly

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def call_tool():
    server_params = StdioServerParameters(
        command="tigergraph-mcp",
        args=["-vv"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")

            result = await session.call_tool(
                "tigergraph__list_graphs",
                arguments={}
            )
            for content in result.content:
                print(content.text)

asyncio.run(call_tool())
```

## Available Tools

### Global Schema Operations
- `tigergraph__get_global_schema` — Get the complete global schema via GSQL `LS`

### Graph Operations
- `tigergraph__list_graphs` — List all graph names in the database
- `tigergraph__create_graph` — Create a new graph with schema
- `tigergraph__drop_graph` — Drop a graph and its schema
- `tigergraph__clear_graph_data` — Clear all data from a graph (keeps schema)

### Schema Operations
- `tigergraph__get_graph_schema` — Get schema as structured JSON
- `tigergraph__show_graph_details` — Show schema, queries, loading jobs, and data sources

### Node Operations
- `tigergraph__add_node` / `tigergraph__add_nodes`
- `tigergraph__get_node` / `tigergraph__get_nodes`
- `tigergraph__delete_node` / `tigergraph__delete_nodes`
- `tigergraph__has_node`
- `tigergraph__get_node_edges`

### Edge Operations
- `tigergraph__add_edge` / `tigergraph__add_edges`
- `tigergraph__get_edge` / `tigergraph__get_edges`
- `tigergraph__delete_edge` / `tigergraph__delete_edges`
- `tigergraph__has_edge`

### Query Operations
- `tigergraph__run_query` — Run an interpreted query
- `tigergraph__run_installed_query` — Run an installed query
- `tigergraph__install_query` / `tigergraph__drop_query`
- `tigergraph__show_query` / `tigergraph__get_query_metadata` / `tigergraph__is_query_installed`
- `tigergraph__get_neighbors`

### Loading Job Operations
- `tigergraph__create_loading_job`
- `tigergraph__run_loading_job_with_file` / `tigergraph__run_loading_job_with_data`
- `tigergraph__get_loading_jobs` / `tigergraph__get_loading_job_status`
- `tigergraph__drop_loading_job`

### Statistics Operations
- `tigergraph__get_vertex_count` / `tigergraph__get_edge_count`
- `tigergraph__get_node_degree`

### GSQL Operations
- `tigergraph__gsql` — Execute raw GSQL
- `tigergraph__generate_gsql` — Generate GSQL from natural language (requires `[llm]`)
- `tigergraph__generate_cypher` — Generate openCypher from natural language (requires `[llm]`)

### Vector Schema Operations
- `tigergraph__add_vector_attribute` / `tigergraph__drop_vector_attribute`
- `tigergraph__list_vector_attributes` / `tigergraph__get_vector_index_status`

### Vector Data Operations
- `tigergraph__upsert_vectors`
- `tigergraph__load_vectors_from_csv` / `tigergraph__load_vectors_from_json`
- `tigergraph__search_top_k_similarity` / `tigergraph__fetch_vector`

### Data Source Operations
- `tigergraph__create_data_source` / `tigergraph__update_data_source`
- `tigergraph__get_data_source` / `tigergraph__drop_data_source`
- `tigergraph__get_all_data_sources` / `tigergraph__drop_all_data_sources`
- `tigergraph__preview_sample_data`

### Discovery & Navigation
- `tigergraph__discover_tools` — Search for tools by description or keywords
- `tigergraph__get_workflow` — Get step-by-step workflow templates
- `tigergraph__get_tool_info` — Get detailed information about a specific tool

## LLM-Friendly Features

### Structured Responses

Every tool returns a consistent JSON structure:

```json
{
  "success": true,
  "operation": "get_node",
  "summary": "Found vertex 'p123' of type 'Person'",
  "data": { ... },
  "suggestions": ["View connected edges: get_node_edges(...)"],
  "metadata": { "graph_name": "MyGraph" }
}
```

Error responses include actionable recovery hints:

```json
{
  "success": false,
  "operation": "get_node",
  "error": "Vertex not found",
  "suggestions": ["Verify the vertex_id is correct"]
}
```

### Rich Tool Descriptions

Each tool includes detailed descriptions with use cases, common workflows, tips, warnings, and related tools.

### Token Optimization

Responses are designed for efficient LLM token usage — no echoing of input parameters, only new information (results, counts, boolean answers).

### Tool Discovery

```python
# Find the right tool
result = await session.call_tool("tigergraph__discover_tools",
    arguments={"query": "how to add data to the graph"})

# Get a workflow template
result = await session.call_tool("tigergraph__get_workflow",
    arguments={"workflow_type": "data_loading"})

# Get detailed tool info
result = await session.call_tool("tigergraph__get_tool_info",
    arguments={"tool_name": "tigergraph__add_node"})
```

## Notes

- **Transport**: stdio by default
- **Error Detection**: GSQL operations include error detection for syntax and semantic errors
- **Connection Management**: Connections are pooled by profile and reused across requests; pool is released at server shutdown
- **Performance**: Persistent HTTP connection pool per profile; async non-blocking I/O; `v.outdegree()` for O(1) degree counting; batch operations for multiple vertices/edges
