# TigerGraph CrewAI Chatbot

A Panel web app with CrewAI agents that interact with TigerGraph via the MCP server.
Supports guided onboarding, schema creation, data loading, and general tool execution
through specialized crews.

## Architecture

```
Panel Web UI  →  ChatFlow (CrewAI Flow)
                      │
          ┌───────────┼───────────────┐
          ▼           ▼               ▼
    PlannerCrew  Onboarding     ToolExecutorCrews
       │          (inline)        (domain-based)
       ▼
    ┌──────────────┬──────────────┐
    ▼              ▼              ▼
  Schema       DataLoading    General Tool
  CreationCrews  Crews        Execution
  (draft/edit/   (draft/edit/
   create)        run)
```

## Requirements

- Python 3.10+
- A running TigerGraph instance
- An OpenAI API key (or compatible LLM provider)

## Setup

1. Install dependencies:

```bash
pip install pyTigerGraph-mcp crewai crewai-tools panel python-dotenv
```

2. Create a `.env` file with your TigerGraph and LLM credentials:

```bash
TG_HOST=http://127.0.0.1
TG_USERNAME=tigergraph
TG_PASSWORD=tigergraph
OPENAI_API_KEY=sk-...
```

You can also use API token authentication — see the main [README](../README.md) for details.

3. Run the chatbot:

```bash
panel serve examples/chatbot_crewai/main.py
```

Then open [http://localhost:5006/main](http://localhost:5006/main) in your browser.

## File Structure

```
examples/chatbot_crewai/
  __init__.py
  main.py                   -- Panel web app entry point
  chat_flow.py              -- CrewAI Flow: routing, onboarding, schema, loading
  chat_session_manager.py   -- Thread-safe chat session state
  crews/
    __init__.py
    planner_crew/            -- Intent detection + task planning
      planner_crew.py
      config/agents.yaml
      config/tasks.yaml
    schema_crew/             -- Schema drafting, editing, creation
      schema_crew.py
      config/agents.yaml
      config/tasks.yaml
    data_loading_crew/       -- Loading config drafting, editing, execution
      data_loading_crew.py
      config/agents.yaml
      config/tasks.yaml
    tool_executor_crew/      -- General tool execution (domain-based routing)
      tool_executor_crew.py
      config/agents.yaml
      config/tasks.yaml
```

## Usage

### Onboarding

Type `onboarding` in the chat to start a guided walkthrough:

1. **Data source setup** -- Automatically creates an S3 anonymous data source
2. **Data preview** -- Provide S3 file paths to preview sample data
3. **Schema design** -- AI designs a graph schema in readable markdown
4. **Schema review** -- Confirm or request changes interactively
5. **Loading config** -- AI drafts a loading job mapping files to the schema
6. **Data loading** -- Creates and runs the loading job

### General Commands

Any other message is analyzed by the Planner crew, which breaks it into tool steps:

- "Show me the schema" → calls `tigergraph__get_graph_schema`
- "Add a Person vertex with id p1, name Alice" → calls `tigergraph__add_node`
- "How many vertices are there?" → calls `tigergraph__get_vertex_count`

### Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `CREWAI_VERBOSE` | `0` | Set to `1` for verbose crew output |
| `CREWAI_LLM` | `openai/gpt-4.1-mini-2025-04-14` | LLM model for CrewAI agents |

## Key Design Decisions

- **MCP tools via MCPServerAdapter**: All TigerGraph operations go through the MCP server. No direct pyTigerGraph imports.
- **Domain-based routing**: The ToolExecutorCrews class groups tools by domain (schema, node, edge, query, etc.) and assigns specialized agents.
- **Two-layer interaction**: Schemas and loading configs are presented in markdown for easy review. JSON is generated internally only when the user confirms.
- **Human-in-the-loop**: `chat_session.wait_for_user_input()` blocks the flow until the user responds, enabling confirmation loops.
