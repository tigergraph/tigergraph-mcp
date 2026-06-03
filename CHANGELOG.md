# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-06-02

### Added

- **HTTP/SSE transport for multi-user deployments** — new `--transport stdio|streamable-http|sse` CLI flag plus `--host`, `--port`, and `--mount-path` options. HTTP modes serve many users from one process; each MCP session owns its own TigerGraph connection so concurrent users stay isolated.
- **Header-based authentication for HTTP/SSE** — clients pass `X-TG-Host` plus credentials (`X-TG-Api-Token`, `X-TG-Jwt-Token`, or `X-TG-Username` + `X-TG-Password`) on every request. The MCP server validates against TigerGraph and returns `401 Unauthorized` on failure, so the MCP client sees a connection failure immediately rather than a tool failure.
- **`authenticate` tool** — registers (or replaces) the active session's TigerGraph credentials from inside an MCP conversation. Useful for switching to a different TigerGraph instance or user mid-session.
- **`update_query_description` / `get_query_description` tools** — wrap pyTigerGraph's `updateQueryDescription` / `getQueryDescription` (TigerGraph 4.0+) so agents can attach and read human-readable descriptions for installed queries and their parameters.
- **`examples/multi_user_backend/` reference** — FastAPI service that demonstrates the "one tigergraph-mcp subprocess + one agent per logged-in user" pattern with idle-session sweeper, per-user request lock, and session caps.

## [1.0.1] - 2026-05-19

### Added

- **Conda installation** — `tigergraph-mcp` is now available on Anaconda.org under the `tigergraph` channel. Install with `conda install -c tigergraph tigergraph-mcp`.
- **Per-call profile routing docs** — added a README section showing how an agent can route individual tool calls to different TigerGraph environments via the `profile` argument, including a sample system prompt.

### Changed

- **Minimum `pyTigerGraph` version raised to `2.0.4`** (was `2.0.2`).

### Fixed

- Auth documentation no longer incorrectly states that a token can be obtained from the TigerGraph Admin Portal.

## [1.0.0] - 2026-04-08

### Added

- Initial release of `tigergraph-mcp` as a standalone MCP server package, using `pyTigerGraph` as the underlying TigerGraph client library.
- **`update_schema` tool** — apply incremental schema changes (add/drop vertex types, edge types, or individual attributes) for both local and global scopes.
- **`validate_schema_names` tool** — pre-validate vertex/edge/attribute names against GSQL reserved keywords and naming conflict rules before creating or updating a graph.
- **Auto token generation** — `ConnectionManager` now automatically generates an auth token when only username/password are provided and REST++ authentication is enabled, removing the need to manually configure `TG_API_TOKEN` or `TG_SECRET`.
- **Environment variable aliases** — `TG_TOKEN` is now accepted as an alias for `TG_API_TOKEN`, and `TG_GSQL_PORT` for `TG_GS_PORT`.
- **Expanded tool metadata** — added `ToolMetadata` entries for all previously unregistered tools (vector operations, loading jobs, data sources, discovery, connection management, etc.).
- **Conda build support** — `build.sh` now supports `--conda-build`, `--conda-upload`, `--conda-all`, and `--conda-forge-test` for building and validating conda packages.
- **Conda recipe** — added `tigergraph-mcp-recipe/recipe/meta.yaml` for conda-forge packaging.
- **Consistent error formatting** — all server-level exception handlers (`TigerGraphException` and generic `Exception`) now use `format_error()`, producing structured JSON output with operation name, full error message, and original arguments.
- **Error summaries include context** — `format_error()` summary now includes a truncated version of the actual error message (up to 200 chars) instead of just "Failed to \<operation\>".
