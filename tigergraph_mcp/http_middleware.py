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

import json
import logging
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from pyTigerGraph import AsyncTigerGraphConnection
from pyTigerGraph.common.exception import TigerGraphException

from .connection_manager import (
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


def _read_headers(scope_headers: Iterable[Tuple[bytes, bytes]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw_name, raw_value in scope_headers:
        name = raw_name.decode("latin-1").lower()
        # Headers may repeat; last wins (consistent with most HTTP servers).
        out[name] = raw_value.decode("latin-1")
    return out


def _parse_credentials(headers: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    """Extract TigerGraph credentials from request headers.

    Returns ``None`` if no host is supplied or no credential mechanism is
    present. A non-None return means the headers are well-formed; it does
    NOT mean the credentials are valid against TigerGraph.
    """
    host = headers.get(HOST_HEADER)
    if not host:
        return None

    api_token = headers.get(API_TOKEN_HEADER, "")
    jwt_token = headers.get(JWT_TOKEN_HEADER, "")
    username = headers.get(USERNAME_HEADER, "")
    password = headers.get(PASSWORD_HEADER, "")

    if not (api_token or jwt_token or (username and password)):
        return None

    return {
        "host": host,
        "graphname": headers.get(GRAPHNAME_HEADER, ""),
        "username": username or "tigergraph",
        "password": password or "tigergraph",
        "secret": headers.get(SECRET_HEADER, ""),
        "api_token": api_token,
        "jwt_token": jwt_token,
        "restpp_port": headers.get(RESTPP_PORT_HEADER, "9000"),
        "gs_port": headers.get(GS_PORT_HEADER, "14240"),
        "ssl_port": headers.get(SSL_PORT_HEADER, "443"),
        "tg_cloud": headers.get(TG_CLOUD_HEADER, "false").lower() == "true",
        "cert_path": headers.get(CERT_PATH_HEADER) or None,
    }


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
        if not creds.get("api_token") and not creds.get("jwt_token"):
            # Password auth: minting a token also validates the password.
            await conn.getToken()
            if getattr(conn, "apiToken", None):
                creds["api_token"] = conn.apiToken
        else:
            # Token auth: a cheap authenticated ping is enough.
            await conn.echo()
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
        creds = _parse_credentials(headers)
        if creds is None:
            await _send_401(
                send,
                "Missing TigerGraph credentials. Set X-TG-Host plus one of "
                "(X-TG-Api-Token, X-TG-Jwt-Token, X-TG-Username + X-TG-Password).",
            )
            return

        if self.validate:
            try:
                await _validate(creds)
            except TigerGraphException as e:
                logger.info(
                    "TigerGraph auth rejected for host=%s: %s",
                    creds.get("host"), e,
                )
                await _send_401(send, f"TigerGraph authentication failed: {e}")
                return
            except Exception as e:  # network errors, bad host, etc.
                logger.warning(
                    "TigerGraph auth probe error for host=%s: %s",
                    creds.get("host"), e,
                )
                await _send_401(send, f"TigerGraph authentication failed: {e}")
                return

        token = set_pending_credentials(creds)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_pending_credentials(token)


async def _send_401(send, message: str) -> None:
    body = json.dumps({"error": message}).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": 401,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("latin-1")),
            (b"www-authenticate", b'Bearer realm="tigergraph-mcp"'),
        ],
    })
    await send({"type": "http.response.body", "body": body})
