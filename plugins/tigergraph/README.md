# TigerGraph

Connect Claude to any TigerGraph deployment — self-managed, on-premise, or a TigerGraph
Savanna instance — using your own host and credentials. Claude can explore and evolve the
graph schema, read and write vertices and edges, run GSQL and Cypher queries, install and
run stored queries, load data from files and data sources, and search vector embeddings.

The plugin runs the open-source [tigergraph-mcp](https://github.com/tigergraph/tigergraph-mcp)
server on your machine. It works in Claude Code.

## Requirements

- [uv](https://docs.astral.sh/uv/) on your `PATH`. The plugin starts the server with `uvx`,
  which also provides a suitable Python if one isn't installed.
- A TigerGraph instance you can reach from your machine, and an account on it.

## Install

```bash
claude plugin marketplace add tigergraph/tigergraph-mcp
claude plugin install tigergraph@tigergraph
```

## Configuration

At install time, Claude Code asks for:

| Option | Required | Description |
|---|---|---|
| TigerGraph host | Yes | Host URL of the instance, for example `https://mycompany.i.tgcloud.io` |
| Username | No | Account to connect as. Defaults to `tigergraph` |
| Password | No | Password for that account |
| Default graph | No | Graph to use when a request doesn't name one |
| API token | No | Used instead of the password when set |
| Tools to offer | No | Limits which tools Claude can use, such as `read-only`. Empty offers all of them |

The password and API token are kept in secure storage, not in a settings file. To change
any option later, open `/plugin`, select **TigerGraph (Self-Managed MCP)** on the
**Installed** tab, and choose **Configure options**.

## What the plugin runs and sends

- **Download:** when it starts, `uvx` downloads the pinned `tigergraph-mcp` package and its
  dependencies from PyPI, then caches them.
- **Network:** the server connects only to the TigerGraph host you configure. It sends that
  host your credentials and the requests Claude makes.
- **Local files:** the tools that load data or vectors from a file read the file path Claude
  gives them and send its contents to your TigerGraph host.
- **Environment:** the server also reads a `.env` file from the working directory or a parent
  directory, if one exists. Options entered at install take precedence over it.
- **No telemetry:** the plugin doesn't collect usage data or send anything to TigerGraph or
  other third parties. The query-generation tools, which call an LLM provider, aren't
  available in the plugin.

## Permissions

In permission rules, a skill's `allowed-tools`, or a hook matcher, the plugin's server is
named `plugin:tigergraph:tigergraph`.

## Documentation and support

- Full documentation: <https://github.com/tigergraph/tigergraph-mcp#readme>
- Issues: <https://github.com/tigergraph/tigergraph-mcp/issues>

## License

Apache-2.0
