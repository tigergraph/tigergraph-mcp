"""Thread-safe chat session state shared between the Panel UI and CrewAI flow."""

import threading
import panel as pn


class ChatSessionManager:
    def __init__(self):
        self.latest_input = ""
        self.flow_active = False
        self.input_ready_event = threading.Event()
        pn.extension(design="material")
        self.chat_ui = pn.chat.ChatInterface()

    def wait_for_user_input(self) -> str:
        """Block until the user submits a message through the UI."""
        self.input_ready_event.wait()
        self.input_ready_event.clear()
        return self.latest_input

    def submit_user_input(self, value: str):
        """Called by the Panel callback when the user sends a message."""
        self.latest_input = value
        self.input_ready_event.set()

    def is_flow_active(self) -> bool:
        return self.flow_active

    def set_flow_active(self, active: bool):
        self.flow_active = active

    def send_message(self, text: str, *, user: str = "Assistant"):
        self.chat_ui.send(text, user=user, respond=False)


chat_session = ChatSessionManager()
