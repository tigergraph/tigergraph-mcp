# TigerGraph LangGraph Chatbot

An interactive CLI chatbot that connects to TigerGraph via the MCP server. Supports
guided onboarding, schema creation, data loading, algorithm execution, and general
graph operations — all through natural language.

## Architecture

```
User CLI  →  Main Workflow  →  Intent Detection
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              Onboarding      React Agent       Help Message
              Subgraph       (general tools)
                │
    ┌───────────┼───────────┬───────────────┐
    ▼           ▼           ▼               ▼
  Data Source  Schema    Loading Job    Algorithms
  Setup       Draft →    Draft →        Suggest →
              Review →   Review →       Review →
              Create     Run            Run
```

## Requirements

- Python 3.10+
- A running TigerGraph instance
- An OpenAI API key (or compatible LLM provider)

## Setup

1. Install dependencies:

```bash
pip install pyTigerGraph-mcp langchain-openai langgraph langchain-mcp-adapters python-dotenv
```

2. Create a `.env` file with your TigerGraph and LLM credentials:

```bash
TG_HOST=http://127.0.0.1
TG_USERNAME=tigergraph
TG_PASSWORD=tigergraph
OPENAI_API_KEY=sk-...
```

3. Run the chatbot:

```bash
python -m examples.chatbot_langgraph.main
```

Or with options:

```bash
python -m examples.chatbot_langgraph.main \
  --model openai:gpt-4.1-mini-2025-04-14 \
  --dotenv .env \
  --temperature 0.1
```

## File Structure

```
examples/chatbot_langgraph/
  __init__.py    -- Package init, exports build_graph
  main.py        -- CLI entry point (async loop, multi-line input)
  workflow.py    -- LangGraph StateGraph: main workflow + onboarding subgraph
  prompts.py     -- All system prompts (schema drafting, loading config, etc.)
  state.py       -- Pydantic state model (ChatSessionState, FlowStatus)
```

## Usage

### Onboarding

Type `onboarding` to start a guided walkthrough:

1. **Data source setup** -- Automatically creates an S3 anonymous data source
2. **Data preview** -- Provide S3 file paths to preview sample data
3. **Schema design** -- LLM analyzes data and proposes a graph schema in readable markdown
4. **Schema review** -- Confirm or request changes interactively
5. **Loading config** -- LLM drafts a loading job mapping files to the schema
6. **Data loading** -- Creates and runs the loading job
7. **Algorithms** -- Suggests and runs relevant graph algorithms

### General Commands

After onboarding (or instead of it), you can issue any command:

- "How many vertices are in the graph?"
- "Drop the graph Customer360Graph"
- "Show me the schema"
- "Create a query to find all people over 30"

Type `help` to see available tools and examples.

### Multi-line Input

Press **Enter** on an empty line to submit multi-line input. Type `exit` to quit.
