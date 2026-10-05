# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Helpers for embedding caller-supplied values in generated GSQL text.

Tools that build an interpreted query from their arguments must never paste a
value into the text verbatim: a vertex ID containing a double quote breaks the
query, and anything after it becomes GSQL. Values go in as escaped string
literals; type names, which GSQL cannot take as parameters, are checked against
the identifier grammar instead.
"""

import re
from typing import Any, List

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def gsql_string(value: Any) -> str:
    """Return ``value`` as a double-quoted GSQL string literal."""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def gsql_identifier(name: str, what: str) -> str:
    """Return ``name`` unchanged if it is a valid GSQL identifier, else raise."""
    if not isinstance(name, str) or not _IDENTIFIER.match(name):
        raise ValueError(
            f"Invalid {what} '{name}': must start with a letter or underscore "
            "and contain only letters, digits, and underscores."
        )
    return name


def gsql_identifier_list(names: str, what: str) -> List[str]:
    """Split a ``|``-separated list of type names and validate each one."""
    return [gsql_identifier(n.strip(), what) for n in names.split("|")]


def positive_int(value: Any, what: str) -> int:
    """Return ``value`` as a positive int, else raise."""
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Invalid {what} '{value}': must be a positive integer.")
    return value
