"""CLI entry point for the TigerGraph LangGraph chatbot."""

import asyncio
import argparse
import uuid
import sys

from langchain_core.messages import AIMessage


async def run():
    parser = argparse.ArgumentParser(
        description="TigerGraph LangGraph Chatbot",
    )
    parser.add_argument(
        "--model",
        default="openai:gpt-4.1-mini-2025-04-14",
        help="Chat model identifier (default: openai:gpt-4.1-mini-2025-04-14)",
    )
    parser.add_argument(
        "--dotenv",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Temperature for the LLM (default: 0.1)",
    )
    args = parser.parse_args()

    from .workflow import build_graph
    graph = await build_graph(
        model=args.model,
        temperature=args.temperature,
        dotenv_path=args.dotenv,
    )

    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    print("\n" + "=" * 60)
    print("  TigerGraph LangGraph Chatbot")
    print("=" * 60)
    print()

    def display_stream_event(event: dict):
        if isinstance(event, dict):
            if "message" in event and isinstance(event["message"], AIMessage):
                print(f"\n{event['message'].content}\n")
            elif "status" in event:
                print(f"  [{event['status']}]", flush=True)

    # Initial invocation to trigger welcome
    async for event in graph.astream(
        {"messages": []}, config, stream_mode="custom"
    ):
        display_stream_event(event)

    while True:
        try:
            lines = []
            prompt = "You: " if not lines else "...  "
            while True:
                line = input(prompt)
                if line.strip() == "":
                    if lines:
                        break
                    continue
                lines.append(line)
                prompt = "...  "

            user_input = "\n".join(lines).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("exit", "quit", "bye"):
            print("\nGoodbye!")
            break

        from langgraph.types import Command
        command = Command(resume=user_input)

        async for event in graph.astream(
            command, config, stream_mode="custom"
        ):
            display_stream_event(event)


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
