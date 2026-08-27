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
    default_profile_name,
    list_env_profiles,
    resolve_profile_name,
    validate_connection,
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
    profile: Optional[str] = Field(
        None,
        description=(
            "Profile whose connection these credentials replace. Omit, or pass "
            "'default', to replace the default profile's connection. Only this "
            "profile is affected; other profiles in the session keep theirs."
        ),
    )
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
        "Re-points one of the session's connections at a TigerGraph instance. "
        "Omit ``profile`` to replace the default profile's connection, or name "
        "a profile to replace only that one, leaving the session's other "
        "profiles untouched. Stdio mode uses env-var profiles instead and does "
        "not need this tool.\n\n"
        "Either ``api_token``/``jwt_token`` OR ``username`` + ``password`` "
        "must be supplied. The credentials live only in the session's "
        "in-memory connection pool and are dropped on disconnect."
    ),
    inputSchema=AuthenticateToolInput.model_json_schema(),
)


async def list_connections() -> List[TextContent]:
    """List all available connection profiles."""
    try:
        # The profiles a caller may name are the ones the server configures,
        # which is the same set in stdio and in an HTTP session.
        profiles = list_env_profiles()
        default = default_profile_name()
        if default not in profiles:
            profiles.append(default)
        profiles = sorted(profiles)

        active = get_active_manager()
        open_now = set(getattr(active, "_connection_pool", {}))

        profile_details = []
        for p in profiles:
            info = dict(ConnectionManager.get_profile_info(p))
            info["is_default"] = p == default
            info["connected"] = p in open_now
            conn = getattr(active, "_connection_pool", {}).get(p)
            if conn is not None:
                # Reflect the live connection, which may differ from the
                # environment when credentials arrived with the request.
                info["host"] = conn.host
                info["username"] = conn.username
                info["graphname"] = conn.graphname or ""
            profile_details.append(info)

        return format_success(
            operation="list_connections",
            summary=(
                f"Found {len(profiles)} connection profile(s): "
                f"{', '.join(profiles)} (default: {default})"
            ),
            data={"profiles": profile_details, "count": len(profiles),
                  "default_profile": default},
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
        effective = resolve_profile_name(profile)
        info = dict(ConnectionManager.get_profile_info(effective))
        info["is_default"] = effective == default_profile_name()

        active = get_active_manager()
        conn = getattr(active, "_connection_pool", {}).get(effective)
        info["connected"] = conn is not None
        if conn is not None:
            info["host"] = conn.host
            info["username"] = conn.username
            info["graphname"] = conn.graphname or ""

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
    profile: Optional[str] = None,
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
        # Prove the credentials before touching the session, so a bad one
        # leaves the existing connection in place instead of replacing a
        # working connection with a broken one.
        target = resolve_profile_name(profile)
        try:
            await validate_connection(conn)
        except Exception as e:
            try:
                await conn.aclose()
            except Exception:
                pass
            return format_error(
                operation="authenticate",
                error=f"TigerGraph rejected the credentials for {host}: {e}",
                suggestions=[
                    "Check the host, username, and password or token",
                    f"The '{target}' profile's existing connection is unchanged",
                ],
            )

        is_default = target == default_profile_name()
        prior = active._connection_pool.pop(target, None)
        if prior is not None:
            try:
                await prior.aclose()
            except Exception:
                pass
        active.register_connection(target, conn, as_default=is_default)

        if jwt_token:
            auth_mode = "token (JWT)"
        elif api_token:
            auth_mode = "token (API)"
        else:
            auth_mode = "password"

        return format_success(
            operation="authenticate",
            summary=(
                f"Session authenticated to {host} as profile '{target}' ({auth_mode})"
            ),
            data={
                "host": host,
                "graphname": graphname or "",
                "auth_mode": auth_mode,
                "profile": target,
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
