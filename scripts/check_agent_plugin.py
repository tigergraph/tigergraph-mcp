#!/usr/bin/env python3
"""Fail when the portable Agent Plugins manifest drifts from the Claude Code one.

Claude Code reads .claude-plugin/plugin.json and .mcp.json; Codex, Copilot CLI and
other Agent Plugins clients read plugin.json and mcp.json at the plugin root. The
two pairs must describe the same plugin and start the same server. mcp.json must
not pass connection settings: the ${user_config.*} placeholders are Claude Code's
own, and other clients would hand them to the server as literal text.
"""

from __future__ import annotations

import json
import pathlib
import sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "tigergraph"
SHARED = ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")


def main() -> int:
    claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    portable = json.loads((PLUGIN / "plugin.json").read_text())
    claude_server = json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]["tigergraph"]
    portable_server = json.loads((PLUGIN / "mcp.json").read_text())["mcpServers"]["tigergraph"]

    errors = [f"plugin.json {k!r} differs from .claude-plugin/plugin.json"
              for k in SHARED if portable.get(k) != claude.get(k)]
    for k in ("command", "args"):
        if portable_server.get(k) != claude_server.get(k):
            errors.append(f"mcp.json {k!r} differs from .mcp.json")
    if "env" in portable_server:
        errors.append("mcp.json sets env; connection settings come from the user's .env instead")

    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        return 1
    print("  plugin.json and mcp.json match the Claude Code manifests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
