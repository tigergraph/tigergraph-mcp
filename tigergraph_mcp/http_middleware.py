# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""ASGI middleware that authenticates HTTP/SSE clients against TigerGraph.

Every request to an HTTP/SSE MCP endpoint must carry the user's TigerGraph
credentials in headers. The middleware parses them, validates against the
target TigerGraph instance, and binds the validated credentials to a
context variable that ``MCPServer._session_manager_for_current_request``
reads when seeding the per-session connection pool. Failed validation
returns ``401 Unauthorized`` before the MCP layer sees the request, so
``MultiServerMCPClient`` (or any HTTP MCP client) sees the connection
attempt fail.

Note: transport-level authentication (who is allowed to reach the MCP
server URL at all) is intentionally out of scope here — that belongs to
a reverse proxy / API gateway and may use any auth model the deployment
prefers. This middleware only handles the TigerGraph-level credentials
that the session ultimately uses for tool calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from pyTigerGraph import AsyncTigerGraphConnection
from pyTigerGraph.common.exception import TigerGraphException

from .connection_manager import (
    resolve_profile_name,
    validate_connection,
    validate_timeout,
    list_env_profiles,
    profile_credentials,
    profile_topology,
    reset_pending_credentials,
    set_pending_credentials,
)

logger = logging.getLogger(__name__)


# Header names this middleware reads. Lowercase — ASGI delivers headers
# in lowercase already.
HOST_HEADER = "x-tg-host"
GRAPHNAME_HEADER = "x-tg-graphname"
USERNAME_HEADER = "x-tg-username"
PASSWORD_HEADER = "x-tg-password"
SECRET_HEADER = "x-tg-secret"
API_TOKEN_HEADER = "x-tg-api-token"
JWT_TOKEN_HEADER = "x-tg-jwt-token"
RESTPP_PORT_HEADER = "x-tg-restpp-port"
GS_PORT_HEADER = "x-tg-gs-port"
SSL_PORT_HEADER = "x-tg-ssl-port"
TG_CLOUD_HEADER = "x-tg-tgcloud"
CERT_PATH_HEADER = "x-tg-cert-path"
PROFILE_HEADER = "x-tg-profile"
# Set by the client on every request after the session is established.
MCP_SESSION_HEADER = "mcp-session-id"

DEFAULT_PROFILE = "default"


def _allowed_profiles() -> Optional[set]:
    """Profiles a client may name, or None when unrestricted.

    ``TG_HTTP_ALLOWED_PROFILES=a,b`` narrows it.
    """
    raw = os.getenv("TG_HTTP_ALLOWED_PROFILES", "").strip()
    if not raw:
        return None
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _read_headers(scope_headers: Iterable[Tuple[bytes, bytes]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw_name, raw_value in scope_headers:
        name = raw_name.decode("latin-1").lower()
        # Headers may repeat; last wins (consistent with most HTTP servers).
        out[name] = raw_value.decode("latin-1")
    return out


def _resolve(headers: Mapping[str, str]) -> Tuple[Optional[Dict[str, Any]], int, str]:
    """Resolve the connection config for one request.

    Server-side profiles supply topology (and optionally credentials); request
    headers override any field, for that session only. Four shapes are
    supported:

    ==============================  ===========================================
    Headers sent                    Result
    ==============================  ===========================================
    X-TG-Profile only               that profile's topology + its credentials
    X-TG-Profile + credentials      that profile's topology, caller's identity
    credentials only                'default' topology, caller's identity
    none                            'default' profile as configured
    ==============================  ===========================================

    Whether a profile carries credentials is the operator's decision when
    writing the env file: a profile with credentials is a shared identity
    usable by anyone who can reach the server, which suits a demo or
    single-user deployment; a profile with only topology forces every caller
    to identify itself.

    Returns ``(config, 0, "")`` on success, or ``(None, status, reason)``.
    Topology problems — an unknown profile, no resolvable host — are ``400``;
    a missing identity is ``401``. The two are kept distinct so a caller can
    tell "I addressed the wrong server" from "my credentials are wrong".
    """
    # X-TG-Profile names which configured profile this session's connection is
    # built from. Absent, it is the server's default profile. Credentials the
    # request supplies always win over the profile's own.
    profile = resolve_profile_name(headers.get(PROFILE_HEADER))

    allowed = _allowed_profiles()
    if allowed is not None and profile not in allowed:
        return None, 400, f"Profile '{profile}' is not available on this server."
    if profile != DEFAULT_PROFILE and profile not in list_env_profiles():
        return None, 400, (
            f"Unknown profile '{profile}'. Profiles are defined in the server's "
            "environment; omit X-TG-Profile to use the default."
        )

    topology = profile_topology(profile)

    host = headers.get(HOST_HEADER) or topology["host"]
    if not host:
        return None, 400, (
            f"No TigerGraph host: profile '{profile}' defines none and no "
            "X-TG-Host header was sent."
        )

    api_token = headers.get(API_TOKEN_HEADER, "")
    jwt_token = headers.get(JWT_TOKEN_HEADER, "")
    username = headers.get(USERNAME_HEADER, "")
    password = headers.get(PASSWORD_HEADER, "")
    secret = headers.get(SECRET_HEADER, "")

    if not (api_token or jwt_token or secret or (username and password)):
        env_creds = profile_credentials(profile)
        api_token = env_creds["api_token"]
        jwt_token = env_creds["jwt_token"]
        secret = env_creds["secret"]
        username = env_creds["username"]
        password = env_creds["password"]
        if not (api_token or jwt_token or secret or (username and password)):
            return None, 401, (
                f"No credentials: profile '{profile}' defines none, so the "
                "request must send X-TG-Api-Token, X-TG-Jwt-Token, or "
                "X-TG-Username with X-TG-Password."
            )

    return {
        "profile": profile,
        "host": host,
        "graphname": headers.get(GRAPHNAME_HEADER) or topology["graphname"],
        "username": username or "tigergraph",
        "password": password or "tigergraph",
        "secret": secret,
        "api_token": api_token,
        "jwt_token": jwt_token,
        "restpp_port": headers.get(RESTPP_PORT_HEADER) or topology["restpp_port"],
        "gs_port": headers.get(GS_PORT_HEADER) or topology["gs_port"],
        "ssl_port": headers.get(SSL_PORT_HEADER) or topology["ssl_port"],
        "tg_cloud": (
            headers[TG_CLOUD_HEADER].lower() == "true"
            if TG_CLOUD_HEADER in headers else topology["tg_cloud"]
        ),
        "cert_path": headers.get(CERT_PATH_HEADER) or topology["cert_path"],
    }, 0, ""


def _parse_credentials(headers: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    """Config for this request, or None if one could not be assembled."""
    creds, _, _ = _resolve(headers)
    return creds


def _build_connection(creds: Mapping[str, Any]) -> AsyncTigerGraphConnection:
    return AsyncTigerGraphConnection(
        host=creds["host"],
        graphname=creds.get("graphname", ""),
        username=creds.get("username", "tigergraph"),
        password=creds.get("password", "tigergraph"),
        gsqlSecret=creds.get("secret", "") or "",
        apiToken=creds.get("api_token", "") or "",
        jwtToken=creds.get("jwt_token", "") or "",
        restppPort=creds.get("restpp_port", "9000"),
        gsPort=creds.get("gs_port", "14240"),
        sslPort=creds.get("ssl_port", "443"),
        tgCloud=bool(creds.get("tg_cloud", False)),
        certPath=creds.get("cert_path"),
    )


async def _validate(creds: Dict[str, Any]) -> None:
    """Validate credentials by talking to TigerGraph.

    Mutates ``creds`` in place: when password auth succeeds, the minted
    token is recorded as ``api_token`` so downstream code reuses it
    rather than re-authenticating.

    Raises :class:`TigerGraphException` (or any underlying network error)
    if the credentials are rejected.
    """
    conn = _build_connection(creds)
    try:
        await validate_connection(conn)
        if not creds.get("api_token") and not creds.get("jwt_token"):
            if getattr(conn, "apiToken", None):
                creds["api_token"] = conn.apiToken
    finally:
        try:
            await conn.aclose()
        except Exception:
            pass


class CredentialHeadersMiddleware:
    """ASGI middleware that requires + validates TigerGraph credentials."""

    def __init__(self, app, validate: bool = True):
        """Wrap ``app`` with TigerGraph credential validation.

        Args:
            app: The downstream ASGI app.
            validate: When ``True`` (the default), each request triggers a
                live TigerGraph validation. Disable only for tests; in
                production the validation is the whole point.
        """
        self.app = app
        self.validate = validate

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = _read_headers(scope.get("headers") or [])
        creds, status, reason = _resolve(headers)
        if creds is None:
            await _send_error(send, status, reason)
            return

        # Credentials are proven when the session's connection is established.
        # A client's headers are fixed for the life of its session, so probing
        # again on later requests re-proves something that cannot have changed;
        # the session's connection pool holds the validated connection.
        establishing = not headers.get(MCP_SESSION_HEADER)
        if self.validate and establishing:
            try:
                await _validate(creds)
            except TigerGraphException as e:
                logger.info(
                    "TigerGraph auth rejected for host=%s: %s",
                    creds.get("host"), e,
                )
                await _send_error(send, 401, f"TigerGraph rejected the credentials: {e}")
                return
            except asyncio.TimeoutError:
                logger.warning("Timed out reaching TigerGraph at host=%s",
                               creds.get("host"))
                await _send_error(
                    send, 502,
                    f"Could not reach TigerGraph at {creds.get('host')}: "
                    f"timed out after {validate_timeout():g}s. Check the host, "
                    "ports, and network path.",
                )
                return
            except Exception as e:
                # Not an auth failure: the server could not be reached at all,
                # so say that rather than blaming the credentials.
                logger.warning(
                    "Could not reach TigerGraph at host=%s: %s",
                    creds.get("host"), e,
                )
                await _send_error(
                    send, 502,
                    f"Could not reach TigerGraph at {creds.get('host')}: {e}",
                )
                return

        token = set_pending_credentials(creds)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_pending_credentials(token)


async def _send_error(send, status: int, message: str) -> None:
    body = json.dumps({"error": message}).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("latin-1")),
    ]
    if status == 401:
        headers.append((b"www-authenticate", b'Bearer realm="tigergraph-mcp"'))
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": headers,
    })
    await send({"type": "http.response.body", "body": body})
