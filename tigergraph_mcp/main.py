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
def main(
    verbose: bool,
    env_file: Path = None,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    mount_path: str = "/mcp",
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

    asyncio.run(
        serve(transport=transport.lower(), host=host, port=port, mount_path=mount_path)
    )


if __name__ == "__main__":
    main()

