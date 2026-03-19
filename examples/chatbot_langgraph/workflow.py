"""LangGraph workflow for the TigerGraph chatbot."""

import logging
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.prebuilt import create_react_agent
from langgraph.config import get_stream_writer
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import Tool

from .state import ChatSessionState, FlowStatus, ToolCallResult, is_confirmed
from .prompts import (
    ONBOARDING_DETECTOR_PROMPT,
    PREVIEW_SAMPLE_DATA_PROMPT,
    DRAFT_SCHEMA_PROMPT,
    EDIT_SCHEMA_PROMPT,
    CREATE_SCHEMA_PROMPT,
    DRAFT_LOADING_CONFIG_PROMPT,
    EDIT_LOADING_CONFIG_PROMPT,
    RUN_LOADING_JOB_PROMPT,
    SUGGEST_ALGORITHMS_PROMPT,
    RUN_ALGORITHMS_PROMPT,
    PLAN_TOOL_EXECUTION_PROMPT,
    GET_SCHEMA_PROMPT,
)

logging.getLogger("httpx").setLevel(logging.WARNING)

S3_ANONYMOUS_SOURCE_NAME = "s3_anonymous_source"

WELCOME_MESSAGE = (
    "**Welcome!** I'm your **TigerGraph Assistant** — here to help you design schemas, "
    "load and explore data, run queries, and more.\n\n"
    "Type what you'd like to do, or say **'onboarding'** to get started, "
    "or **'help'** to see what I can do."
)


async def build_graph(
    model: str = "openai:gpt-4.1-mini-2025-04-14",
    temperature: float = 0.1,
    dotenv_path: str = ".env",
):
    env_dict = dotenv_values(dotenv_path=Path(dotenv_path).expanduser().resolve())
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
    tools = await client.get_tools()

    load_dotenv(dotenv_path=dotenv_path)
    llm = init_chat_model(model=model, temperature=temperature)

    # -- Onboarding subgraph ---------------------------------------------------

    preview_agent = create_react_agent(model=model, tools=tools)
    create_schema_agent = create_react_agent(
        model=model, tools=tools, response_format=ToolCallResult
    )
    load_data_agent = create_react_agent(
        model=model, tools=tools, response_format=ToolCallResult
    )
    algorithms_agent = create_react_agent(model=model, tools=tools)

    async def setup_data_source(state: ChatSessionState) -> ChatSessionState:
        writer = get_stream_writer()
        writer({"status": "Setting up S3 data source..."})

        response = await preview_agent.ainvoke(
            {
                "messages": [
                    SystemMessage(
                        content="Check if a data source named "
                        f"'{S3_ANONYMOUS_SOURCE_NAME}' exists using "
                        "`tigergraph__get_data_source`. If it does not exist "
                        "(error), create it using `tigergraph__create_data_source` "
                        f"with name='{S3_ANONYMOUS_SOURCE_NAME}', type='s3', "
                        "config={{'file.reader.settings.fs.s3a.aws.credentials."
                        "provider': 'org.apache.hadoop.fs.s3a."
                        "AnonymousAWSCredentialsProvider'}}."
                    ),
                ]
            }
        )

        message = AIMessage(
            content="Please provide the S3 path(s) to your data file(s) to get "
            "started.\nOnly S3 paths with anonymous access are supported.\n\n"
            "Example: `s3a://bucket-name/path/to/your/file.csv`"
        )
        state.messages.append(message)
        writer({"message": message})
        return state

    async def wait_and_preview(state: ChatSessionState) -> ChatSessionState:
        human_review = interrupt("Provide S3 file paths")
        message = HumanMessage(
            content=f"Preview the data in the data source "
            f"'{S3_ANONYMOUS_SOURCE_NAME}'. {human_review}"
        )
        state.messages.append(message)

        writer = get_stream_writer()
        writer({"status": "Previewing sample data..."})

        response = await preview_agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=PREVIEW_SAMPLE_DATA_PROMPT),
                    message,
                ]
            }
        )

        latest = _extract_last_ai_message(response)
        if not latest:
            state.flow_status = FlowStatus.PREVIEW_FAILED
        else:
            state.flow_status = FlowStatus.PREVIEW_SUCCESSFUL
            state.messages.append(latest)
            writer({"message": latest})
            state.previewed_sample_data = str(latest.content)
        return state

    async def evaluate_preview(state: ChatSessionState) -> FlowStatus:
        if state.flow_status == FlowStatus.PREVIEW_FAILED:
            return FlowStatus.PREVIEW_FAILED
        return FlowStatus.PREVIEW_SUCCESSFUL

    async def prompt_retry(state: ChatSessionState) -> ChatSessionState:
        message = AIMessage(
            content="There was a problem previewing your data. Please ensure your "
            "S3 path is correct and publicly accessible, then try again."
        )
        state.messages.append(message)
        writer = get_stream_writer()
        writer({"message": message})
        return state

    async def draft_schema(state: ChatSessionState) -> ChatSessionState:
        writer = get_stream_writer()
        writer({"status": "Drafting schema..."})

        human_msg = HumanMessage(
            content=f"Design a graph schema for this data:\n"
            f"{state.previewed_sample_data}"
        )
        message = await llm.ainvoke(
            [SystemMessage(content=DRAFT_SCHEMA_PROMPT), *state.messages, human_msg]
        )
        state.messages.append(message)
        state.current_schema_draft = message.content
        writer({"message": message})
        return state

    async def wait_for_schema_review(state: ChatSessionState) -> ChatSessionState:
        human_review = interrupt("Review the schema")
        state.messages.append(HumanMessage(content=human_review))
        if is_confirmed(human_review):
            state.flow_status = FlowStatus.USER_CONFIRMED
        else:
            state.flow_status = FlowStatus.USER_REQUESTED_CHANGES
        return state

    async def route_schema_review(state: ChatSessionState) -> FlowStatus:
        if state.flow_status == FlowStatus.USER_REQUESTED_CHANGES:
            return FlowStatus.USER_REQUESTED_CHANGES
        return FlowStatus.USER_CONFIRMED

    async def edit_schema(state: ChatSessionState) -> ChatSessionState:
        writer = get_stream_writer()
        writer({"status": "Editing schema..."})

        message = await llm.ainvoke(
            [SystemMessage(content=EDIT_SCHEMA_PROMPT), *state.messages]
        )
        state.messages.append(message)
        state.current_schema_draft = message.content
        writer({"message": message})
        return state

    async def create_schema(state: ChatSessionState) -> ChatSessionState:
        writer = get_stream_writer()
        writer({"status": "Creating schema..."})
        state.flow_status = FlowStatus.SCHEMA_CREATED_FAILED

        try:
            response = await create_schema_agent.ainvoke(
                {"messages": [SystemMessage(content=CREATE_SCHEMA_PROMPT), *state.messages]}
            )
            if isinstance(response, dict) and "structured_response" in response:
                sr = response["structured_response"]
                message = AIMessage(content=sr.message)
                state.messages.append(message)
                writer({"message": message})
                if sr.success:
                    state.flow_status = FlowStatus.SCHEMA_CREATED_SUCCESSFUL
        except Exception as e:
            message = AIMessage(content=f"Error creating schema: {e}")
            state.messages.append(message)
            writer({"message": message})

        state.current_schema_draft = ""
        return state

    async def route_schema_creation(state: ChatSessionState) -> FlowStatus:
        if state.flow_status == FlowStatus.SCHEMA_CREATED_SUCCESSFUL:
            return FlowStatus.SCHEMA_CREATED_SUCCESSFUL
        return FlowStatus.SCHEMA_CREATED_FAILED

    async def draft_loading_config(state: ChatSessionState) -> ChatSessionState:
        writer = get_stream_writer()
        writer({"status": "Drafting loading config..."})

        response = await load_data_agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=GET_SCHEMA_PROMPT),
                    HumanMessage(content="Get the graph schema of the created graph."),
                ]
            }
        )
        schema_msg = _extract_last_ai_message(response)
        if schema_msg:
            state.messages.append(schema_msg)

        human_msg = HumanMessage(
            content="Draft a loading job config for the data files."
        )
        message = await llm.ainvoke(
            [
                SystemMessage(content=DRAFT_LOADING_CONFIG_PROMPT),
                *state.messages,
                human_msg,
            ]
        )
        state.messages.append(message)
        state.current_loading_job_draft = message.content
        writer({"message": message})
        return state

    async def wait_for_loading_review(state: ChatSessionState) -> ChatSessionState:
        human_review = interrupt("Review the loading config")
        state.messages.append(HumanMessage(content=human_review))
        if is_confirmed(human_review):
            state.flow_status = FlowStatus.USER_CONFIRMED
        else:
            state.flow_status = FlowStatus.USER_REQUESTED_CHANGES
        return state

    async def route_loading_review(state: ChatSessionState) -> FlowStatus:
        if state.flow_status == FlowStatus.USER_REQUESTED_CHANGES:
            return FlowStatus.USER_REQUESTED_CHANGES
        return FlowStatus.USER_CONFIRMED

    async def edit_loading_config(state: ChatSessionState) -> ChatSessionState:
        writer = get_stream_writer()
        writer({"status": "Editing loading config..."})

        message = await llm.ainvoke(
            [SystemMessage(content=EDIT_LOADING_CONFIG_PROMPT), *state.messages]
        )
        state.messages.append(message)
        state.current_loading_job_draft = message.content
        writer({"message": message})
        return state

    async def run_loading_job(state: ChatSessionState) -> ChatSessionState:
        writer = get_stream_writer()
        writer({"status": "Loading data..."})
        state.flow_status = FlowStatus.DATA_LOADED_FAILED

        try:
            response = await load_data_agent.ainvoke(
                {"messages": [SystemMessage(content=RUN_LOADING_JOB_PROMPT), *state.messages]}
            )
            if isinstance(response, dict) and "structured_response" in response:
                sr = response["structured_response"]
                message = AIMessage(content=sr.message)
                state.messages.append(message)
                writer({"message": message})
                if sr.success:
                    state.flow_status = FlowStatus.DATA_LOADED_SUCCESSFUL
        except Exception as e:
            message = AIMessage(content=f"Error loading data: {e}")
            state.messages.append(message)
            writer({"message": message})

        state.current_loading_job_draft = ""
        return state

    async def route_data_loading(state: ChatSessionState) -> FlowStatus:
        if state.flow_status == FlowStatus.DATA_LOADED_SUCCESSFUL:
            return FlowStatus.DATA_LOADED_SUCCESSFUL
        return FlowStatus.DATA_LOADED_FAILED

    async def suggest_algorithms(state: ChatSessionState) -> ChatSessionState:
        writer = get_stream_writer()
        writer({"status": "Suggesting graph algorithms..."})

        message = await llm.ainvoke(
            [SystemMessage(content=SUGGEST_ALGORITHMS_PROMPT), *state.messages]
        )
        state.messages.append(message)
        writer({"message": message})
        return state

    async def wait_for_algo_review(state: ChatSessionState) -> ChatSessionState:
        human_review = interrupt("Review algorithm suggestions")
        state.messages.append(HumanMessage(content=human_review))
        if is_confirmed(human_review):
            state.flow_status = FlowStatus.USER_CONFIRMED
        else:
            state.flow_status = FlowStatus.USER_REQUESTED_CHANGES
        return state

    async def route_algo_review(state: ChatSessionState) -> FlowStatus:
        if state.flow_status == FlowStatus.USER_REQUESTED_CHANGES:
            return FlowStatus.USER_REQUESTED_CHANGES
        return FlowStatus.USER_CONFIRMED

    async def edit_algo_selection(state: ChatSessionState) -> ChatSessionState:
        message = await llm.ainvoke(
            [
                SystemMessage(
                    content="Adjust the algorithm selection based on user feedback."
                ),
                *state.messages,
            ]
        )
        state.messages.append(message)
        writer = get_stream_writer()
        writer({"message": message})
        return state

    async def run_algorithms(state: ChatSessionState) -> ChatSessionState:
        writer = get_stream_writer()
        writer({"status": "Running algorithms..."})

        try:
            response = await algorithms_agent.ainvoke(
                {"messages": [SystemMessage(content=RUN_ALGORITHMS_PROMPT), *state.messages]}
            )
            latest = _extract_last_ai_message(response)
            if latest:
                state.messages.append(latest)
                writer({"message": latest})
        except Exception as e:
            message = AIMessage(content=f"Error running algorithms: {e}")
            state.messages.append(message)
            writer({"message": message})

        return state

    # Build onboarding subgraph
    onboarding_builder = StateGraph(ChatSessionState)
    onboarding_builder.add_node(setup_data_source)
    onboarding_builder.add_node(wait_and_preview)
    onboarding_builder.add_node(prompt_retry)
    onboarding_builder.add_node(draft_schema)
    onboarding_builder.add_node(wait_for_schema_review)
    onboarding_builder.add_node(edit_schema)
    onboarding_builder.add_node(create_schema)
    onboarding_builder.add_node(draft_loading_config)
    onboarding_builder.add_node(wait_for_loading_review)
    onboarding_builder.add_node(edit_loading_config)
    onboarding_builder.add_node(run_loading_job)
    onboarding_builder.add_node(suggest_algorithms)
    onboarding_builder.add_node(wait_for_algo_review)
    onboarding_builder.add_node(edit_algo_selection)
    onboarding_builder.add_node(run_algorithms)

    onboarding_builder.add_edge(START, "setup_data_source")
    onboarding_builder.add_edge("setup_data_source", "wait_and_preview")
    onboarding_builder.add_conditional_edges(
        "wait_and_preview",
        evaluate_preview,
        {
            FlowStatus.PREVIEW_FAILED: "prompt_retry",
            FlowStatus.PREVIEW_SUCCESSFUL: "draft_schema",
        },
    )
    onboarding_builder.add_edge("prompt_retry", "wait_and_preview")
    onboarding_builder.add_edge("draft_schema", "wait_for_schema_review")
    onboarding_builder.add_conditional_edges(
        "wait_for_schema_review",
        route_schema_review,
        {
            FlowStatus.USER_REQUESTED_CHANGES: "edit_schema",
            FlowStatus.USER_CONFIRMED: "create_schema",
        },
    )
    onboarding_builder.add_edge("edit_schema", "wait_for_schema_review")
    onboarding_builder.add_conditional_edges(
        "create_schema",
        route_schema_creation,
        {
            FlowStatus.SCHEMA_CREATED_FAILED: END,
            FlowStatus.SCHEMA_CREATED_SUCCESSFUL: "draft_loading_config",
        },
    )
    onboarding_builder.add_edge("draft_loading_config", "wait_for_loading_review")
    onboarding_builder.add_conditional_edges(
        "wait_for_loading_review",
        route_loading_review,
        {
            FlowStatus.USER_REQUESTED_CHANGES: "edit_loading_config",
            FlowStatus.USER_CONFIRMED: "run_loading_job",
        },
    )
    onboarding_builder.add_edge("edit_loading_config", "wait_for_loading_review")
    onboarding_builder.add_conditional_edges(
        "run_loading_job",
        route_data_loading,
        {
            FlowStatus.DATA_LOADED_FAILED: END,
            FlowStatus.DATA_LOADED_SUCCESSFUL: "suggest_algorithms",
        },
    )
    onboarding_builder.add_edge("suggest_algorithms", "wait_for_algo_review")
    onboarding_builder.add_conditional_edges(
        "wait_for_algo_review",
        route_algo_review,
        {
            FlowStatus.USER_REQUESTED_CHANGES: "edit_algo_selection",
            FlowStatus.USER_CONFIRMED: "run_algorithms",
        },
    )
    onboarding_builder.add_edge("edit_algo_selection", "wait_for_algo_review")
    onboarding_builder.add_edge("run_algorithms", END)

    onboarding_subgraph = onboarding_builder.compile(checkpointer=True)

    # -- Task execution subgraph -----------------------------------------------

    schema_trigger = Tool.from_function(
        func=lambda _: "",
        name="trigger_graph_schema_creation",
        description=(
            "Triggers the schema creation workflow to analyze data, suggest a graph "
            "schema, incorporate user feedback, and create the schema in TigerGraph. "
            "Call this tool alone, not grouped with other tools."
        ),
    )
    load_trigger = Tool.from_function(
        func=lambda _: "",
        name="trigger_load_data",
        description=(
            "Triggers the data loading workflow to map file contents to the graph "
            "schema and load data into TigerGraph. "
            "Call this tool alone, not grouped with other tools."
        ),
    )

    all_tools = list(tools) + [schema_trigger, load_trigger]
    llm_with_tools = llm.bind_tools(all_tools)

    # Build schema creation subgraph for task execution
    schema_sub_builder = StateGraph(ChatSessionState)
    schema_sub_builder.add_node(draft_schema)
    schema_sub_builder.add_node(wait_for_schema_review)
    schema_sub_builder.add_node(edit_schema)
    schema_sub_builder.add_node(create_schema)
    schema_sub_builder.add_edge(START, "draft_schema")
    schema_sub_builder.add_edge("draft_schema", "wait_for_schema_review")
    schema_sub_builder.add_conditional_edges(
        "wait_for_schema_review",
        route_schema_review,
        {
            FlowStatus.USER_REQUESTED_CHANGES: "edit_schema",
            FlowStatus.USER_CONFIRMED: "create_schema",
        },
    )
    schema_sub_builder.add_edge("edit_schema", "wait_for_schema_review")
    schema_sub_builder.add_edge("create_schema", END)
    schema_subgraph = schema_sub_builder.compile(checkpointer=True)

    # Build loading subgraph for task execution
    loading_sub_builder = StateGraph(ChatSessionState)
    loading_sub_builder.add_node(draft_loading_config)
    loading_sub_builder.add_node(wait_for_loading_review)
    loading_sub_builder.add_node(edit_loading_config)
    loading_sub_builder.add_node(run_loading_job)
    loading_sub_builder.add_edge(START, "draft_loading_config")
    loading_sub_builder.add_edge("draft_loading_config", "wait_for_loading_review")
    loading_sub_builder.add_conditional_edges(
        "wait_for_loading_review",
        route_loading_review,
        {
            FlowStatus.USER_REQUESTED_CHANGES: "edit_loading_config",
            FlowStatus.USER_CONFIRMED: "run_loading_job",
        },
    )
    loading_sub_builder.add_edge("edit_loading_config", "wait_for_loading_review")
    loading_sub_builder.add_edge("run_loading_job", END)
    loading_subgraph = loading_sub_builder.compile(checkpointer=True)

    # -- Main workflow ---------------------------------------------------------

    async def send_welcome(state: ChatSessionState) -> ChatSessionState:
        message = AIMessage(content=WELCOME_MESSAGE)
        state.messages.append(message)
        writer = get_stream_writer()
        writer({"message": message})
        return state

    async def wait_for_user(state: ChatSessionState) -> ChatSessionState:
        human_review = interrupt("Please provide input")
        state.messages.append(HumanMessage(content=human_review))
        return state

    async def detect_intent(state: ChatSessionState) -> ChatSessionState:
        last_msg = state.messages[-1].content
        if isinstance(last_msg, str) and last_msg.strip().lower() in (
            "onboarding", "onboard", "get started",
        ):
            state.flow_status = FlowStatus.ONBOARDING_REQUIRED
            return state

        if isinstance(last_msg, str) and last_msg.strip().lower() == "help":
            state.flow_status = FlowStatus.HELP_REQUESTED
            return state

        response = await llm.ainvoke(
            [
                SystemMessage(content=ONBOARDING_DETECTOR_PROMPT),
                HumanMessage(content=str(last_msg)),
            ]
        )
        if str(response.content).strip().lower() == "true":
            state.flow_status = FlowStatus.ONBOARDING_REQUIRED
        else:
            state.flow_status = FlowStatus.TOOL_EXECUTION_READY
        return state

    async def route_intent(state: ChatSessionState) -> FlowStatus:
        if state.flow_status == FlowStatus.ONBOARDING_REQUIRED:
            return FlowStatus.ONBOARDING_REQUIRED
        if state.flow_status == FlowStatus.HELP_REQUESTED:
            return FlowStatus.HELP_REQUESTED
        return FlowStatus.TOOL_EXECUTION_READY

    async def handle_help(state: ChatSessionState) -> ChatSessionState:
        message = AIMessage(content=_get_help_message(tools))
        state.messages.append(message)
        writer = get_stream_writer()
        writer({"message": message})
        return state

    # General-purpose task execution via react agent
    general_agent = create_react_agent(model=model, tools=tools)

    async def execute_general_task(state: ChatSessionState) -> ChatSessionState:
        try:
            response = await general_agent.ainvoke(
                {"messages": [SystemMessage(content=PLAN_TOOL_EXECUTION_PROMPT), *state.messages]}
            )
            latest = _extract_last_ai_message(response)
            if latest:
                state.messages.append(latest)
                writer = get_stream_writer()
                writer({"message": latest})
        except Exception as e:
            message = AIMessage(content=f"Error: {e}")
            state.messages.append(message)
            writer = get_stream_writer()
            writer({"message": message})
        return state

    # Build main graph
    builder = StateGraph(ChatSessionState)
    builder.add_node(send_welcome)
    builder.add_node(wait_for_user)
    builder.add_node(detect_intent)
    builder.add_node(handle_help)
    builder.add_node("onboarding", onboarding_subgraph)
    builder.add_node(execute_general_task)

    builder.add_edge(START, "send_welcome")
    builder.add_edge("send_welcome", "wait_for_user")
    builder.add_edge("wait_for_user", "detect_intent")
    builder.add_conditional_edges(
        "detect_intent",
        route_intent,
        {
            FlowStatus.TOOL_EXECUTION_READY: "execute_general_task",
            FlowStatus.ONBOARDING_REQUIRED: "onboarding",
            FlowStatus.HELP_REQUESTED: "handle_help",
        },
    )
    builder.add_edge("execute_general_task", "wait_for_user")
    builder.add_edge("onboarding", "wait_for_user")
    builder.add_edge("handle_help", "wait_for_user")

    return builder.compile(checkpointer=MemorySaver())


def _extract_last_ai_message(response):
    if isinstance(response, dict) and "messages" in response:
        messages = response["messages"]
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, AIMessage):
                return last
    return None


def _get_help_message(tools) -> str:
    tool_list = ", ".join(f"**{tool.name}**" for tool in tools[:15])
    return f"""\
Here are some things I can help you with:

**Available tools (showing first 15):** {tool_list}, and more...

**Example instructions:**
- **Create a schema**: "Generate a graph schema from these two CSV files."
- **Add data**: "Add a person named John who is 30 years old."
- **Connect nodes**: "Create an edge to show that John works at TigerGraph."
- **Query the graph**: "How many vertices are in the graph?"
- **Load data**: "Load data from S3 into my graph."

**New here?** Say **"onboarding"** to start an interactive walkthrough.

Just tell me what you'd like to do!"""
