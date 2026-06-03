# tigergraph-mcp

Model Context Protocol (MCP) server for TigerGraph — lets AI agents interact with TigerGraph through the MCP standard. All tools use pyTigerGraph's async APIs for optimal performance.

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Getting Started](#getting-started)
- [Usage](#usage)
  - [Running the MCP Server](#running-the-mcp-server)
  - [Configuration](#configuration)
  - [Multiple Connection Profiles](#multiple-connection-profiles)
  - [Multi-user Deployments (HTTP/SSE)](#multi-user-deployments-httpsse)
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

## Requirements

- **Python 3.10, 3.11, or 3.12**
- **TigerGraph 4.1 or later** — Install from the [TigerGraph Downloads page](https://dl.tigergraph.com/) or use [TigerGraph Savanna](https://savanna.tgcloud.io/) for a managed cloud instance.

> **Recommended: TigerGraph 4.2+** to enable TigerVector and advanced hybrid retrieval features.

## Installation

Install with **pip**:

```bash
pip install tigergraph-mcp
```

Or with **conda** (from the `tigergraph` channel):

```bash
conda install -c tigergraph tigergraph-mcp
```

This installs:
- `pyTigerGraph>=2.0.4` — the TigerGraph Python SDK
- `mcp>=1.0.0` — the MCP SDK
- `pydantic>=2.0.0` — for data validation
- `click` — for the CLI entry point
- `python-dotenv>=1.0.0` — for loading `.env` files

To enable the `tigergraph__generate_gsql` and `tigergraph__generate_cypher` tools (LLM-powered query generation), install the optional `[llm]` extras (pip only):

```bash
pip install "tigergraph-mcp[llm]"
```


## Getting Started

TigerGraph-MCP supports multiple AI agent frameworks. Choose the one that fits your workflow:

### LangGraph (Recommended)

LangGraph is ideal for building stateful, agent-based workflows with complex tool chaining. Setup guide and full chatbot example:

- [LangGraph Setup](docs/langgraph_setup.md)
- [Chatbot example code](examples/chatbot_langgraph/)
- [Example transcripts](docs/chatbot_langgraph_examples/)

### CrewAI

CrewAI provides a simpler starting point for basic agentic workflows with a web-based UI:

- [CrewAI Setup](docs/crewai_setup.md)
- [Chatbot example code](examples/chatbot_crewai/)

### GitHub Copilot Chat (VS Code)

For quick tasks or straightforward tool invocations directly in your editor:

- [Copilot Chat Setup](docs/copilot_setup.md)

## Usage

### Running the MCP Server

#### stdio (default — single user, one IDE/agent)

```bash
tigergraph-mcp
```

Credentials come from env vars or a `.env` file. This is the right mode for Claude Code, Cursor, GitHub Copilot Chat, or any single-user IDE integration.

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

#### Streamable HTTP / SSE (multi-user, shared server)

```bash
tigergraph-mcp --transport streamable-http --host 0.0.0.0 --port 8000
# legacy SSE shape:
tigergraph-mcp --transport sse --host 0.0.0.0 --port 8000
```

In HTTP modes each MCP session gets its own connection pool, so concurrent users don't share state. Clients connect at `http://<host>:<port>/mcp` (the mount path is configurable via `--mount-path`).

Credentials per session come from one of two places:

1. The `authenticate` MCP tool (see [Multi-user Deployments](#multi-user-deployments-httpsse) below) — the client registers credentials as its first call.
2. The same `TG_*` / `<PROFILE>_TG_*` env vars used by stdio — useful when every session should share one cluster.

Authenticate the HTTP endpoint itself with a reverse proxy / API gateway when exposing it beyond localhost. The MCP server does not perform user authentication on its own.

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

When `TG_API_TOKEN` (or `TG_JWT_TOKEN`) is set, the server uses token-based authentication (`Authorization: Bearer <token>`) and ignores username/password. You can obtain a token via `pyTigerGraph`'s `getToken()` method or by directly calling TigerGraph's token generation endpoint.

When only username/password are provided and the TigerGraph instance requires a token for RESTPP endpoints, pyTigerGraph auto-mints one on the first 401 response and transparently retries the request — no manual token setup needed.

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

#### Switching profiles per call

Every tool accepts an optional `profile` argument, so an agent can route individual calls to different environments without restarting the server. Connections are pooled per profile and reused across calls.

```
User: Compare the vertex count of MyGraph between staging and prod.

Agent:
  → get_vertex_count(profile="staging", graph_name="MyGraph")
  → get_vertex_count(profile="prod",    graph_name="MyGraph")

User: Show me the schema on staging, then run this GSQL on prod:
      SHOW VERTEX Person

Agent:
  → get_graph_schema(profile="staging", graph_name="MyGraph")
  → gsql(profile="prod", command="SHOW VERTEX Person")
```

A minimal system prompt that lets the agent discover profiles at runtime:

```text
You are a TigerGraph assistant with access to multiple environments
through the tigergraph-mcp server.

At the start of a session — or whenever the user references an
environment you haven't seen yet — call the `list_connections` tool
to discover available profiles. Do not assume or hardcode profile names.

Most tools accept an optional `profile` argument. When the user names
an environment, pass `profile="<name>"` to the tool calls in that turn.
If the user doesn't specify a profile, use the default profile.
```

Omitting `profile` falls back to `TG_PROFILE`, then `"default"`.

### Multi-user Deployments (HTTP/SSE)

Run one shared `tigergraph-mcp` HTTP server and let each logged-in user supply their own TigerGraph credentials. Sessions are isolated: every user's connection pool, profile state, and tool list lives in its own `SessionConnectionManager`.

#### Option 1 — Frontend backend owns the MCP client (recommended)

Your web backend authenticates the user, opens an MCP session per login, calls `tigergraph__authenticate` once to register their TigerGraph credentials, then routes all subsequent agent traffic through that session. The LLM never sees credentials.

```text
[user logs in]              backend validates the user (any IdP or
                            passthrough TigerGraph auth) and mints a
                            short-lived TigerGraph token.
[per-user MCP session]      backend opens one MCPClient per user and
                            invokes `tigergraph__authenticate(host=...,
                            api_token=...)` as the session's first call.
[agent traffic]              every subsequent tool call goes to the
                            same session → same TigerGraph connection.
[user logs out]             backend closes the MCPClient → MCP server
                            drops the session's connection pool.
```

A working reference lives in [`examples/multi_user_backend/`](examples/multi_user_backend/): a FastAPI service that does the above with subprocess-per-user (stdio). To use the shared HTTP server instead, point each user's `MultiServerMCPClient` at `streamable_http` with the URL of your tigergraph-mcp instance, and call `tigergraph__authenticate` instead of relying on env-var profiles.

#### Option 2 — Cursor / Copilot pointing at a remote MCP server

Each developer's `mcp.json` carries their own TigerGraph credentials as headers. The MCP server validates them against TigerGraph on every request and 401s on failure, so a bad credential surfaces as a connection error rather than a tool failure:

```json
{
  "servers": {
    "tigergraph-mcp-server": {
      "type": "http",
      "url": "https://my-tg-mcp.internal/mcp",
      "headers": {
        "X-TG-Host": "https://acme.tgcloud.io",
        "X-TG-Api-Token": "${env:TG_API_TOKEN}"
      }
    }
  }
}
```

Recognised credential headers (mirror the `TG_*` env vars used in stdio mode):

| Header | Env-var equivalent |
|---|---|
| `X-TG-Host` (required) | `TG_HOST` |
| `X-TG-Graphname` | `TG_GRAPHNAME` |
| `X-TG-Username` + `X-TG-Password` | `TG_USERNAME` + `TG_PASSWORD` |
| `X-TG-Secret` | `TG_SECRET` |
| `X-TG-Api-Token` | `TG_API_TOKEN` |
| `X-TG-Jwt-Token` | `TG_JWT_TOKEN` |
| `X-TG-Restpp-Port`, `X-TG-Gs-Port`, `X-TG-Ssl-Port` | `TG_RESTPP_PORT`, `TG_GS_PORT`, `TG_SSL_PORT` |
| `X-TG-Tgcloud` (`true`/`false`) | `TG_TGCLOUD` |
| `X-TG-Cert-Path` | `TG_CERT_PATH` |

`X-TG-Host` plus one of (`X-TG-Api-Token`, `X-TG-Jwt-Token`, `X-TG-Username` + `X-TG-Password`) is required; the rest are optional.

For per-call credential routing inside the agent's conversation, have the agent call `authenticate` once at session start:

```text
User: Connect to my TigerGraph at https://acme.tgcloud.io with token eyJ...
Agent:
  → authenticate(host="https://acme.tgcloud.io", api_token="eyJ...")
  → get_graph_schema(graph_name="MyGraph")
```

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
        "tigergraph-mcp-server": {
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
- `tigergraph__update_query_description` / `tigergraph__get_query_description` — Set or read query and per-parameter descriptions (TigerGraph 4.0+)
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

### Connection / Session
- `tigergraph__list_connections` / `tigergraph__show_connection` — Inspect configured profiles
- `tigergraph__authenticate` — Register per-session TigerGraph credentials (HTTP/SSE mode)

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
