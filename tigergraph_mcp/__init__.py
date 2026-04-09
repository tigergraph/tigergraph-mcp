# Copyright 2025 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Model Context Protocol (MCP) support for TigerGraph.

This module provides MCP server capabilities for TigerGraph, allowing
AI agents to interact with TigerGraph through the Model Context Protocol.
"""

from importlib.metadata import version as _pkg_version, PackageNotFoundError

from .server import serve, MCPServer
from .connection_manager import get_connection, ConnectionManager
from .tool_names import TigerGraphToolName

try:
    __version__ = _pkg_version("tigergraph-mcp")
except PackageNotFoundError:
    __version__ = "1.0.0"

__license__ = "Apache 2"

__all__ = [
    "serve",
    "MCPServer",
    "get_connection",
    "ConnectionManager",
    "TigerGraphToolName",
]

