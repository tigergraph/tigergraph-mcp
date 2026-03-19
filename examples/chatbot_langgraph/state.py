"""State model for the TigerGraph chatbot."""

from typing import Annotated, List, Optional
from pydantic import BaseModel
from enum import Enum

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class FlowStatus(str, Enum):
    TOOL_EXECUTION_READY = "tool_execution_ready"
    HELP_REQUESTED = "help_requested"
    ONBOARDING_REQUIRED = "onboarding_required"

    PREVIEW_SUCCESSFUL = "preview_successful"
    PREVIEW_FAILED = "preview_failed"

    USER_CONFIRMED = "user_confirmed"
    USER_REQUESTED_CHANGES = "user_requested_changes"

    SCHEMA_CREATED_SUCCESSFUL = "schema_created_successful"
    SCHEMA_CREATED_FAILED = "schema_created_failed"

    DATA_LOADED_SUCCESSFUL = "data_loaded_successful"
    DATA_LOADED_FAILED = "data_loaded_failed"


CONFIRMED_KEYWORDS = [
    "confirmed", "confirm", "approve", "approved", "go ahead", "ok", "okay",
    "yes", "yep", "yeah", "sure", "sounds good", "looks good", "do it", "fine",
    "alright", "let's do it", "proceed", "that's fine", "that's good",
    "works for me", "i agree", "all good", "go for it", "cool", "got it",
    "absolutely", "continue", "no problem",
]


class ChatSessionState(BaseModel):
    messages: Annotated[List[BaseMessage], add_messages] = []
    flow_status: Optional[FlowStatus] = None
    previewed_sample_data: str = ""
    current_schema_draft: str = ""
    current_loading_job_draft: str = ""


class ToolCallResult(BaseModel):
    success: bool
    message: str


def is_confirmed(text: str) -> bool:
    normalized = text.strip().lower()
    return any(kw in normalized for kw in CONFIRMED_KEYWORDS)
