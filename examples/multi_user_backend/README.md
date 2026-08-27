# Multi-user backend example

A FastAPI service that gives every logged-in user their own
**tigergraph-mcp subprocess** and **agent runtime**, with per-user
credentials and clean teardown on logout. This is **Pattern A** from
the multi-user deployment guide — process-per-user isolation, no
changes to the MCP server itself.

## When to use this

- You want each user to bring their own TigerGraph credentials.
- You expect up to a few hundred concurrent logged-in users.
- You don't want to refactor the MCP server.

For thousands of users, run `tigergraph-mcp --transport streamable-http`
instead and have each user's MCP client send credentials in `X-TG-*`
headers — one shared MCP server handles every session with per-session
TigerGraph connections.

## How it's structured

```
Browser
  │
  │   POST /login (tg_host, tg_username, tg_password)
  ▼
FastAPI backend (app.py)
  │
  ├─ validate creds via pyTigerGraph.getToken() → mint token, discard password
  │
  ▼
UserSessionManager (user_sessions.py)
  │
  ├─ user_id "alice" ─▶ tigergraph-mcp subprocess #1 ──▶ TG (alice's token)
  │                     LangGraph agent #1
  │
  ├─ user_id "bob"   ─▶ tigergraph-mcp subprocess #2 ──▶ TG (bob's token)
  │                     LangGraph agent #2
  │
  └─ idle sweeper: auto-logout users idle > 30 min (configurable)
```

Every chat message from a user is routed to **that user's** agent,
which has tools bound to **that user's** subprocess. The LLM never sees
credentials.

## Running it

```bash
pip install "tigergraph-mcp[llm]" fastapi uvicorn

export OPENAI_API_KEY=sk-...

uvicorn examples.multi_user_backend.app:app --reload
```

### Login

```bash
curl -X POST http://127.0.0.1:8000/login \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "tg_host": "https://acme.tgcloud.io",
    "tg_username": "alice",
    "tg_password": "alicepass",
    "graphname": "MyGraph"
  }'
```

### Chat

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "Count the vertices in MyGraph"}'
```

### Logout

```bash
curl -X POST 'http://127.0.0.1:8000/logout?user_id=alice'
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `LLM_MODEL` | `openai:gpt-4.1-mini-2025-04-14` | Model passed to `init_chat_model`. |
| `MAX_SESSIONS` | `100` | Refuse new logins past this cap (returns `RuntimeError`). |
| `SESSION_IDLE_TIMEOUT` | `1800` | Seconds of inactivity before auto-logout. |
| `OPENAI_API_KEY` | _required_ | Or any API key the chosen `LLM_MODEL` needs. |

## Production checklist

- Front the FastAPI service with TLS (e.g. behind nginx or a managed
  load balancer); credentials cross the wire on `/login`.
- Wrap `/login` and `/chat` with your own session-cookie or JWT layer
  so `user_id` isn't trusted from the request body.
- Raise `ulimit -u` and `ulimit -n` to comfortably exceed
  `MAX_SESSIONS`; each subprocess opens stdio pipes and TG sockets.
- Subprocess crashes are surfaced as exceptions on the next agent call;
  catch and prompt the user to log in again.
- For users idle for hours, the idle sweeper closes the subprocess but
  preserves no resumable state — they re-login like a fresh session.

## Cost model

Each logged-in user costs roughly **one Python subprocess** (~100 MB
resident) plus its TigerGraph socket pool. Concurrency is bounded by
the host's process limit far more than by RAM. For larger fleets, run
`tigergraph-mcp --transport streamable-http` and let users connect
their MCP clients directly — one shared server, session-keyed
TigerGraph connections (~2–5 MB per user).
