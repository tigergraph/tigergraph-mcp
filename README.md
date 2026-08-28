# tigergraph-mcp

Model Context Protocol (MCP) server for TigerGraph — lets AI agents interact with TigerGraph through the MCP standard. All tools use pyTigerGraph's async APIs for optimal performance.

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Getting Started](#getting-started)
- [Usage](#usage)
  - [Running the MCP Server](#running-the-mcp-server)
    - [stdio (single user, one IDE/agent)](#stdio-default--single-user-one-ideagent)
    - [Streamable HTTP / SSE (multi-user, shared server)](#streamable-http--sse-multi-user-shared-server)
  - [HTTP Mode End-to-End](#http-mode-end-to-end)
  - [Configuration](#configuration)
  - [Multiple Connection Profiles](#multiple-connection-profiles)
    - [Helping the agent pick the right environment](#helping-the-agent-pick-the-right-environment)
  - [Multi-user Deployments (HTTP/SSE)](#multi-user-deployments-httpsse)
  - [Using with Existing Connection](#using-with-existing-connection)
- [Client Examples](#client-examples)
  - [LangChain / LangGraph over stdio](#langchain--langgraph-over-stdio)
  - [LangChain / LangGraph over HTTP](#langchain--langgraph-over-http)
  - [MCP SDK over stdio](#mcp-sdk-over-stdio)
  - [MCP SDK over HTTP](#mcp-sdk-over-http)
- [Available Tools](#available-tools)
- [Loading from a Data Warehouse](docs/warehouse_loading.md)
- [LLM-Friendly Features](#llm-friendly-features)
  - [Structured Responses](#structured-responses)
  - [Rich Tool Descriptions](#rich-tool-descriptions)
  - [Token Optimization](#token-optimization)
  - [Tool Discovery](#tool-discovery)
- [Notes](#notes)

## Requirements

- **Python 3.10 through 3.14**
- **MCP SDK 1.x or 2.x** — the server works with either generation of the `mcp` package. Client code differs between them; see [MCP SDK over HTTP](#mcp-sdk-over-http).
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

To serve over HTTP (`--transport streamable-http` or `sse`), also install a web stack:

```bash
pip install uvicorn starlette
```

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

The server talks MCP over its own **stdin and stdout**: it reads JSON-RPC messages from
standard input and writes replies to standard output, then exits when standard input
closes. Run it in a terminal and it simply waits for messages — there is no prompt and no
human-facing console. You normally never start it this way; the MCP client (Claude Code,
Cursor, GitHub Copilot Chat, a LangChain agent) spawns it as a subprocess and owns the
pipes. Running it by hand is mainly useful for checking that it starts:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"1"}}}' \
  | tigergraph-mcp
```

Because the client owns the process, credentials must reach it as environment variables —
from a `.env` file, or from the client's own `env` mapping. This is the right mode for any
single-user IDE integration.

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

Here the server **binds the chosen port and serves MCP over HTTP**, staying up until you
stop it — a long-lived service you start once (under systemd, a container, or whatever
supervises it), not a process a client spawns. Many clients connect to it concurrently,
and it does not read standard input at all.

Each MCP session gets its own connection pool, so concurrent users never share state. Clients connect at `http://<host>:<port>/mcp/` — **note the trailing slash**; `/mcp` returns a `307` redirect that some clients will not follow on `POST`. The mount path is configurable with `--mount-path`.

The server reads the same `.env` file and `TG_*` / `<PROFILE>_TG_*` variables as stdio, which supply each profile's topology and, optionally, its credentials. A client selects a profile with `X-TG-Profile` and may override any value with the other `X-TG-*` headers — see [Server-side profiles and header overrides](#server-side-profiles-and-header-overrides). With no headers at all, the default profile is used exactly as configured.

Authenticate the HTTP endpoint itself with a reverse proxy / API gateway when exposing it beyond localhost. The MCP server checks TigerGraph credentials, not who may reach the URL.

### HTTP Mode End-to-End

Run one shared server that several people or services connect to. Five steps.

**1. Install with the web stack**

```bash
pip install tigergraph-mcp uvicorn starlette
```

**2. Describe your TigerGraph sites**

Put the environments in an env file. The unprefixed `TG_*` variables are the default
profile; each `<NAME>_TG_*` group adds another. Credentials here are optional — include
them for a shared or demo deployment, omit them to require every client to send its own:

```bash
# /etc/tigergraph-mcp/.env
TG_DEFAULT_PROFILE=prod

PROD_TG_HOST=https://mycompany.i.tgcloud.io
PROD_TG_USERNAME=analyst
PROD_TG_PASSWORD=...

STAGING_TG_HOST=https://tg-staging.example.com
STAGING_TG_USERNAME=analyst
STAGING_TG_PASSWORD=...
```

**3. Start the server**

```bash
tigergraph-mcp --transport streamable-http \
  --host 0.0.0.0 --port 8000 \
  --env-file /etc/tigergraph-mcp/.env
```

It binds the port and serves until stopped, so run it under systemd, a container, or
whatever supervises your services. Put a reverse proxy or API gateway in front for TLS
and to control who may reach the URL.

**4. Check that it is up**

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/mcp/ \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

| Response | Meaning |
|---|---|
| `200` | Up, and the default profile's credentials work |
| `400` | Up, but the request does not name a reachable site (e.g. an unknown profile) |
| `401` | Up, but no usable credentials — the client must send them |
| `502` | Up, but TigerGraph itself could not be reached |
| `307` | You omitted the **trailing slash** on `/mcp/` |
| connection refused | The server is not running |

**5. Point a client at it**

The URL is `http://<host>:<port>/mcp/` — keep the trailing slash. Credentials, when the
client supplies them, travel as `X-TG-*` headers; omit them to use the server's default
profile as configured.

*Cursor, VS Code, or any editor using `mcp.json`:*

```json
{
  "servers": {
    "tigergraph-mcp-server": {
      "type": "http",
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "X-TG-Profile": "staging"
      }
    }
  }
}
```

The scheme is whatever the server is reachable on. `tigergraph-mcp` itself serves plain
**HTTP** and does not terminate TLS, so use `http://` when connecting to it directly. A
deployed instance normally sits behind a reverse proxy that adds TLS, in which case the
URL is the proxy's — `https://my-tg-mcp.internal/mcp/`. Credentials travel in headers, so
anything beyond localhost should be `https://`.

To connect as yourself rather than as the profile's configured user, add your own
credentials — keeping secrets out of the file by referencing the environment:

```json
      "headers": {
        "X-TG-Host": "https://mycompany.i.tgcloud.io",
        "X-TG-Api-Token": "${env:TG_API_TOKEN}"
      }
```

*Python, LangChain, or any MCP SDK client:* see [Client Examples](#client-examples) for
runnable versions of both. The HTTP client API differs between MCP SDK generations, so
check which one you have with `pip show mcp`:

```python
# MCP SDK 2.x
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with httpx2.AsyncClient(headers={"X-TG-Profile": "staging"}) as http_client:
    async with streamable_http_client(
        "http://localhost:8000/mcp/", http_client=http_client
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("tigergraph__list_graphs", {})
```

```python
# MCP SDK 1.x
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client(
    "http://localhost:8000/mcp/", headers={"X-TG-Profile": "staging"}
) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        await session.call_tool("tigergraph__list_graphs", {})
```

Which profile a call uses, and how an agent picks one, is covered in
[Multiple Connection Profiles](#multiple-connection-profiles); the full header list is in
[Server-side profiles and header overrides](#server-side-profiles-and-header-overrides).

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

#### Selecting the default profile

```bash
# Switch to staging for this run
TG_DEFAULT_PROFILE=staging tigergraph-mcp

# Or set permanently in .env
TG_DEFAULT_PROFILE=prod
```

`TG_DEFAULT_PROFILE` names the profile used when a call does not specify one. If it is not set, the unprefixed `TG_*` variables are the default profile. `TG_PROFILE` is accepted as an alias.

Omitting the `profile` argument and passing `profile="default"` mean the same thing — the default profile — in both stdio and HTTP mode.

#### Switching profiles per call

Every tool accepts an optional `profile` argument, so an agent can route individual calls to different environments without restarting the server. Connections are pooled per profile and reused across calls. `list_connections` reports the configured profiles, which one is the default, and which are currently connected — in HTTP mode scoped to the calling session.

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

#### Helping the agent pick the right environment

Users normally name an environment the way it is configured — "staging", "the prod
cluster". `list_connections` reports each profile's name **and its host**, so the agent can
also resolve the occasional bare hostname or URL to the profile that reaches it:

```json
{
  "default_profile": "dev",
  "profiles": [
    {"profile": "dev",     "host": "http://localhost",                "username": "tigergraph", "is_default": true,  "connected": true},
    {"profile": "prod",    "host": "https://mycompany.i.tgcloud.io",  "username": "analyst",    "is_default": false, "connected": false},
    {"profile": "staging", "host": "https://tg-staging.example.com",  "username": "analyst",    "is_default": false, "connected": false}
  ]
}
```

Note that `prod`'s host carries no hint of the profile name, so a user who names that
host cannot be served by guessing from profile names alone.

A system prompt that puts that to work:

```text
You are a TigerGraph assistant. The tigergraph-mcp server may be configured
with several environments, each identified by a profile name.

Discovering profiles
- Call `list_connections` before your first data access, and again whenever
  the user mentions an environment you have not seen.
- Each profile reports its name, host, and username, which one is the
  default, and which are already connected.
- Never invent or hardcode a profile name.

Choosing one
- Users normally name an environment, not a machine. If the user names a
  profile ("use staging", "on the prod cluster"), use that profile.
- If the user names a host or URL instead, match it against the `host`
  field. Several profiles may share one host, differing only in the user
  they connect as. In that case run the request against every matching
  profile and report the results per profile, rather than asking which
  one was meant.
- If nothing matches what the user named, say so and list the configured
  profiles with their hosts. Do not guess.
- If the user says nothing about an environment, use the default profile
  and mention which one you used.

Using one
- Pass `profile="<name>"` on every tool call meant for that environment.
- A single turn may use different profiles when the user compares
  environments.

Reporting
- Answer about the environments the user asked about. Do not list the
  profiles you considered and skipped, and do not narrate the lookup.
- Name the environment alongside each answer, so the user knows which
  one it came from — especially when reporting more than one.
```

With that prompt, a site named in plain language resolves to a profile:

```
User: How many vertices does MyGraph have on staging?

Agent:
  → get_vertex_count(profile="staging", graph_name="MyGraph")
  "On staging: 1,204 vertices."

User: And on mycompany.i.tgcloud.io?          # a host, not an environment

Agent:                                        # tool calls, not shown to the user
  → list_connections()                        # prod and prod_ro share that host
  → get_vertex_count(profile="prod",    graph_name="MyGraph")
  → get_vertex_count(profile="prod_ro", graph_name="MyGraph")

Agent replies:
  "Two profiles reach that host:
     prod (as analyst):     1,204 vertices
     prod_ro (as readonly): 1,204 vertices"
```

The reply names the environment behind each number and says nothing about `dev` or
`staging`, which the user did not ask about.

Omitting `profile`, or passing `"default"`, uses the default profile — `TG_DEFAULT_PROFILE` if set (or its alias `TG_PROFILE`), otherwise the unprefixed `TG_*` variables.

### Multi-user Deployments (HTTP/SSE)

Run one shared `tigergraph-mcp` HTTP server and let each logged-in user supply their own TigerGraph credentials. Sessions are isolated: every user's connection pool, profile state, and tool list lives in its own `SessionConnectionManager`.

#### Option 1 — Frontend backend owns the MCP client (recommended)

Your web backend authenticates the user, opens one MCP session per login carrying that
user's TigerGraph credentials as `X-TG-*` headers, and routes all of their agent traffic
through that session. The LLM never sees credentials.

```text
[user logs in]         backend validates the user (any IdP, or passthrough
                       TigerGraph auth) and mints a short-lived TG token.
[per-user session]     backend opens one MCP session with that user's
                       X-TG-* headers; the server validates them once and
                       builds that session's connection.
[agent traffic]        every tool call reuses the same session, and so the
                       same pooled TigerGraph connection.
[user logs out]        backend closes its client; the session's pool is
                       reclaimed after TG_HTTP_SESSION_IDLE_TIMEOUT.
```

Hold the session open for the user's lifetime rather than calling `get_tools()` per
request — see [Client Examples](#client-examples) for why.

A working reference lives in [`examples/multi_user_backend/`](examples/multi_user_backend/):
a FastAPI service that does this with subprocess-per-user over stdio. To use the shared
HTTP server instead, point each user's `MultiServerMCPClient` at `streamable_http` with
your server's URL and put that user's credentials in `headers`.

The `authenticate` tool remains available for re-pointing a live session mid-conversation:
omit `profile` to replace the session's default connection, or name one to replace just
that profile. Credentials are checked before the swap, so a bad one is reported at once
and the existing connection keeps working. It is not needed when credentials arrive as
headers.

#### Option 2 — Cursor / Copilot pointing at a remote MCP server

Each developer's `mcp.json` names a profile, or carries their own TigerGraph credentials
as headers. Credentials are checked against TigerGraph when the session is established, so
a bad one surfaces as a connection failure rather than a puzzling tool error:

```json
{
  "servers": {
    "tigergraph-mcp-server": {
      "type": "http",
      "url": "https://my-tg-mcp.internal/mcp/",
      "headers": {
        "X-TG-Host": "https://mycompany.i.tgcloud.io",
        "X-TG-Api-Token": "${env:TG_API_TOKEN}"
      }
    }
  }
}
```

See [HTTP Mode End-to-End](#http-mode-end-to-end) for setting the server up in the first
place.

#### Server-side profiles and header overrides

The HTTP server reads the same `.env` file and `TG_*` / `<PROFILE>_TG_*` variables as stdio (`--env-file`, or a `.env` discovered from the working directory). Profiles define **topology** — host, ports, graph, TLS — and may optionally carry credentials. A request selects one with `X-TG-Profile`, and any `X-TG-*` header overrides that profile's value **for that session only**:

| Headers sent | Connection used |
|---|---|
| `X-TG-Profile` only | that profile's topology **and** its configured credentials |
| `X-TG-Profile` + credential headers | that profile's topology, the caller's identity |
| Credential headers only | the `default` profile's topology, the caller's identity |
| No headers | the `default` profile exactly as configured |

`TG_DEFAULT_PROFILE` (alias `TG_PROFILE`) names which profile acts as the default for requests that don't send `X-TG-Profile`; unset, the unprefixed `TG_*` variables are the default profile. Naming a profile the server does not define is an error rather than a silent fallback. `TG_HTTP_ALLOWED_PROFILES=demo,staging` narrows which profiles clients may name.

A named profile uses its own credentials where it defines them, and the unprefixed `TG_*` ones where it does not — the same inheritance stdio uses. If no credentials are configured anywhere, every caller must supply their own.

Whether profiles carry credentials at all is the operator's decision when writing the env file. Credentials in the env file are a shared identity usable by anyone who can reach the server, which suits a demo or single-user deployment; an env file with topology only forces every caller to identify itself, which is what you want for multi-user deployments.

Within a session, a tool call may name any configured profile with its `profile` argument. That connection is opened in **that session's** pool and is never shared with other sessions — the same shape as a stdio process holding several profiles. Omitting `profile`, or passing `"default"`, resolves to the server's default profile, exactly as it does in stdio. A client normally sends no `X-TG-Profile` at all, which establishes the session on that default profile.

Failures are reported by kind, so a caller can tell a wrong address from a wrong login:

| Status | Meaning | Examples |
|---|---|---|
| `400` | Topology — the request does not describe a reachable server | unknown profile, no host resolvable |
| `401` | Credentials — missing, or rejected by TigerGraph | no identity supplied, wrong password |
| `502` | Connection — the server could not be reached | unroutable host, wrong port, timeout |

The reachability probe is bounded by `TG_HTTP_VALIDATE_TIMEOUT` (default 10 seconds) so an unroutable host fails promptly instead of hanging the request.

Idle sessions are reclaimed after `TG_HTTP_SESSION_IDLE_TIMEOUT` seconds (default 900; `0` keeps them for the life of the process), so pools do not accumulate when clients open many short-lived sessions. A reclaimed session is not broken — a later request rebuilds its pool.

Credentials are checked against TigerGraph when the session's connection is established, not on every request — a client's headers are fixed for the life of its session, so re-checking proves nothing new. A rejected credential never establishes a session. Requests that cannot be resolved at all (unknown profile, no host) are refused without contacting TigerGraph.

Access control to the endpoint itself remains the deployment's responsibility — put a reverse proxy or API gateway in front.

Recognised headers (they mirror the `TG_*` env vars used in stdio mode):

| Header | Env-var equivalent |
|---|---|
| `X-TG-Profile` | selects a server-side profile (`<PROFILE>_TG_*`) |
| `X-TG-Host` | `TG_HOST` |
| `X-TG-Graphname` | `TG_GRAPHNAME` |
| `X-TG-Username` + `X-TG-Password` | `TG_USERNAME` + `TG_PASSWORD` |
| `X-TG-Secret` | `TG_SECRET` |
| `X-TG-Api-Token` | `TG_API_TOKEN` |
| `X-TG-Jwt-Token` | `TG_JWT_TOKEN` |
| `X-TG-Restpp-Port`, `X-TG-Gs-Port`, `X-TG-Ssl-Port` | `TG_RESTPP_PORT`, `TG_GS_PORT`, `TG_SSL_PORT` |
| `X-TG-Tgcloud` (`true`/`false`) | `TG_TGCLOUD` |
| `X-TG-Cert-Path` | `TG_CERT_PATH` |

A host and an identity must be resolvable from the selected profile, the headers, or a combination of the two; every header is otherwise optional.

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

> **Hold one session for the run.** `MultiServerMCPClient(...)` connects nothing, and
> `await client.get_tools()` opens a session only to list the tools, then closes it —
> the returned tools carry a connection *config*, so **each tool call opens a new
> session**. Over stdio that spawns a `tigergraph-mcp` process per call; over HTTP it
> creates a session, a connection, and a credential check per call. Binding tools to a
> session held open by `client.session(...)` reuses one process (or one session and its
> pooled connection) for the whole run — in a measured 8-call agent run, 1 session
> instead of 9, and roughly 4× faster. Use `get_tools()` only for one-shot scripts.

### LangChain / LangGraph over stdio

The client starts `tigergraph-mcp` as a subprocess and passes credentials as env vars.

```python
import asyncio
from pathlib import Path

from dotenv import dotenv_values
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

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


async def main():
    async with client.session("tigergraph-mcp-server") as session:
        tools = await load_mcp_tools(session)
        # ... run your agent here; every tool call reuses this session
        print([t.name for t in tools])


asyncio.run(main())
```

> **Note:** Instead of loading a `.env` file, you can pass credentials directly in
> the `env` mapping:
>
> ```python
>     "env": {
>       "TG_HOST": "http://localhost",
>       "TG_USERNAME": "tigergraph",
>       "TG_PASSWORD": "tigergraph",
>       "TG_GRAPHNAME": "MyGraph"
>     }
> ```
>
> Either way the credentials must be in `env`: the subprocess does not inherit
> your shell environment.

### LangChain / LangGraph over HTTP

The server is already running elsewhere; the client only connects. Credentials travel
as headers, so nothing about TigerGraph needs to be configured on this side.

```python
import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

client = MultiServerMCPClient(
    {
        "tigergraph-mcp-server": {
            "transport": "streamable_http",
            "url": "http://localhost:8000/mcp/",   # trailing slash required
            "headers": {
                # Omit these entirely to use the server's default profile.
                "X-TG-Profile": "staging",
                "X-TG-Username": "my_user",
                "X-TG-Password": "my_password",
            },
        },
    }
)


async def main():
    async with client.session("tigergraph-mcp-server") as session:
        tools = await load_mcp_tools(session)
        print([t.name for t in tools])


asyncio.run(main())
```

### MCP SDK over stdio

`stdio_client` does **not** pass your environment to the subprocess — it forwards only a
minimal safe set (`HOME`, `PATH`, `SHELL`, …). Credentials must be supplied explicitly
via `env`, or the server will fall back to its defaults and try `http://127.0.0.1`.

```python
import asyncio
from pathlib import Path

from dotenv import dotenv_values
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

env_dict = dotenv_values(dotenv_path=Path(".env").expanduser().resolve())


async def main():
    server_params = StdioServerParameters(
        command="tigergraph-mcp",
        args=["-vv"],
        env={**get_default_environment(), **env_dict},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")

            result = await session.call_tool("tigergraph__list_graphs", arguments={})
            for content in result.content:
                print(content.text)


asyncio.run(main())
```

### MCP SDK over HTTP

The HTTP client API changed between MCP SDK generations. Check yours with `pip show mcp`
— a fresh `pip install` currently gets 2.x. In 1.x the function took `headers` and yielded
three values; in 2.x it takes an `http_client` carrying the headers and yields two.

```python
# MCP SDK 2.x
import asyncio

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = "http://localhost:8000/mcp/"           # trailing slash required
HEADERS = {                                  # omit to use the default profile
    "X-TG-Profile": "staging",
}


async def main():
    async with httpx2.AsyncClient(headers=HEADERS) as http_client:
        async with streamable_http_client(URL, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                print(f"Available tools: {[t.name for t in tools.tools]}")

                # Every call reuses this session's pooled connection.
                result = await session.call_tool("tigergraph__list_graphs", arguments={})
                for content in result.content:
                    print(content.text)

                # Route one call to another configured profile.
                await session.call_tool(
                    "tigergraph__list_graphs", arguments={"profile": "prod"}
                )


asyncio.run(main())
```

```python
# MCP SDK 1.x
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://localhost:8000/mcp/"
HEADERS = {"X-TG-Profile": "staging"}


async def main():
    async with streamablehttp_client(URL, headers=HEADERS) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("tigergraph__list_graphs", arguments={})
            for content in result.content:
                print(content.text)


asyncio.run(main())
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
- `tigergraph__create_loading_job` — from files, or from a `data_source` + `query` pair to load the result of a SQL query against a warehouse
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
- `tigergraph__get_data_source_types` — List supported types and their configuration keys
- `tigergraph__preview_sample_data`

Supported data source types:

| Family | Types |
|---|---|
| Object storage | `s3`, `gcs`, `abs` (alias: `azure_blob`) |
| Data warehouse | `snowflake`, `bigquery`, `postgresql` |
| Lakehouse | `iceberg` |
| Streaming | `kafka`, `kafka_v2`, `mirrormaker` |

Each type takes different configuration keys. Call `tigergraph__get_data_source_types`
for the required keys and a worked example, or see
[Loading from a data warehouse](docs/warehouse_loading.md).

Credentials in `config` are sent to TigerGraph but masked in tool responses, so they
do not appear in a conversation transcript.

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
