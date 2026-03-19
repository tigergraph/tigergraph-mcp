"""Panel web app entry point for the TigerGraph CrewAI chatbot."""

import threading
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
import panel as pn
from mcp import StdioServerParameters
from crewai_tools import MCPServerAdapter

from chat_flow import ChatFlow
from chat_session_manager import chat_session

DOTENV_PATH = Path(".env")

WELCOME_MESSAGE = (
    "**Welcome!** I'm your **TigerGraph Assistant** — here to help you design schemas, "
    "load and explore data, run queries, and more.\n\n"
    "Type what you'd like to do, or say **'onboarding'** to get started, "
    "or **'help'** to see what I can do."
)


class TigerGraphChatApp:
    def __init__(self):
        load_dotenv(dotenv_path=DOTENV_PATH)
        pn.extension(design="material")
        chat_session.chat_ui.callback = self.callback
        chat_session.send_message(WELCOME_MESSAGE)

    def callback(self, contents: str, user: str, instance: pn.chat.ChatInterface):
        if not chat_session.is_flow_active():
            thread = threading.Thread(
                target=self.start_chat_flow, args=(contents,), daemon=True
            )
            thread.start()
        else:
            chat_session.submit_user_input(contents)

    def start_chat_flow(self, message: str):
        chat_session.set_flow_active(True)
        try:
            env_dict = dotenv_values(
                dotenv_path=DOTENV_PATH.expanduser().resolve()
            )
            with MCPServerAdapter(
                StdioServerParameters(command="tigergraph-mcp", env=env_dict),
            ) as tools:
                tool_registry = {tool.name: tool for tool in tools}
                flow = ChatFlow(
                    tool_registry=tool_registry,
                    conversation_history=[f"User: {message}"],
                )
                flow.kickoff()
        except Exception as e:
            chat_session.send_message(f"An error occurred: {e}")
        chat_session.set_flow_active(False)

    def run(self):
        chat_session.chat_ui.servable()


TigerGraphChatApp().run()
