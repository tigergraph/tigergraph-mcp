#!/usr/bin/env python3
"""Fail if the MCP server is declared inline in plugin.json.

Claude Code 2.1.282 accepts an inline ``mcpServers`` key in plugin.json --
``claude plugin validate --strict`` passes and the plugin installs -- but the
server never registers and ``claude plugin details`` reports no MCP servers.
Declaring it in ``.mcp.json`` at the plugin root works.

The failure is silent and validation does not catch it, so the obvious cleanup
of folding the two files into one would ship a plugin that does nothing. This
check makes that mistake loud.
"""

from __future__ import annotations

import json
import pathlib
import sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "tigergraph"


def main() -> int:
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    mcp_file = PLUGIN / ".mcp.json"

    if "mcpServers" in manifest:
        print(
            "plugin.json declares mcpServers inline. Claude Code validates this "
            "but never registers the server; move it to .mcp.json.",
            file=sys.stderr,
        )
        return 1

    if not mcp_file.exists():
        print(f"missing {mcp_file.relative_to(PLUGIN.parent.parent)}", file=sys.stderr)
        return 1

    servers = json.loads(mcp_file.read_text()).get("mcpServers")
    if not servers:
        print(".mcp.json declares no servers under 'mcpServers'", file=sys.stderr)
        return 1

    print(f"  server declared in .mcp.json: {', '.join(servers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
