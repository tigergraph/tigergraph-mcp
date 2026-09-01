# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Behavioural hints attached to every tool.

MCP lets a server tell clients what a tool *does* to its environment, which is
how an editor decides whether to run something silently or ask first. The
classification lives here rather than beside each tool definition so the whole
picture can be reviewed at once — a tool landing in the wrong set is a safety
question, not a cosmetic one.

The same sets back the ``read-only`` and ``destructive`` selectors used by tool
filtering, so a deployment can serve only the tools that read.
"""

from typing import Dict, Iterable, List

from mcp.types import Tool, ToolAnnotations

# Tools that only observe: they never change the database, the session, or
# anything else. Safe for a client to run without asking.
READ_ONLY = frozenset({
    # data
    "tigergraph__get_edge",
    "tigergraph__get_edges",
    "tigergraph__get_node",
    "tigergraph__get_node_edges",
    "tigergraph__get_nodes",
    "tigergraph__has_edge",
    "tigergraph__has_node",
    # discovery (these do not touch TigerGraph at all)
    "tigergraph__discover_tools",
    "tigergraph__get_tool_info",
    "tigergraph__get_workflow",
    # loading
    "tigergraph__get_all_data_sources",
    "tigergraph__get_data_source",
    "tigergraph__get_data_source_types",
    "tigergraph__get_loading_job_status",
    "tigergraph__get_loading_jobs",
    "tigergraph__preview_sample_data",
    # query
    "tigergraph__generate_cypher",
    "tigergraph__generate_gsql",
    "tigergraph__get_neighbors",
    "tigergraph__get_query_description",
    "tigergraph__get_query_metadata",
    "tigergraph__is_query_installed",
    "tigergraph__show_query",
    # schema
    "tigergraph__get_global_schema",
    "tigergraph__get_graph_schema",
    "tigergraph__list_graphs",
    "tigergraph__show_graph_details",
    "tigergraph__validate_schema_names",
    # utility
    "tigergraph__get_edge_count",
    "tigergraph__get_node_degree",
    "tigergraph__get_vertex_count",
    "tigergraph__list_connections",
    "tigergraph__show_connection",
    # vector
    "tigergraph__fetch_vector",
    "tigergraph__get_vector_index_status",
    "tigergraph__list_vector_attributes",
    "tigergraph__search_top_k_similarity",
})

# Tools that may remove or overwrite something. Everything that drops, deletes
# or clears, plus the three that execute caller-supplied query text: what those
# do depends entirely on the text, so they are classified by what they *may* do.
DESTRUCTIVE = frozenset({
    "tigergraph__clear_graph_data",
    "tigergraph__delete_edge",
    "tigergraph__delete_edges",
    "tigergraph__delete_node",
    "tigergraph__delete_nodes",
    "tigergraph__drop_all_data_sources",
    "tigergraph__drop_data_source",
    "tigergraph__drop_graph",
    "tigergraph__drop_loading_job",
    "tigergraph__drop_query",
    "tigergraph__drop_vector_attribute",
    "tigergraph__update_schema",      # may remove attributes or types
    "tigergraph__gsql",               # arbitrary GSQL, including DDL
    "tigergraph__run_query",          # arbitrary query text
    "tigergraph__run_installed_query",
})

# Running twice leaves the same state as running once.
IDEMPOTENT = frozenset({
    "tigergraph__add_node",
    "tigergraph__add_nodes",
    "tigergraph__add_edge",
    "tigergraph__add_edges",
    "tigergraph__upsert_vectors",
    "tigergraph__authenticate",
    "tigergraph__update_data_source",
    "tigergraph__update_query_description",
    "tigergraph__clear_graph_data",
    "tigergraph__drop_graph",
    "tigergraph__drop_query",
    "tigergraph__drop_data_source",
    "tigergraph__drop_all_data_sources",
    "tigergraph__drop_loading_job",
    "tigergraph__drop_vector_attribute",
    "tigergraph__delete_node",
    "tigergraph__delete_nodes",
    "tigergraph__delete_edge",
    "tigergraph__delete_edges",
}) | READ_ONLY

# Reaches something beyond the configured TigerGraph instance.
OPEN_WORLD = frozenset({
    "tigergraph__generate_cypher",   # calls an LLM provider
    "tigergraph__generate_gsql",
})

# Short labels for a client's approval prompt, where the full description is
# far too long to show. Only where the generated fallback reads badly.
TITLES: Dict[str, str] = {
    "tigergraph__gsql": "Run GSQL command",
    "tigergraph__run_query": "Run interpreted query",
    "tigergraph__run_installed_query": "Run installed query",
    "tigergraph__generate_gsql": "Generate GSQL (LLM)",
    "tigergraph__generate_cypher": "Generate Cypher (LLM)",
}


def _title(name: str) -> str:
    if name in TITLES:
        return TITLES[name]
    return name.replace("tigergraph__", "").replace("_", " ").capitalize()


def annotations_for(name: str) -> ToolAnnotations:
    """Behavioural hints for one tool."""
    read_only = name in READ_ONLY
    return ToolAnnotations(
        title=_title(name),
        readOnlyHint=read_only,
        # A read-only tool changes nothing, so it cannot be destructive.
        destructiveHint=False if read_only else name in DESTRUCTIVE,
        idempotentHint=name in IDEMPOTENT,
        openWorldHint=name in OPEN_WORLD,
    )


def hints(name: str) -> Dict[str, object]:
    """The hints for one tool, keyed as they appear on the wire.

    MCP 1.x names these fields in camelCase and 2.x in snake_case with
    camelCase aliases, so read them through the alias rather than as
    attributes.
    """
    return annotations_for(name).model_dump(by_alias=True, exclude_none=True)


def annotate(tools: Iterable[Tool]) -> List[Tool]:
    """Return copies of ``tools`` carrying their behavioural hints."""
    return [t.model_copy(update={"annotations": annotations_for(t.name)}) for t in tools]
