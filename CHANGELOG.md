# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.3] - 2026-09-01

### Added

- **Serve a subset of the tools** — `--allowed-tools` and `--blocked-tools`, or `TG_ALLOWED_TOOLS` and `TG_BLOCKED_TOOLS`, narrow the tool list a client receives. A selector is a comma-separated list of categories (`schema`, `data`, `query`, `vector`, `loading`, `utility`, `discovery`), the capabilities `read-only` or `destructive`, or individual tool names. An unrecognised selector is reported at startup rather than silently serving a short list. Serving only the tools that read cuts the tool payload an agent carries by well over half.
- **HTTP sessions can narrow the list further** — an `X-TG-Tools` header restricts a single session to a subset of what the deployment already serves. It can never widen it, so a client cannot reach a tool the deployment withheld.
- **Every tool now declares what it does** — the MCP behavioural hints `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint` are attached to all tools, so a client can run reads without prompting and ask before anything that removes data. Tools that execute caller-supplied query text are marked destructive, since what they do depends on the text.

## [1.0.2] - 2026-08-26

### Added

- **HTTP/SSE transport for multi-user deployments** — new `--transport stdio|streamable-http|sse` flag plus `--host`, `--port`, and `--mount-path`. One process serves many users, each MCP session owning its own TigerGraph connections so concurrent users stay isolated. Requires `uvicorn` and `starlette`.
- **Per-request credentials for HTTP/SSE** — clients send `X-TG-*` headers. The server reads the same env file and `TG_*` / `<PROFILE>_TG_*` profiles as stdio for topology and optional credentials; `X-TG-Profile` selects a profile and the other headers override its values for that session. Credentials are checked against TigerGraph when a session's connection is established, and a rejected credential never establishes a session. Failures are reported by kind: `400` when the request does not describe a reachable server, `401` for missing or rejected credentials, `502` when the server cannot be reached. `TG_HTTP_ALLOWED_PROFILES`, `TG_HTTP_VALIDATE_TIMEOUT`, and `TG_HTTP_SESSION_IDLE_TIMEOUT` tune which profiles may be named, how long the reachability check waits, and when idle session pools are reclaimed.
- **`authenticate` tool** — re-points one of the session's connections at a TigerGraph instance from inside an MCP conversation. Omitting `profile` replaces the default profile's connection; naming one replaces only that profile, leaving the session's others untouched. The credentials are checked against TigerGraph before the swap, so a bad one is reported immediately and the existing connection is left in place. HTTP/SSE only.
- **`update_query_description` / `get_query_description` tools** — attach and read human-readable descriptions for installed queries and their parameters (TigerGraph 4.0+).
- **`get_data_source_types` tool** — lists every supported data source type with its required and optional configuration keys and a worked example, so the configuration shape does not have to be guessed.
- **Data warehouse and lakehouse data sources** — `create_data_source` now accepts `snowflake`, `bigquery`, `postgresql`, `iceberg`, `kafka_v2`, and `mirrormaker` alongside the object store and Kafka types. Each takes a different configuration shape, so a rejected request comes back with the keys that type needs and an example.
- **Loading jobs can read from a data source query** — a file entry may name a `data_source` and a `query` instead of a `file_path`, loading the result of a SQL query against a warehouse.
- **`examples/multi_user_backend/` reference** — FastAPI service demonstrating one `tigergraph-mcp` subprocess and one agent per logged-in user, with an idle-session sweeper, per-user request lock, and session caps.

### Changed

- **Data source configuration keys now match what TigerGraph requires.** Several documented keys were wrong: Google Cloud Storage keys are dot-separated (`project.id`, `client.email`, `private.key.id`, `private.key`), Azure Blob takes `client.id` / `client.secret` / `tenant.id`, and Kafka takes `bootstrap.servers`. S3 requires both `access.key` and `secret.key`, including for public buckets; PostgreSQL's `port` and `db.name` are optional.
- **Data source credentials are masked in tool responses.** Reads previously returned whatever the server sent, which on TigerGraph 4.x includes stored secrets.
- **`TG_DEFAULT_PROFILE` names the default profile**, with `TG_PROFILE` kept as an alias. Omitting a tool's `profile` argument and passing `"default"` now resolve identically — to that profile, or to the unprefixed `TG_*` variables when it is unset.
- **Python 3.13 and 3.14 are supported and tested.** The minimum stays at 3.10.
- **Both the 1.x and 2.x MCP SDKs are supported.** The README's HTTP client examples now cover both, whose client APIs differ. The 2.0 SDK replaced the handler decorators with constructor callbacks; the server detects which API the installed SDK provides, so upgrading the SDK no longer breaks startup.

### Fixed

- **`azure_blob` reached the server as an unsupported type**, so creating an Azure Blob data source always failed. TigerGraph's type is `abs`, and `azure_blob` is now translated to it.
- A `type` key inside `config` no longer overrides the `data_source_type` argument when creating a data source.
- The end-to-end workflow test skips itself when no TigerGraph is reachable instead of failing, so the test suite passes on a machine or CI runner without a database.
- `list_connections` lists only profiles a call can actually select, and it and `show_connection` describe the calling session rather than the server process. In HTTP mode they reported the server's own state, so an agent could not discover which profiles it may use, and an open connection was shown with its configured values instead of the credentials the request supplied. They now also report which profile is the default and which are connected.
- `authenticate` registers its credentials under whichever profile is the default, so a tool call that omits `profile` uses them. It previously always wrote to a profile literally named `default`, which had no effect when `TG_DEFAULT_PROFILE` named another one.

### Removed

- `local` is no longer listed as a data source type. TigerGraph does not accept it — local files are loaded with `run_loading_job_with_file`. Passing it still reaches the server, which reports the types it supports.

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
