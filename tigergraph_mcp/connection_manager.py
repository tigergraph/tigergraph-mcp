# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Connection manager for MCP server.

Manages AsyncTigerGraphConnection instances for MCP tools.
Supports named connection profiles via environment variables:

  - Default profile uses unprefixed ``TG_*`` vars (backward compatible).
  - Named profiles use ``<PROFILE>_TG_*`` vars (e.g. ``STAGING_TG_HOST``).
  - ``TG_PROFILE`` selects the active profile (default: ``"default"``).

For stdio mode (one-user-per-process), the ``ConnectionManager`` class with
its classmethod API is the singleton store. For HTTP/SSE mode (many users
on one server) each session creates its own ``SessionConnectionManager``
instance; the active instance is published via a ``ContextVar`` so the
module-level ``get_connection()`` resolves the right pool per request.
"""

import contextvars
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from pyTigerGraph import AsyncTigerGraphConnection

logger = logging.getLogger(__name__)

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    _dotenv_available = True
except ImportError:
    _dotenv_available = False


def _load_env_file(env_path: Optional[str] = None) -> None:
    """Load environment variables from .env file if available.

    Args:
        env_path: Optional path to .env file. If not provided, looks for .env in current directory.
    """
    if not _dotenv_available:
        return

    if env_path:
        env_file = Path(env_path).expanduser().resolve()
    else:
        # Look for .env in current directory and parent directories
        current_dir = Path.cwd()
        env_file = None
        for directory in [current_dir] + list(current_dir.parents):
            potential_env = directory / ".env"
            if potential_env.exists():
                env_file = potential_env
                break

        if env_file is None:
            # Also check in the directory where the script is running
            env_file = Path(".env")

    if env_file and env_file.exists():
        load_dotenv(env_file, override=False)  # Don't override existing env vars
        logger.debug(f"Loaded environment variables from {env_file}")
    elif env_path:
        logger.warning(f"Specified .env file not found: {env_path}")


_ENV_ALIASES = {
    "API_TOKEN": "TOKEN",
    "GS_PORT": "GSQL_PORT",
}


def _get_env_for_profile(profile: str, key: str, default: str = "") -> str:
    """Resolve a config value for a profile.

    Default profile uses unprefixed ``TG_*`` vars.
    Named profiles use ``<PROFILE>_TG_*`` vars, falling back to
    the unprefixed ``TG_*`` var, then the built-in *default*.

    Legacy env var aliases (``TG_TOKEN`` -> ``TG_API_TOKEN``,
    ``TG_GSQL_PORT`` -> ``TG_GS_PORT``) are resolved automatically.
    """
    if profile == "default":
        value = os.getenv(f"TG_{key}", "")
        if not value:
            alias = _ENV_ALIASES.get(key)
            if alias:
                value = os.getenv(f"TG_{alias}", "")
        return value or default

    value = os.getenv(f"{profile.upper()}_TG_{key}", "")
    if not value:
        alias = _ENV_ALIASES.get(key)
        if alias:
            value = os.getenv(f"{profile.upper()}_TG_{alias}", "")
    if not value:
        value = os.getenv(f"TG_{key}", "")
    if not value:
        alias = _ENV_ALIASES.get(key)
        if alias:
            value = os.getenv(f"TG_{alias}", "")
    return value or default


def _discover_profiles_into(profile_set: set) -> None:
    """Add every ``<PROFILE>_TG_HOST`` env var as a profile name."""
    for key in os.environ:
        if key.endswith("_TG_HOST") and not key.startswith("TG_"):
            profile = key.rsplit("_TG_HOST", 1)[0].lower()
            profile_set.add(profile)
    profile_set.add("default")


def _build_or_reuse(
    pool: Dict[str, AsyncTigerGraphConnection],
    profile: str,
    graph_name: Optional[str],
    on_default_created: Optional[Callable[[AsyncTigerGraphConnection], None]] = None,
) -> AsyncTigerGraphConnection:
    """Shared pool/build logic used by both manager flavors.

    Looks up by ``profile`` (cache key) and reuses if present. When a
    cached connection exists and the caller passes a different
    ``graph_name``, the cached connection's ``graphname`` is mutated in
    place. On miss, builds a fresh ``AsyncTigerGraphConnection`` from the
    profile's env vars, inserts it into ``pool``, and (for the default
    profile) invokes ``on_default_created`` so callers can update any
    legacy "default connection" pointer.
    """
    if profile in pool:
        conn = pool[profile]
        if graph_name and conn.graphname != graph_name:
            conn.graphname = graph_name
        return conn

    host = _get_env_for_profile(profile, "HOST", "http://127.0.0.1")
    graphname = graph_name or _get_env_for_profile(profile, "GRAPHNAME", "")
    username = _get_env_for_profile(profile, "USERNAME", "tigergraph")
    password = _get_env_for_profile(profile, "PASSWORD", "tigergraph")
    secret = _get_env_for_profile(profile, "SECRET", "")
    api_token = _get_env_for_profile(profile, "API_TOKEN", "")
    jwt_token = _get_env_for_profile(profile, "JWT_TOKEN", "")
    restpp_port = _get_env_for_profile(profile, "RESTPP_PORT", "9000")
    gs_port = _get_env_for_profile(profile, "GS_PORT", "14240")
    ssl_port = _get_env_for_profile(profile, "SSL_PORT", "443")
    tg_cloud = _get_env_for_profile(profile, "TGCLOUD", "false").lower() == "true"
    cert_path = _get_env_for_profile(profile, "CERT_PATH", "") or None

    conn = AsyncTigerGraphConnection(
        host=host,
        graphname=graphname,
        username=username,
        password=password,
        gsqlSecret=secret if secret else "",
        apiToken=api_token if api_token else "",
        jwtToken=jwt_token if jwt_token else "",
        restppPort=restpp_port,
        gsPort=gs_port,
        sslPort=ssl_port,
        tgCloud=tg_cloud,
        certPath=cert_path,
    )

    pool[profile] = conn
    if profile == "default" and on_default_created is not None:
        on_default_created(conn)

    logger.info(f"Created connection for profile '{profile}' -> {host}")
    return conn


def _profile_info(profile: str) -> Dict[str, str]:
    """Build the non-sensitive profile info dict. Shared by both managers."""
    api_token = _get_env_for_profile(profile, "API_TOKEN", "")
    jwt_token = _get_env_for_profile(profile, "JWT_TOKEN", "")
    if jwt_token:
        auth_mode = "token (JWT)"
    elif api_token:
        auth_mode = "token (API)"
    else:
        auth_mode = "password"

    return {
        "profile": profile,
        "host": _get_env_for_profile(profile, "HOST", "http://127.0.0.1"),
        "graphname": _get_env_for_profile(profile, "GRAPHNAME", ""),
        "username": _get_env_for_profile(profile, "USERNAME", "tigergraph"),
        "auth_mode": auth_mode,
        "restpp_port": _get_env_for_profile(profile, "RESTPP_PORT", "9000"),
        "gs_port": _get_env_for_profile(profile, "GS_PORT", "14240"),
        "tgcloud": _get_env_for_profile(profile, "TGCLOUD", "false"),
    }


async def _aclose_pool(pool: Dict[str, AsyncTigerGraphConnection]) -> None:
    for key, conn in list(pool.items()):
        try:
            await conn.aclose()
            logger.debug(f"Closed connection for profile '{key}'")
        except Exception as e:
            logger.warning(f"Error closing connection '{key}': {e}")
    pool.clear()


class ConnectionManager:
    """Process-global connection pool, used by stdio mode.

    Connections are pooled by ``profile`` so that repeated calls with the
    same profile reuse the same ``AsyncTigerGraphConnection`` (and its
    underlying ``aiohttp`` connection pool). Call
    ``await ConnectionManager.close_all()`` at server shutdown to release
    those pools.
    """

    _connection_pool: Dict[str, AsyncTigerGraphConnection] = {}
    _profiles: set = set()

    # Legacy single-connection reference for backward compat.
    _default_connection: Optional[AsyncTigerGraphConnection] = None

    @classmethod
    def load_profiles(cls, env_path: Optional[str] = None) -> None:
        """Discover available profiles from environment variables.

        Profiles are detected by scanning for ``<PROFILE>_TG_HOST`` env vars.
        The ``"default"`` profile always exists and uses unprefixed ``TG_*``
        vars. Called once at server startup.
        """
        _load_env_file(env_path)
        _discover_profiles_into(cls._profiles)
        logger.info(f"Discovered connection profiles: {sorted(cls._profiles)}")

    @classmethod
    def list_profiles(cls) -> List[str]:
        """Return sorted list of discovered profile names."""
        if not cls._profiles:
            cls._profiles.add("default")
        return sorted(cls._profiles)

    @classmethod
    def get_default_connection(cls) -> Optional[AsyncTigerGraphConnection]:
        """Get the default connection instance (backward compat)."""
        return cls._default_connection

    @classmethod
    def set_default_connection(cls, conn: AsyncTigerGraphConnection) -> None:
        """Set the default connection instance (backward compat)."""
        cls._default_connection = conn

    @classmethod
    def get_connection_for_profile(
        cls,
        profile: str = "default",
        graph_name: Optional[str] = None,
    ) -> AsyncTigerGraphConnection:
        """Get or create a connection for the given profile and optional graph."""
        def _set_default(conn: AsyncTigerGraphConnection) -> None:
            cls._default_connection = conn

        return _build_or_reuse(
            cls._connection_pool, profile, graph_name, _set_default
        )

    @classmethod
    def get_profile_info(cls, profile: str = "default") -> Dict[str, str]:
        """Return non-sensitive connection info for a profile."""
        return _profile_info(profile)

    @classmethod
    def create_connection_from_env(
        cls, env_path: Optional[str] = None
    ) -> AsyncTigerGraphConnection:
        """Create a connection from environment variables (backward compat).

        Equivalent to ``get_connection_for_profile("default")``.
        """
        _load_env_file(env_path)
        return cls.get_connection_for_profile("default")

    @classmethod
    async def close_all(cls) -> None:
        """Close all pooled connections and release their HTTP connection pools."""
        await _aclose_pool(cls._connection_pool)
        cls._default_connection = None


class SessionConnectionManager:
    """Per-session connection pool, used by HTTP/SSE mode.

    Each MCP session owns one instance for the lifetime of the session.
    Same method surface as ``ConnectionManager`` but with instance state,
    so concurrent sessions can't see each other's connections.
    """

    def __init__(self) -> None:
        self._connection_pool: Dict[str, AsyncTigerGraphConnection] = {}
        self._profiles: set = set()
        self._default_connection: Optional[AsyncTigerGraphConnection] = None

    def load_profiles(self, env_path: Optional[str] = None) -> None:
        _load_env_file(env_path)
        _discover_profiles_into(self._profiles)
        logger.info(
            f"[session] Discovered connection profiles: {sorted(self._profiles)}"
        )

    def list_profiles(self) -> List[str]:
        if not self._profiles:
            self._profiles.add("default")
        return sorted(self._profiles)

    def get_default_connection(self) -> Optional[AsyncTigerGraphConnection]:
        return self._default_connection

    def set_default_connection(self, conn: AsyncTigerGraphConnection) -> None:
        self._default_connection = conn

    def get_connection_for_profile(
        self,
        profile: str = "default",
        graph_name: Optional[str] = None,
    ) -> AsyncTigerGraphConnection:
        def _set_default(conn: AsyncTigerGraphConnection) -> None:
            self._default_connection = conn

        return _build_or_reuse(
            self._connection_pool, profile, graph_name, _set_default
        )

    def get_profile_info(self, profile: str = "default") -> Dict[str, str]:
        return _profile_info(profile)

    async def close_all(self) -> None:
        await _aclose_pool(self._connection_pool)
        self._default_connection = None


# ---------------------------------------------------------------------------
# Active-manager resolution
#
# ``_current_session_manager`` is a ContextVar that HTTP/SSE transports set
# before dispatching each tool call. When unset (the stdio default), tool
# functions fall back to the process-global ``ConnectionManager`` class.
# ---------------------------------------------------------------------------

_current_session_manager: contextvars.ContextVar[Optional[SessionConnectionManager]] = (
    contextvars.ContextVar("tg_mcp_session_manager", default=None)
)


# Credentials read from request headers (HTTP/SSE transports). Populated by
# ``CredentialHeadersMiddleware`` for the duration of one request, consumed
# when a session manager is first looked up to seed its default connection.
_pending_credentials: contextvars.ContextVar[Optional[Dict[str, Any]]] = (
    contextvars.ContextVar("tg_mcp_pending_credentials", default=None)
)


def set_pending_credentials(creds: Optional[Dict[str, Any]]):
    """Bind credentials extracted from request headers for the active request.

    Returns the contextvars token so middleware can reset it on request exit.
    """
    return _pending_credentials.set(creds)


def get_pending_credentials() -> Optional[Dict[str, Any]]:
    """Return the credentials bound for the active request, if any."""
    return _pending_credentials.get()


def reset_pending_credentials(token) -> None:
    """Reset the pending-credentials ContextVar to its prior state."""
    _pending_credentials.reset(token)


def get_active_manager():
    """Return the currently active manager.

    A ``SessionConnectionManager`` if one is set in the ContextVar (HTTP/SSE
    request scope), else the ``ConnectionManager`` class itself acting as
    the process-global singleton.
    """
    cm = _current_session_manager.get()
    return cm if cm is not None else ConnectionManager


@contextmanager
def use_session_manager(
    manager: SessionConnectionManager,
) -> Iterator[SessionConnectionManager]:
    """Bind a session manager as the active manager inside a ``with`` block.

    Intended for HTTP/SSE transports that own a manager per session and
    need each tool dispatch to resolve against it. The token-based reset
    keeps the binding correct under concurrent requests.
    """
    token = _current_session_manager.set(manager)
    try:
        yield manager
    finally:
        _current_session_manager.reset(token)


def get_connection(
    profile: Optional[str] = None,
    graph_name: Optional[str] = None,
    connection_config: Optional[Dict[str, Any]] = None,
) -> AsyncTigerGraphConnection:
    """Get or create an async TigerGraph connection.

    Args:
        profile: Connection profile name. Falls back to ``TG_PROFILE`` env var,
            then ``"default"``.
        graph_name: Graph name override. If provided, updates the connection's
            active graph.
        connection_config: Explicit connection config dict. If provided, creates
            a one-off connection (not pooled).

    Returns:
        AsyncTigerGraphConnection instance.
    """
    if connection_config:
        return AsyncTigerGraphConnection(
            host=connection_config.get("host", "http://127.0.0.1"),
            graphname=connection_config.get("graphname", graph_name or ""),
            username=connection_config.get("username", "tigergraph"),
            password=connection_config.get("password", "tigergraph"),
            gsqlSecret=connection_config.get("gsqlSecret", ""),
            apiToken=connection_config.get("apiToken", ""),
            jwtToken=connection_config.get("jwtToken", ""),
            restppPort=connection_config.get("restppPort", "9000"),
            gsPort=connection_config.get("gsPort", "14240"),
            sslPort=connection_config.get("sslPort", "443"),
            tgCloud=connection_config.get("tgCloud", False),
            certPath=connection_config.get("certPath", None),
        )

    effective_profile = profile or os.getenv("TG_PROFILE", "default")
    active = get_active_manager()
    return active.get_connection_for_profile(effective_profile, graph_name)
