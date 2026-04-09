# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
