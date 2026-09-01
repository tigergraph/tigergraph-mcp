# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Serving a subset of the tools.

The full tool list is large, and an agent pays for every tool it is given on
every request. A deployment can narrow the list to the tools its agents
actually need, or to the ones that only read.

A selector is a comma-separated list of:

- a category — ``schema``, ``data``, ``query``, ``vector``, ``loading``,
  ``utility``, ``discovery``
- ``read-only`` or ``destructive``, resolved from the behavioural hints
- an exact tool name, with or without the ``tigergraph__`` prefix

An unknown selector is an error rather than an empty result, so a typo is
reported at startup instead of quietly serving three tools.
"""

import contextvars
import os
from difflib import get_close_matches
from typing import Iterable, List, Optional, Sequence, Set

from mcp.types import Tool

from .tool_annotations import DESTRUCTIVE, READ_ONLY
from .tool_metadata import TOOL_METADATA

CAPABILITY_SELECTORS = ("read-only", "destructive")


def _categories() -> Set[str]:
    return {m.category.value for m in TOOL_METADATA.values()}


def _tools_in_category(category: str) -> Set[str]:
    return {n for n, m in TOOL_METADATA.items() if m.category.value == category}


def known_selectors() -> List[str]:
    """Every selector this server accepts, for error messages."""
    return sorted(_categories()) + list(CAPABILITY_SELECTORS)


def parse_selector(spec: str, available: Iterable[str]) -> Set[str]:
    """Expand a selector string into the tool names it names.

    Raises:
        ValueError: on a token that matches no category, capability or tool.
    """
    available = set(available)
    selected: Set[str] = set()

    for raw in spec.split(","):
        token = raw.strip().lower()
        if not token:
            continue

        if token in _categories():
            selected |= _tools_in_category(token)
        elif token == "read-only":
            selected |= set(READ_ONLY)
        elif token == "destructive":
            selected |= set(DESTRUCTIVE)
        else:
            qualified = token if token.startswith("tigergraph__") else f"tigergraph__{token}"
            if qualified in available:
                selected.add(qualified)
            else:
                choices = known_selectors() + [
                    n.replace("tigergraph__", "") for n in available
                ]
                close = get_close_matches(token, choices, n=3, cutoff=0.6)
                hint = f" Did you mean: {', '.join(close)}?" if close else ""
                raise ValueError(
                    f"Unknown tool selector '{raw.strip()}'. Use a category "
                    f"({', '.join(sorted(_categories()))}), 'read-only', "
                    f"'destructive', or a tool name.{hint}"
                )

    return selected & available


def select(
    tools: Sequence[Tool],
    allowed: Optional[str] = None,
    blocked: Optional[str] = None,
) -> List[Tool]:
    """Narrow ``tools`` by an allow selector, then remove a blocked selector."""
    names = {t.name for t in tools}

    keep = parse_selector(allowed, names) if allowed else set(names)
    if blocked:
        keep -= parse_selector(blocked, names)

    return [t for t in tools if t.name in keep]


# ---------------------------------------------------------------------------
# Configured selection
#
# Set once from the command line or the environment. HTTP sessions may narrow
# it further per request, never widen it, so a client cannot reach a tool the
# deployment withheld.
# ---------------------------------------------------------------------------

_allowed: Optional[str] = None
_blocked: Optional[str] = None

_session_allowed: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "tg_mcp_session_allowed", default=None
)


def configure(allowed: Optional[str] = None, blocked: Optional[str] = None) -> None:
    """Set the server-wide selection, falling back to the environment."""
    global _allowed, _blocked
    _allowed = allowed or os.getenv("TG_ALLOWED_TOOLS") or None
    _blocked = blocked or os.getenv("TG_BLOCKED_TOOLS") or None


def configured() -> tuple:
    return _allowed, _blocked


def set_session_selector(spec: Optional[str]):
    """Narrow the current request further. Returns a contextvars token."""
    return _session_allowed.set(spec)


def reset_session_selector(token) -> None:
    _session_allowed.reset(token)


def apply(tools: Sequence[Tool]) -> List[Tool]:
    """Apply the configured selection, and any narrowing for this request."""
    result = select(tools, _allowed, _blocked)

    session_spec = _session_allowed.get()
    if session_spec:
        # Narrowing only: intersect with what the deployment already allows.
        result = select(result, session_spec, None)
    return result
