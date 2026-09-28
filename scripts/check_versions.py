#!/usr/bin/env python3
"""Fail when the version disagrees anywhere it is declared.

The version appears in six places across three release channels — PyPI, conda,
and the Claude Code plugin — and a mismatch is only discovered by a user whose
install resolves to a package that does not exist. Cheaper to catch here.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def _search(pattern: str, path: str) -> str:
    m = re.search(pattern, _read(path), re.M)
    if not m:
        raise SystemExit(f"{path}: no version found for {pattern!r}")
    return m.group(1)


def _plugin() -> dict:
    return json.loads(_read("plugins/tigergraph/.claude-plugin/plugin.json"))


def _mcp_server_args() -> list:
    servers = json.loads(_read("plugins/tigergraph/.mcp.json"))["mcpServers"]
    return servers["tigergraph"]["args"]


def _server_json() -> dict:
    return json.loads(_read("server.json"))


def versions() -> dict:
    args = _mcp_server_args()
    pinned = [a.split("@", 1)[1] for a in args if a.startswith("tigergraph-mcp@")]
    sj = _server_json()
    return {
        "pyproject.toml": _search(r'^version = "([^"]+)"', "pyproject.toml"),
        "recipe/meta.yaml": _search(
            r'{% set version = "([^"]+)" %}', "tigergraph-mcp-recipe/recipe/meta.yaml"
        ),
        "__init__.py fallback": _search(
            r'__version__ = "([^"]+)"', "tigergraph_mcp/__init__.py"
        ),
        "plugin.json version": _plugin()["version"],
        ".mcp.json uvx pin": pinned[0] if pinned else "<missing>",
        "server.json version": sj["version"],
        "server.json package": sj["packages"][0]["version"],
    }


def main() -> int:
    found = versions()
    distinct = set(found.values())
    for where, value in found.items():
        print(f"  {where:24} {value}")
    if len(distinct) != 1:
        print(f"\nVersions disagree: {sorted(distinct)}", file=sys.stderr)
        return 1
    print(f"\nAll agree on {distinct.pop()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
