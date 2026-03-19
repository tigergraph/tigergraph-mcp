"""CrewAI Flow for the TigerGraph chatbot.

Routes user requests through specialized crews for planning, schema creation,
data loading, and general tool execution.
"""

import json
import os
from typing import Any, Dict, List, Optional

from crewai.flow.flow import Flow, router, or_, start
from crewai.tools import BaseTool
from panel.chat import ChatMessage
from pydantic import BaseModel

from chat_session_manager import chat_session
from crews import (
    PlannerCrew,
    SchemaCreationCrews,
    DataLoadingCrews,
    ToolExecutorCrews,
)

S3_ANONYMOUS_SOURCE_NAME = "s3_anonymous_source"

verbose = int(os.getenv("CREWAI_VERBOSE", "0"))
llm = os.getenv("CREWAI_LLM", "openai/gpt-4.1-mini-2025-04-14")


class ChatSessionState(BaseModel):
    conversation_history: List[str] = []
    task_plan: List[Dict[str, Any]] = []
    current_task_index: int = 0
    current_tool_name: str = ""
    current_command: str = ""
    last_data_preview: str = ""
    is_from_onboarding: bool = False
    current_schema_draft: str = ""
    current_loading_job_draft: str = ""
    tool_registry: Dict[str, Any] = {}


# -- Confirmed-keyword detection -----------------------------------------------

CONFIRMED_KEYWORDS = [
    "confirmed", "confirm", "approve", "approved", "go ahead", "ok", "okay",
    "yes", "yep", "yeah", "sure", "sounds good", "looks good", "do it", "fine",
    "alright", "let's do it", "proceed", "that's fine", "that's good",
    "works for me", "i agree", "all good", "go for it", "cool", "got it",
    "absolutely", "continue", "no problem",
]


def _is_confirmed(text: str) -> bool:
    normalized = text.strip().lower()
    return any(kw in normalized for kw in CONFIRMED_KEYWORDS)


# -- Helpers -------------------------------------------------------------------

def _send_message(text: str, *, record_history: bool = True) -> Optional[ChatMessage]:
    msg = chat_session.chat_ui.send(text, user="Assistant", respond=False)
    return msg


def _update_message(msg: Optional[ChatMessage], text: str, *, record_history: bool = True):
    if msg:
        msg.object = text


def _add_to_history(state: ChatSessionState, role: str, text: str):
    state.conversation_history.append(f"{role}: {text}")


# ==============================================================================
# Flow
# ==============================================================================

class ChatFlow(Flow[ChatSessionState]):
    def __init__(self, tool_registry: Dict[str, Any], conversation_history: List[str]):
        super().__init__()
        self.state.tool_registry = tool_registry
        self.state.conversation_history = conversation_history

    # -- Entry -----------------------------------------------------------------

    @start()
    def initialize_session(self):
        return self.analyze_and_evaluate_plan()

    def analyze_and_evaluate_plan(self):
        last_command = self.state.conversation_history[-1].replace("User: ", "", 1)
        planner = PlannerCrew(verbose=verbose, llm=llm)

        onboarding_result = (
            planner
            .onboarding_detector_crew()
            .kickoff(inputs={"last_command": last_command})
        )
        onboarding_text = str(onboarding_result).strip().lower()

        if onboarding_text == "onboarding":
            self.state.is_from_onboarding = True
            return "onboarding"

        plan_result = (
            planner
            .planning_crew()
            .kickoff(
                inputs={
                    "conversation_history": self.state.conversation_history,
                    "last_command": last_command,
                    "tools": json.dumps(
                        [
                            {"tool_name": name, "description": getattr(t, "description", "")}
                            for name, t in self.state.tool_registry.items()
                        ]
                    ),
                }
            )
        )

        plan_text = str(plan_result).strip()
        if plan_text.lower() == "none" or not plan_text:
            return "unknown"

        try:
            self.state.task_plan = json.loads(plan_text)
            self.state.current_task_index = 0
            return "has_plan"
        except json.JSONDecodeError:
            return "unknown"

    # -- Routing ---------------------------------------------------------------

    @router("onboarding")
    def start_onboarding(self):
        return self._run_onboarding()

    @router("has_plan")
    def evaluate_task_type(self):
        if self.state.current_task_index >= len(self.state.task_plan):
            return "done"

        step = self.state.task_plan[self.state.current_task_index]
        self.state.current_tool_name = step.get("tool_name", "")
        self.state.current_command = step.get("command", "")

        if self.state.current_tool_name == "tigergraph__create_graph":
            return "task_type_create_schema"
        if self.state.current_tool_name == "tigergraph__create_loading_job":
            return "task_type_load_data"
        return "task_type_general_tool"

    @router("unknown")
    def handle_unknown(self):
        _send_message(
            "I'm not sure how to handle that request. Could you rephrase?\n\n"
            "Say **'help'** to see what I can do, or **'onboarding'** for a guided walkthrough."
        )
        user_input = chat_session.wait_for_user_input()
        _add_to_history(self.state, "User", user_input)
        return self.analyze_and_evaluate_plan()

    @router("done")
    def handle_done(self):
        _send_message("All tasks completed. What would you like to do next?")
        user_input = chat_session.wait_for_user_input()
        _add_to_history(self.state, "User", user_input)
        return self.analyze_and_evaluate_plan()

    # -- Schema creation -------------------------------------------------------

    @router("task_type_create_schema")
    def run_schema_creation(self):
        crews = SchemaCreationCrews(
            tools=self.state.tool_registry, verbose=verbose, llm=llm
        )

        draft_result = (
            crews
            .draft_schema_crew()
            .kickoff(
                inputs={
                    "conversation_history": self.state.conversation_history,
                    "command": self.state.current_command,
                    "data_preview": self.state.last_data_preview,
                }
            )
        )
        draft_text = str(draft_result)
        self.state.current_schema_draft = draft_text
        _send_message(draft_text)

        while True:
            _send_message("Please **confirm** this schema, or tell me what to change.")
            user_input = chat_session.wait_for_user_input()
            _add_to_history(self.state, "User", user_input)

            if _is_confirmed(user_input):
                break

            edit_result = (
                crews
                .edit_schema_crew()
                .kickoff(
                    inputs={
                        "current_schema_draft": self.state.current_schema_draft,
                        "user_feedback": user_input,
                    }
                )
            )
            edit_text = str(edit_result)
            self.state.current_schema_draft = edit_text
            _send_message(edit_text)

        status_msg = _send_message("Creating schema...")
        create_result = (
            crews
            .create_schema_crew()
            .kickoff(
                inputs={
                    "current_schema_draft": self.state.current_schema_draft,
                    "conversation_history": self.state.conversation_history,
                }
            )
        )
        _update_message(status_msg, str(create_result))
        _add_to_history(self.state, "Assistant", str(create_result))
        self.state.current_schema_draft = ""

        self.state.current_task_index += 1
        if self.state.is_from_onboarding:
            return self._continue_onboarding_after_schema()
        return self.evaluate_task_type()

    # -- Data loading ----------------------------------------------------------

    @router("task_type_load_data")
    def run_data_loading(self):
        crews = DataLoadingCrews(
            tools=self.state.tool_registry, verbose=verbose, llm=llm
        )

        draft_result = (
            crews
            .draft_loading_job_crew()
            .kickoff(
                inputs={
                    "conversation_history": self.state.conversation_history,
                    "command": self.state.current_command,
                    "data_preview": self.state.last_data_preview,
                }
            )
        )
        draft_text = str(draft_result)
        self.state.current_loading_job_draft = draft_text
        _send_message(draft_text)

        while True:
            _send_message("Please **confirm** this loading config, or tell me what to change.")
            user_input = chat_session.wait_for_user_input()
            _add_to_history(self.state, "User", user_input)

            if _is_confirmed(user_input):
                break

            edit_result = (
                crews
                .edit_loading_job_crew()
                .kickoff(
                    inputs={
                        "current_loading_job_draft": self.state.current_loading_job_draft,
                        "user_feedback": user_input,
                    }
                )
            )
            edit_text = str(edit_result)
            self.state.current_loading_job_draft = edit_text
            _send_message(edit_text)

        status_msg = _send_message("Running loading job...")
        run_result = (
            crews
            .run_loading_job_crew()
            .kickoff(
                inputs={
                    "current_loading_job_draft": self.state.current_loading_job_draft,
                    "conversation_history": self.state.conversation_history,
                }
            )
        )
        _update_message(status_msg, str(run_result))
        _add_to_history(self.state, "Assistant", str(run_result))
        self.state.current_loading_job_draft = ""

        self.state.current_task_index += 1
        return self.evaluate_task_type()

    # -- General tool execution ------------------------------------------------

    @router("task_type_general_tool")
    def execute_general_tool(self):
        executor = ToolExecutorCrews(
            tools=self.state.tool_registry, verbose=verbose, llm=llm
        )

        crew = executor.get_crew_for_tool(self.state.current_tool_name)
        if crew is None:
            _send_message(
                f"No handler for tool `{self.state.current_tool_name}`. Skipping."
            )
        else:
            status_msg = _send_message(f"Running `{self.state.current_tool_name}`...")
            result = crew.kickoff(
                inputs={
                    "command": self.state.current_command,
                    "conversation_history": self.state.conversation_history,
                }
            )
            _update_message(status_msg, str(result))
            _add_to_history(self.state, "Assistant", str(result))

        self.state.current_task_index += 1
        return self.evaluate_task_type()

    # -- Onboarding flow -------------------------------------------------------

    def _run_onboarding(self):
        self._ensure_s3_data_source()
        self._onboarding_preview_data()
        self._onboarding_draft_schema()
        return "task_type_create_schema"

    def _ensure_s3_data_source(self):
        status_msg = _send_message("Checking data source...")
        executor = ToolExecutorCrews(
            tools=self.state.tool_registry, verbose=verbose, llm=llm
        )
        try:
            crew = executor.get_crew_for_tool("tigergraph__get_data_source")
            if crew:
                crew.kickoff(
                    inputs={
                        "command": f"Get data source '{S3_ANONYMOUS_SOURCE_NAME}'",
                        "conversation_history": [],
                    }
                )
                _update_message(status_msg, f"Data source `{S3_ANONYMOUS_SOURCE_NAME}` exists.")
                return
        except Exception:
            pass

        _update_message(status_msg, f"Creating data source `{S3_ANONYMOUS_SOURCE_NAME}`...")
        crew = executor.get_crew_for_tool("tigergraph__create_data_source")
        if crew:
            crew.kickoff(
                inputs={
                    "command": (
                        f"Create an S3 data source named '{S3_ANONYMOUS_SOURCE_NAME}' "
                        f"with type 's3' and config: "
                        f'{{"file.reader.settings.fs.s3a.aws.credentials.provider": '
                        f'"org.apache.hadoop.fs.s3a.AnonymousAWSCredentialsProvider"}}'
                    ),
                    "conversation_history": [],
                }
            )

    def _onboarding_preview_data(self):
        _send_message(
            "Please provide the S3 path(s) to your data file(s).\n\n"
            "Example: `s3a://bucket-name/path/to/file.csv`"
        )
        user_input = chat_session.wait_for_user_input()
        _add_to_history(self.state, "User", user_input)

        status_msg = _send_message("Previewing data...")
        executor = ToolExecutorCrews(
            tools=self.state.tool_registry, verbose=verbose, llm=llm
        )
        crew = executor.get_crew_for_tool("tigergraph__preview_sample_data")
        if crew:
            result = crew.kickoff(
                inputs={
                    "command": (
                        f"Preview data from data source '{S3_ANONYMOUS_SOURCE_NAME}': "
                        f"{user_input}"
                    ),
                    "conversation_history": self.state.conversation_history,
                }
            )
            preview_text = str(result)
            self.state.last_data_preview = preview_text
            _update_message(status_msg, preview_text)
            _add_to_history(self.state, "Assistant", preview_text)

    def _onboarding_draft_schema(self):
        self.state.current_tool_name = "tigergraph__create_graph"
        self.state.current_command = (
            "Create a graph schema based on the previewed data."
        )
        self.state.task_plan = [
            {"tool_name": "tigergraph__create_graph", "command": self.state.current_command},
            {"tool_name": "tigergraph__create_loading_job", "command": "Load the previewed data files."},
        ]
        self.state.current_task_index = 0

    def _continue_onboarding_after_schema(self):
        self.state.current_tool_name = "tigergraph__create_loading_job"
        self.state.current_command = "Load the previewed data files."
        return "task_type_load_data"
