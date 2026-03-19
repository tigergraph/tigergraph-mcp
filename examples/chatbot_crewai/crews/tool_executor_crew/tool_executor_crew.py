"""General-purpose tool executor crew.

Dynamically selects the right agent and tool based on the tool name prefix.
Tools are grouped by domain (schema, node, edge, query, statistics, vector,
data source, gsql, loading job).
"""

from functools import cached_property
from typing import Any, Dict, List, Optional

from crewai import Agent, Crew, Task
from crewai.project import CrewBase, agent, task


TOOL_DOMAIN_MAP = {
    "tigergraph__get_global_schema": "schema",
    "tigergraph__list_graphs": "schema",
    "tigergraph__drop_graph": "schema",
    "tigergraph__clear_graph_data": "schema",
    "tigergraph__get_graph_schema": "schema",
    "tigergraph__show_graph_details": "schema",
    "tigergraph__add_node": "node",
    "tigergraph__add_nodes": "node",
    "tigergraph__get_node": "node",
    "tigergraph__get_nodes": "node",
    "tigergraph__delete_node": "node",
    "tigergraph__delete_nodes": "node",
    "tigergraph__has_node": "node",
    "tigergraph__get_node_edges": "node",
    "tigergraph__add_edge": "edge",
    "tigergraph__add_edges": "edge",
    "tigergraph__get_edge": "edge",
    "tigergraph__get_edges": "edge",
    "tigergraph__delete_edge": "edge",
    "tigergraph__delete_edges": "edge",
    "tigergraph__has_edge": "edge",
    "tigergraph__run_query": "query",
    "tigergraph__run_installed_query": "query",
    "tigergraph__install_query": "query",
    "tigergraph__drop_query": "query",
    "tigergraph__show_query": "query",
    "tigergraph__get_query_metadata": "query",
    "tigergraph__is_query_installed": "query",
    "tigergraph__get_neighbors": "query",
    "tigergraph__get_vertex_count": "statistics",
    "tigergraph__get_edge_count": "statistics",
    "tigergraph__get_node_degree": "statistics",
    "tigergraph__gsql": "gsql",
    "tigergraph__generate_gsql": "gsql",
    "tigergraph__generate_cypher": "gsql",
    "tigergraph__add_vector_attribute": "vector",
    "tigergraph__drop_vector_attribute": "vector",
    "tigergraph__list_vector_attributes": "vector",
    "tigergraph__get_vector_index_status": "vector",
    "tigergraph__upsert_vectors": "vector",
    "tigergraph__load_vectors_from_csv": "vector",
    "tigergraph__load_vectors_from_json": "vector",
    "tigergraph__search_top_k_similarity": "vector",
    "tigergraph__fetch_vector": "vector",
    "tigergraph__create_data_source": "datasource",
    "tigergraph__update_data_source": "datasource",
    "tigergraph__get_data_source": "datasource",
    "tigergraph__drop_data_source": "datasource",
    "tigergraph__get_all_data_sources": "datasource",
    "tigergraph__drop_all_data_sources": "datasource",
    "tigergraph__preview_sample_data": "datasource",
    "tigergraph__run_loading_job_with_file": "loading",
    "tigergraph__run_loading_job_with_data": "loading",
    "tigergraph__get_loading_jobs": "loading",
    "tigergraph__get_loading_job_status": "loading",
    "tigergraph__drop_loading_job": "loading",
    "tigergraph__discover_tools": "discovery",
    "tigergraph__get_workflow": "discovery",
    "tigergraph__get_tool_info": "discovery",
}

DOMAIN_AGENT_CONFIG = {
    "schema": {
        "role": "Schema Administrator",
        "goal": "Execute schema and graph management operations on TigerGraph.",
        "backstory": "You manage TigerGraph graph schemas — listing, inspecting, and dropping graphs.",
    },
    "node": {
        "role": "Node Operations Agent",
        "goal": "Execute vertex (node) operations on TigerGraph.",
        "backstory": "You handle all vertex operations — adding, getting, deleting, and checking nodes.",
    },
    "edge": {
        "role": "Edge Operations Agent",
        "goal": "Execute edge operations on TigerGraph.",
        "backstory": "You handle all edge operations — adding, getting, deleting, and checking edges.",
    },
    "query": {
        "role": "Query Agent",
        "goal": "Execute query operations on TigerGraph.",
        "backstory": "You run, install, drop, and inspect GSQL queries.",
    },
    "statistics": {
        "role": "Statistics Agent",
        "goal": "Retrieve graph statistics from TigerGraph.",
        "backstory": "You retrieve vertex counts, edge counts, and node degrees.",
    },
    "gsql": {
        "role": "GSQL Agent",
        "goal": "Execute raw GSQL commands or generate queries from natural language.",
        "backstory": "You execute GSQL commands and generate GSQL/Cypher from natural language descriptions.",
    },
    "vector": {
        "role": "Vector Operations Agent",
        "goal": "Execute vector schema and data operations on TigerGraph.",
        "backstory": "You manage vector attributes, indexes, and perform similarity searches.",
    },
    "datasource": {
        "role": "Data Source Agent",
        "goal": "Manage external data sources and preview sample data.",
        "backstory": "You create, update, inspect, and drop data sources, and preview file contents.",
    },
    "loading": {
        "role": "Loading Job Agent",
        "goal": "Manage and run loading jobs on TigerGraph.",
        "backstory": "You run loading jobs with files or inline data, check status, and manage job lifecycle.",
    },
    "discovery": {
        "role": "Tool Discovery Agent",
        "goal": "Help users discover available tools and workflows.",
        "backstory": "You search for tools, suggest workflows, and provide tool information.",
    },
}


@CrewBase
class ToolExecutorCrews:
    def __init__(
        self,
        tools: Dict[str, Any],
        verbose: int = 0,
        llm: str = "openai/gpt-4.1-mini-2025-04-14",
    ):
        self._tools = tools
        self.verbose = verbose
        self.llm = llm

    def _get_tools_for_domain(self, domain: str) -> List:
        return [
            self._tools[name]
            for name, d in TOOL_DOMAIN_MAP.items()
            if d == domain and name in self._tools
        ]

    def get_crew_for_tool(self, tool_name: str) -> Optional[Crew]:
        domain = TOOL_DOMAIN_MAP.get(tool_name)
        if not domain:
            return None

        agent_cfg = DOMAIN_AGENT_CONFIG.get(domain)
        if not agent_cfg:
            return None

        domain_tools = self._get_tools_for_domain(domain)
        schema_tool = self._tools.get("tigergraph__get_graph_schema")
        if schema_tool and schema_tool not in domain_tools:
            domain_tools.append(schema_tool)

        ag = Agent(
            role=agent_cfg["role"],
            goal=agent_cfg["goal"],
            backstory=agent_cfg["backstory"],
            tools=domain_tools,
            llm=self.llm,
        )

        t = Task(
            description=(
                "Execute the following command using the appropriate TigerGraph tool.\n\n"
                "Command: {command}\n\n"
                "Context: {conversation_history}\n\n"
                "Call the right tool with the correct parameters. "
                "Report the result clearly and concisely."
            ),
            expected_output="The result of the tool call.",
            agent=ag,
        )

        return Crew(
            agents=[ag],
            tasks=[t],
            verbose=self.verbose,
        )
