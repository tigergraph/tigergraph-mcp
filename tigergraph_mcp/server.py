# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""MCP Server implementation for TigerGraph."""

import contextlib
import logging
from typing import Dict, List, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tool_names import TigerGraphToolName
from .response_formatter import format_error
from .connection_manager import (
    ConnectionManager,
    SessionConnectionManager,
    get_pending_credentials,
    use_session_manager,
)
from pyTigerGraph import AsyncTigerGraphConnection
from pyTigerGraph.common.exception import TigerGraphException
from .tools import (
    get_all_tools,
    # Connection profile operations
    list_connections,
    show_connection,
    authenticate,
    # Global schema operations (database level)
    get_global_schema,
    # Graph operations (database level)
    list_graphs,
    create_graph,
    drop_graph,
    clear_graph_data,
    # Schema operations (graph level)
    get_graph_schema,
    show_graph_details,
    # Schema modification
    update_schema,
    # Validation tools
    validate_schema_names,
    # Node tools
    add_node,
    add_nodes,
    get_node,
    get_nodes,
    delete_node,
    delete_nodes,
    has_node,
    get_node_edges,
    # Edge tools
    add_edge,
    add_edges,
    get_edge,
    get_edges,
    delete_edge,
    delete_edges,
    has_edge,
    # Query tools
    run_query,
    run_installed_query,
    install_query,
    drop_query,
    show_query,
    get_query_metadata,
    update_query_description,
    get_query_description,
    is_query_installed,
    get_neighbors,
    # Loading job tools
    create_loading_job,
    run_loading_job_with_file,
    run_loading_job_with_data,
    get_loading_jobs,
    get_loading_job_status,
    drop_loading_job,
    # Statistics tools
    get_vertex_count,
    get_edge_count,
    get_node_degree,
    # GSQL tools
    gsql,
    generate_gsql,
    generate_cypher,
    # Vector schema tools
    add_vector_attribute,
    drop_vector_attribute,
    list_vector_attributes,
    get_vector_index_status,
    # Vector data tools
    upsert_vectors,
    load_vectors_from_csv,
    load_vectors_from_json,
    search_top_k_similarity,
    fetch_vector,
    # Data Source tools
    create_data_source,
    update_data_source,
    get_data_source,
    drop_data_source,
    get_all_data_sources,
    drop_all_data_sources,
    preview_sample_data,
    # Discovery tools
    discover_tools,
    get_workflow,
    get_tool_info,
)

logger = logging.getLogger(__name__)


class MCPServer:
    """MCP Server for TigerGraph.

    In stdio mode (``multi_session=False``) every tool call uses the
    process-global :class:`ConnectionManager`. In HTTP/SSE mode
    (``multi_session=True``) each MCP session gets its own
    :class:`SessionConnectionManager`, looked up by ``id(session)`` on
    every tool call and bound via :func:`use_session_manager` for the
    duration of the dispatch.
    """

    def __init__(self, name: str = "TigerGraph-MCP", multi_session: bool = False):
        """Initialize the MCP server.

        Args:
            name: Server name advertised via MCP.
            multi_session: True for HTTP/SSE transports. Enables per-session
                connection pools so concurrent users don't share state.
        """
        self.server = Server(name)
        self.multi_session = multi_session
        self._session_managers: Dict[int, SessionConnectionManager] = {}
        self._setup_handlers()

    async def _session_manager_for_current_request(
        self,
    ) -> Optional[SessionConnectionManager]:
        """Look up (or create) the SessionConnectionManager for the in-flight request.

        Returns None in stdio mode or when no MCP session is bound to the
        current request context (defensive — should not happen in normal
        dispatch under HTTP/SSE). For HTTP/SSE sessions this also seeds the
        session's default connection and the cached privilege set from the
        credentials the middleware extracted.
        """
        if not self.multi_session:
            return None
        try:
            session = self.server.request_context.session
        except LookupError:
            return None
        key = id(session)
        cm = self._session_managers.get(key)
        if cm is None:
            cm = SessionConnectionManager()
            # Seed the session with the same profile set the process
            # discovered at startup so list_profiles is informative.
            cm._profiles = set(ConnectionManager._profiles) | {"default"}
            self._session_managers[key] = cm

        # Seed (or refresh) the session's default connection from credentials
        # the middleware extracted for the current request. ``creds`` may be
        # None when the middleware is disabled (tests) or when the request
        # arrived without headers (rejected by the middleware before this
        # code runs in normal HTTP deployments).
        creds = get_pending_credentials()
        if creds is not None and self._creds_differ(cm, creds):
            await self._apply_credentials(cm, creds)
        return cm

    @staticmethod
    def _creds_differ(cm: SessionConnectionManager, creds: dict) -> bool:
        """Cheap check: does ``creds`` describe a different host/auth than the
        session's current default connection?"""
        conn = cm.get_default_connection()
        if conn is None:
            return True
        if getattr(conn, "host", None) != creds.get("host"):
            return True
        # If a fresh token came through (e.g. password auth minted a new
        # token), pick it up.
        new_token = creds.get("api_token") or creds.get("jwt_token") or ""
        existing = getattr(conn, "apiToken", "") or getattr(conn, "jwtToken", "") or ""
        return new_token != existing

    async def _apply_credentials(
        self, cm: SessionConnectionManager, creds: dict
    ) -> None:
        """Build an :class:`AsyncTigerGraphConnection` from ``creds`` and pin
        it as the session's default connection."""
        conn = AsyncTigerGraphConnection(
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
        cm._connection_pool["default"] = conn
        cm.set_default_connection(conn)
        cm._profiles.add("default")

    async def aclose_session_managers(self) -> None:
        """Close all per-session connection pools. Call at shutdown."""
        managers = list(self._session_managers.values())
        self._session_managers.clear()
        for cm in managers:
            try:
                await cm.close_all()
            except Exception:
                logger.exception("Error closing a session connection manager")

    def _setup_handlers(self):
        """Setup MCP server handlers."""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List all available tools."""
            return get_all_tools()

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict) -> List[TextContent]:
            """Handle tool calls."""
            session_cm = await self._session_manager_for_current_request()
            bind_cm = (
                use_session_manager(session_cm)
                if session_cm is not None
                else contextlib.nullcontext()
            )
            with bind_cm:
                try:
                    match name:
                        # Connection profile operations
                        case TigerGraphToolName.LIST_CONNECTIONS:
                            return await list_connections(**arguments)
                        case TigerGraphToolName.SHOW_CONNECTION:
                            return await show_connection(**arguments)
                        case TigerGraphToolName.AUTHENTICATE:
                            return await authenticate(**arguments)
                        # Global schema operations (database level)
                        case TigerGraphToolName.GET_GLOBAL_SCHEMA:
                            return await get_global_schema(**arguments)
                        # Graph operations (database level)
                        case TigerGraphToolName.LIST_GRAPHS:
                            return await list_graphs(**arguments)
                        case TigerGraphToolName.CREATE_GRAPH:
                            return await create_graph(**arguments)
                        case TigerGraphToolName.DROP_GRAPH:
                            return await drop_graph(**arguments)
                        case TigerGraphToolName.CLEAR_GRAPH_DATA:
                            return await clear_graph_data(**arguments)
                        # Schema operations (graph level)
                        case TigerGraphToolName.GET_GRAPH_SCHEMA:
                            return await get_graph_schema(**arguments)
                        case TigerGraphToolName.SHOW_GRAPH_DETAILS:
                            return await show_graph_details(**arguments)
                        case TigerGraphToolName.UPDATE_SCHEMA:
                            return await update_schema(**arguments)
                        case TigerGraphToolName.VALIDATE_SCHEMA_NAMES:
                            return await validate_schema_names(**arguments)
                        # Node operations
                        case TigerGraphToolName.ADD_NODE:
                            return await add_node(**arguments)
                        case TigerGraphToolName.ADD_NODES:
                            return await add_nodes(**arguments)
                        case TigerGraphToolName.GET_NODE:
                            return await get_node(**arguments)
                        case TigerGraphToolName.GET_NODES:
                            return await get_nodes(**arguments)
                        case TigerGraphToolName.DELETE_NODE:
                            return await delete_node(**arguments)
                        case TigerGraphToolName.DELETE_NODES:
                            return await delete_nodes(**arguments)
                        case TigerGraphToolName.HAS_NODE:
                            return await has_node(**arguments)
                        case TigerGraphToolName.GET_NODE_EDGES:
                            return await get_node_edges(**arguments)
                        # Edge operations
                        case TigerGraphToolName.ADD_EDGE:
                            return await add_edge(**arguments)
                        case TigerGraphToolName.ADD_EDGES:
                            return await add_edges(**arguments)
                        case TigerGraphToolName.GET_EDGE:
                            return await get_edge(**arguments)
                        case TigerGraphToolName.GET_EDGES:
                            return await get_edges(**arguments)
                        case TigerGraphToolName.DELETE_EDGE:
                            return await delete_edge(**arguments)
                        case TigerGraphToolName.DELETE_EDGES:
                            return await delete_edges(**arguments)
                        case TigerGraphToolName.HAS_EDGE:
                            return await has_edge(**arguments)
                        # Query operations
                        case TigerGraphToolName.RUN_QUERY:
                            return await run_query(**arguments)
                        case TigerGraphToolName.RUN_INSTALLED_QUERY:
                            return await run_installed_query(**arguments)
                        case TigerGraphToolName.INSTALL_QUERY:
                            return await install_query(**arguments)
                        case TigerGraphToolName.DROP_QUERY:
                            return await drop_query(**arguments)
                        case TigerGraphToolName.SHOW_QUERY:
                            return await show_query(**arguments)
                        case TigerGraphToolName.GET_QUERY_METADATA:
                            return await get_query_metadata(**arguments)
                        case TigerGraphToolName.UPDATE_QUERY_DESCRIPTION:
                            return await update_query_description(**arguments)
                        case TigerGraphToolName.GET_QUERY_DESCRIPTION:
                            return await get_query_description(**arguments)
                        case TigerGraphToolName.IS_QUERY_INSTALLED:
                            return await is_query_installed(**arguments)
                        case TigerGraphToolName.GET_NEIGHBORS:
                            return await get_neighbors(**arguments)
                        # Loading job operations
                        case TigerGraphToolName.CREATE_LOADING_JOB:
                            return await create_loading_job(**arguments)
                        case TigerGraphToolName.RUN_LOADING_JOB_WITH_FILE:
                            return await run_loading_job_with_file(**arguments)
                        case TigerGraphToolName.RUN_LOADING_JOB_WITH_DATA:
                            return await run_loading_job_with_data(**arguments)
                        case TigerGraphToolName.GET_LOADING_JOBS:
                            return await get_loading_jobs(**arguments)
                        case TigerGraphToolName.GET_LOADING_JOB_STATUS:
                            return await get_loading_job_status(**arguments)
                        case TigerGraphToolName.DROP_LOADING_JOB:
                            return await drop_loading_job(**arguments)
                        # Statistics operations
                        case TigerGraphToolName.GET_VERTEX_COUNT:
                            return await get_vertex_count(**arguments)
                        case TigerGraphToolName.GET_EDGE_COUNT:
                            return await get_edge_count(**arguments)
                        case TigerGraphToolName.GET_NODE_DEGREE:
                            return await get_node_degree(**arguments)
                        # GSQL operations
                        case TigerGraphToolName.GSQL:
                            return await gsql(**arguments)
                        case TigerGraphToolName.GENERATE_GSQL:
                            return await generate_gsql(**arguments)
                        case TigerGraphToolName.GENERATE_CYPHER:
                            return await generate_cypher(**arguments)
                        # Vector schema operations
                        case TigerGraphToolName.ADD_VECTOR_ATTRIBUTE:
                            return await add_vector_attribute(**arguments)
                        case TigerGraphToolName.DROP_VECTOR_ATTRIBUTE:
                            return await drop_vector_attribute(**arguments)
                        case TigerGraphToolName.LIST_VECTOR_ATTRIBUTES:
                            return await list_vector_attributes(**arguments)
                        case TigerGraphToolName.GET_VECTOR_INDEX_STATUS:
                            return await get_vector_index_status(**arguments)
                        # Vector data operations
                        case TigerGraphToolName.UPSERT_VECTORS:
                            return await upsert_vectors(**arguments)
                        case TigerGraphToolName.LOAD_VECTORS_FROM_CSV:
                            return await load_vectors_from_csv(**arguments)
                        case TigerGraphToolName.LOAD_VECTORS_FROM_JSON:
                            return await load_vectors_from_json(**arguments)
                        case TigerGraphToolName.SEARCH_TOP_K_SIMILARITY:
                            return await search_top_k_similarity(**arguments)
                        case TigerGraphToolName.FETCH_VECTOR:
                            return await fetch_vector(**arguments)
                        # Data Source operations
                        case TigerGraphToolName.CREATE_DATA_SOURCE:
                            return await create_data_source(**arguments)
                        case TigerGraphToolName.UPDATE_DATA_SOURCE:
                            return await update_data_source(**arguments)
                        case TigerGraphToolName.GET_DATA_SOURCE:
                            return await get_data_source(**arguments)
                        case TigerGraphToolName.DROP_DATA_SOURCE:
                            return await drop_data_source(**arguments)
                        case TigerGraphToolName.GET_ALL_DATA_SOURCES:
                            return await get_all_data_sources(**arguments)
                        case TigerGraphToolName.DROP_ALL_DATA_SOURCES:
                            return await drop_all_data_sources(**arguments)
                        case TigerGraphToolName.PREVIEW_SAMPLE_DATA:
                            return await preview_sample_data(**arguments)
                        # Discovery operations
                        case TigerGraphToolName.DISCOVER_TOOLS:
                            return await discover_tools(**arguments)
                        case TigerGraphToolName.GET_WORKFLOW:
                            return await get_workflow(**arguments)
                        case TigerGraphToolName.GET_TOOL_INFO:
                            return await get_tool_info(**arguments)
                        case _:
                            raise ValueError(f"Unknown tool: {name}")
                except TigerGraphException as e:
                    logger.exception("Error in tool execution")
                    return format_error(
                        operation=name,
                        error=e,
                        context={"arguments": arguments},
                    )
                except Exception as e:
                    logger.exception("Error in tool execution")
                    return format_error(
                        operation=name,
                        error=e,
                        context={"arguments": arguments},
                    )


async def serve(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    mount_path: str = "/mcp",
) -> None:
    """Serve the MCP server over the chosen transport.

    Args:
        transport: One of ``"stdio"`` (default), ``"streamable-http"``, ``"sse"``.
        host: Bind address for HTTP transports. Ignored for stdio.
        port: TCP port for HTTP transports. Ignored for stdio.
        mount_path: URL path mount point for HTTP transports.

    For HTTP/SSE transports each MCP session gets its own connection pool
    (via :class:`SessionConnectionManager`); for stdio the process-global
    :class:`ConnectionManager` is used.
    """
    if transport == "stdio":
        await _serve_stdio()
    elif transport in ("streamable-http", "sse"):
        await _serve_http(transport, host, port, mount_path)
    else:
        raise ValueError(
            f"Unknown transport: {transport!r}. "
            "Expected 'stdio', 'streamable-http', or 'sse'."
        )


async def _serve_stdio() -> None:
    server = MCPServer(multi_session=False)
    options = server.server.create_initialization_options()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.server.run(
                read_stream, write_stream, options, raise_exceptions=True
            )
    finally:
        await ConnectionManager.close_all()


async def _serve_http(
    transport: str, host: str, port: int, mount_path: str
) -> None:
    """Serve over streamable-http or SSE using Starlette + uvicorn.

    Each MCP session gets its own :class:`SessionConnectionManager`. Every
    request must carry the user's TigerGraph credentials in ``X-TG-*``
    headers; ``CredentialHeadersMiddleware`` validates them against
    TigerGraph and 401s any request that fails, so MCP clients see a
    connection failure as soon as they try their first operation.

    Transport-level authentication (who can reach this URL at all) is
    intentionally out of scope and left to a reverse proxy / ingress.
    """
    import uvicorn
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Mount

    from .http_middleware import CredentialHeadersMiddleware

    server = MCPServer(multi_session=True)
    middleware = [Middleware(CredentialHeadersMiddleware)]

    if transport == "streamable-http":
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

        session_manager = StreamableHTTPSessionManager(app=server.server)

        @contextlib.asynccontextmanager
        async def lifespan(app):
            async with session_manager.run():
                try:
                    yield
                finally:
                    await server.aclose_session_managers()

        starlette_app = Starlette(
            routes=[Mount(mount_path, app=session_manager.handle_request)],
            middleware=middleware,
            lifespan=lifespan,
        )
    else:
        # SSE — legacy transport, deprecated by the MCP spec in favor of
        # streamable-http. Wired for completeness.
        from mcp.server.sse import SseServerTransport
        from starlette.responses import Response
        from starlette.routing import Route

        sse_transport = SseServerTransport(f"{mount_path}/messages")

        async def handle_sse(request):
            async with sse_transport.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                read_stream, write_stream = streams
                await server.server.run(
                    read_stream,
                    write_stream,
                    server.server.create_initialization_options(),
                )
            return Response()

        @contextlib.asynccontextmanager
        async def lifespan(app):
            try:
                yield
            finally:
                await server.aclose_session_managers()

        starlette_app = Starlette(
            routes=[
                Route(f"{mount_path}/sse", endpoint=handle_sse),
                Mount(f"{mount_path}/messages", app=sse_transport.handle_post_message),
            ],
            middleware=middleware,
            lifespan=lifespan,
        )

    config = uvicorn.Config(
        starlette_app, host=host, port=port, log_level="info"
    )
    await uvicorn.Server(config).serve()

