# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Connection profile tools for MCP.

Allows agents to list available connection profiles, inspect
non-sensitive connection details for a given profile, and (in
HTTP/SSE multi-user mode) register per-session credentials so
subsequent tool calls in that session use them.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from mcp.types import Tool, TextContent
from pyTigerGraph import AsyncTigerGraphConnection

from ..tool_names import TigerGraphToolName
from ..connection_manager import (
    ConnectionManager,
    SessionConnectionManager,
    get_active_manager,
)
from ..response_formatter import format_success, format_error


class ListConnectionsToolInput(BaseModel):
    """Input schema for listing available connection profiles."""


class ShowConnectionToolInput(BaseModel):
    """Input schema for showing connection details."""
    profile: Optional[str] = Field(
        None,
        description=(
            "Connection profile name to inspect. "
            "If not provided, shows the active profile (from TG_PROFILE env var or 'default')."
        ),
    )


class AuthenticateToolInput(BaseModel):
    """Input schema for registering session credentials."""
    host: str = Field(..., description="TigerGraph host URL, e.g. https://acme.tgcloud.io.")
    graphname: Optional[str] = Field(None, description="Default graph for this session.")
    username: Optional[str] = Field(None, description="TigerGraph username (password auth).")
    password: Optional[str] = Field(None, description="TigerGraph password (password auth).")
    secret: Optional[str] = Field(None, description="TigerGraph GSQL secret (alternative to password auth).")
    api_token: Optional[str] = Field(None, description="TigerGraph REST++ API token (token auth).")
    jwt_token: Optional[str] = Field(None, description="TigerGraph JWT token (token auth).")
    restpp_port: Optional[str] = Field(None, description="REST++ port (default 9000).")
    gs_port: Optional[str] = Field(None, description="GSQL Server port (default 14240).")
    ssl_port: Optional[str] = Field(None, description="SSL port (default 443).")
    tg_cloud: Optional[bool] = Field(None, description="True if connecting to TigerGraph Cloud.")
    cert_path: Optional[str] = Field(None, description="Path to a CA bundle for TLS verification.")


list_connections_tool = Tool(
    name=TigerGraphToolName.LIST_CONNECTIONS,
    description=(
        "List all available TigerGraph connection profiles. "
        "Profiles are configured via environment variables: "
        "the default profile uses TG_HOST, TG_USERNAME, etc., "
        "while named profiles use <PROFILE>_TG_HOST, <PROFILE>_TG_USERNAME, etc."
    ),
    inputSchema=ListConnectionsToolInput.model_json_schema(),
)

show_connection_tool = Tool(
    name=TigerGraphToolName.SHOW_CONNECTION,
    description=(
        "Show non-sensitive connection details for a specific profile "
        "(host, username, graph name, ports). Never reveals passwords or tokens."
    ),
    inputSchema=ShowConnectionToolInput.model_json_schema(),
)


authenticate_tool = Tool(
    name=TigerGraphToolName.AUTHENTICATE,
    description=(
        "Register TigerGraph credentials for the current MCP session.\n\n"
        "Typically the first tool call an HTTP/SSE client makes — pins the "
        "session's connection so subsequent tool calls go to the right "
        "TigerGraph with the right user. Stdio mode normally uses env-var "
        "profiles instead and does not need this tool.\n\n"
        "Either ``api_token``/``jwt_token`` OR ``username`` + ``password`` "
        "must be supplied. The credentials live only in the session's "
        "in-memory connection pool and are dropped on disconnect."
    ),
    inputSchema=AuthenticateToolInput.model_json_schema(),
)


async def list_connections() -> List[TextContent]:
    """List all available connection profiles."""
    try:
        profiles = ConnectionManager.list_profiles()
        profile_details = []
        for p in profiles:
            info = ConnectionManager.get_profile_info(p)
            profile_details.append(info)

        return format_success(
            operation="list_connections",
            summary=f"Found {len(profiles)} connection profile(s): {', '.join(profiles)}",
            data={"profiles": profile_details, "count": len(profiles)},
            suggestions=[
                "Show details: show_connection(profile='<name>')",
                "Use a profile: pass profile='<name>' to any tool",
            ],
        )
    except Exception as e:
        return format_error(
            operation="list_connections",
            error=str(e),
        )


async def show_connection(profile: Optional[str] = None) -> List[TextContent]:
    """Show non-sensitive connection details for a profile."""
    try:
        import os
        effective = profile or os.getenv("TG_PROFILE", "default")
        info = ConnectionManager.get_profile_info(effective)

        return format_success(
            operation="show_connection",
            summary=f"Connection profile '{effective}': {info['host']}",
            data=info,
            suggestions=[
                "List all profiles: list_connections()",
                f"Use this profile: pass profile='{effective}' to any tool",
            ],
        )
    except Exception as e:
        return format_error(
            operation="show_connection",
            error=str(e),
        )


async def authenticate(
    host: str,
    graphname: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    secret: Optional[str] = None,
    api_token: Optional[str] = None,
    jwt_token: Optional[str] = None,
    restpp_port: Optional[str] = None,
    gs_port: Optional[str] = None,
    ssl_port: Optional[str] = None,
    tg_cloud: Optional[bool] = None,
    cert_path: Optional[str] = None,
) -> List[TextContent]:
    """Register credentials for the active session's connection pool.

    Only useful when the active manager is a :class:`SessionConnectionManager`
    (HTTP/SSE mode). In stdio mode, returns an error suggesting env-var profile
    configuration instead.
    """
    try:
        if not api_token and not jwt_token and not (username and password):
            return format_error(
                operation="authenticate",
                error="authenticate requires api_token, jwt_token, or (username + password)",
            )

        active = get_active_manager()
        if not isinstance(active, SessionConnectionManager):
            return format_error(
                operation="authenticate",
                error=(
                    "authenticate is only meaningful in HTTP/SSE mode "
                    "where each session owns a connection manager. "
                    "In stdio mode, configure TG_* env vars instead."
                ),
            )

        conn = AsyncTigerGraphConnection(
            host=host,
            graphname=graphname or "",
            username=username or "tigergraph",
            password=password or "tigergraph",
            gsqlSecret=secret or "",
            apiToken=api_token or "",
            jwtToken=jwt_token or "",
            restppPort=restpp_port or "9000",
            gsPort=gs_port or "14240",
            sslPort=ssl_port or "443",
            tgCloud=bool(tg_cloud) if tg_cloud is not None else False,
            certPath=cert_path or None,
        )
        # Replace any previous "default" connection in this session.
        prior = active._connection_pool.pop("default", None)
        if prior is not None:
            try:
                await prior.aclose()
            except Exception:
                pass
        active._connection_pool["default"] = conn
        active.set_default_connection(conn)

        if "default" not in active._profiles:
            active._profiles.add("default")

        if jwt_token:
            auth_mode = "token (JWT)"
        elif api_token:
            auth_mode = "token (API)"
        else:
            auth_mode = "password"

        return format_success(
            operation="authenticate",
            summary=f"Session authenticated to {host} ({auth_mode})",
            data={
                "host": host,
                "graphname": graphname or "",
                "auth_mode": auth_mode,
            },
            suggestions=[
                "Inspect: show_connection()",
                "Run a tool, e.g. get_graph_schema(graph_name='...')",
            ],
        )
    except Exception as e:
        return format_error(
            operation="authenticate",
            error=str(e),
        )
