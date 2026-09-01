# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Main entry point for TigerGraph MCP server."""

import logging
import sys
import click
import asyncio
from pathlib import Path

from .server import serve


@click.command()
@click.option("-v", "--verbose", count=True)
@click.option("--env-file", type=click.Path(exists=True, path_type=Path), default=None,
              help="Path to .env file (default: searches for .env in current and parent directories)")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "streamable-http", "sse"], case_sensitive=False),
    default="stdio",
    show_default=True,
    help=(
        "Transport mode. Use 'stdio' for single-user IDE integrations "
        "(default). Use 'streamable-http' for multi-user deployments. "
        "'sse' is the legacy HTTP transport."
    ),
)
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Bind address for HTTP transports.")
@click.option("--port", type=int, default=8000, show_default=True,
              help="TCP port for HTTP transports.")
@click.option("--mount-path", default="/mcp", show_default=True,
              help="URL path mount point for HTTP transports.")
@click.option(
    "--allowed-tools",
    default=None,
    help=(
        "Serve only these tools. Comma-separated categories (schema, data, "
        "query, vector, loading, utility, discovery), 'read-only', "
        "'destructive', or tool names. Defaults to TG_ALLOWED_TOOLS, else all."
    ),
)
@click.option(
    "--blocked-tools",
    default=None,
    help=(
        "Remove these tools from whatever is served. Same syntax as "
        "--allowed-tools. Defaults to TG_BLOCKED_TOOLS."
    ),
)
def main(
    verbose: bool,
    env_file: Path = None,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    mount_path: str = "/mcp",
    allowed_tools: str = None,
    blocked_tools: str = None,
) -> None:
    """TigerGraph MCP Server - TigerGraph functionality for MCP

    The server will automatically load environment variables from a .env file
    if python-dotenv is installed and a .env file is found.
    """

    logging_level = logging.WARN
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(level=logging_level, stream=sys.stderr)

    # Ensure mcp.server.lowlevel.server respects the WARNING level
    logging.getLogger('mcp.server.lowlevel.server').setLevel(logging.WARNING)

    # Load .env file and discover connection profiles
    from .connection_manager import ConnectionManager
    ConnectionManager.load_profiles(env_path=str(env_file) if env_file else None)

    # Which tools to serve. Resolved after the env file is loaded so it may be
    # configured there, and validated now so a bad selector fails at startup.
    from . import tool_filter
    from .tools import get_all_tools
    tool_filter.configure(allowed=allowed_tools, blocked=blocked_tools)
    try:
        served = len(get_all_tools())
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    if tool_filter.configured() != (None, None):
        logging.getLogger(__name__).info(
            "Serving %d of %d tools", served, len(get_all_tools(apply_filter=False))
        )
        if served == 0:
            raise click.ClickException(
                "The configured tool selection leaves no tools to serve."
            )

    asyncio.run(
        serve(transport=transport.lower(), host=host, port=port, mount_path=mount_path)
    )


if __name__ == "__main__":
    main()

