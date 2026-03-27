# Copyright 2025 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Tool metadata for enhanced LLM guidance."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from enum import Enum


class ToolCategory(str, Enum):
    """Categories for organizing tools."""
    SCHEMA = "schema"
    DATA = "data"
    QUERY = "query"
    VECTOR = "vector"
    LOADING = "loading"
    DISCOVERY = "discovery"
    UTILITY = "utility"


class ToolMetadata(BaseModel):
    """Enhanced metadata for tools to help LLMs understand usage patterns."""
    category: ToolCategory
    prerequisites: List[str] = []
    related_tools: List[str] = []
    common_next_steps: List[str] = []
    use_cases: List[str] = []
    complexity: str = "basic"  # basic, intermediate, advanced
    examples: List[Dict[str, Any]] = []
    keywords: List[str] = []  # For discovery


# Define metadata for each tool
TOOL_METADATA: Dict[str, ToolMetadata] = {
    # Schema Operations
    "tigergraph__show_graph_details": ToolMetadata(
        category=ToolCategory.SCHEMA,
        prerequisites=[],
        related_tools=["tigergraph__get_graph_schema"],
        common_next_steps=["tigergraph__add_node", "tigergraph__add_edge", "tigergraph__run_query"],
        use_cases=[
            "Getting a full listing of a graph (schema, queries, jobs)",
            "Understanding the structure of a graph before writing queries",
            "Discovering available vertex and edge types",
            "First step in any graph interaction workflow"
        ],
        complexity="basic",
        keywords=["schema", "structure", "show", "understand", "explore", "queries", "jobs"],
        examples=[
            {
                "description": "Show everything under default graph",
                "parameters": {}
            },
            {
                "description": "Show everything under a specific graph",
                "parameters": {"graph_name": "SocialGraph"}
            }
        ]
    ),
    
    "tigergraph__list_graphs": ToolMetadata(
        category=ToolCategory.SCHEMA,
        prerequisites=[],
        related_tools=["tigergraph__show_graph_details", "tigergraph__create_graph"],
        common_next_steps=["tigergraph__show_graph_details"],
        use_cases=[
            "Discovering what graphs exist in the database",
            "First step when connecting to a new TigerGraph instance",
            "Verifying a graph was created successfully"
        ],
        complexity="basic",
        keywords=["list", "graphs", "discover", "available"],
        examples=[{"description": "List all graphs", "parameters": {}}]
    ),
    
    "tigergraph__create_graph": ToolMetadata(
        category=ToolCategory.SCHEMA,
        prerequisites=[],
        related_tools=["tigergraph__list_graphs", "tigergraph__show_graph_details"],
        common_next_steps=["tigergraph__show_graph_details", "tigergraph__add_node"],
        use_cases=[
            "Creating a new graph from scratch",
            "Setting up a graph with specific vertex and edge types",
            "Initializing a new project or data model"
        ],
        complexity="intermediate",
        keywords=["create", "new", "graph", "initialize", "setup"],
        examples=[
            {
                "description": "Create a social network graph",
                "parameters": {
                    "graph_name": "SocialGraph",
                    "vertex_types": [
                        {
                            "name": "Person",
                            "attributes": [
                                {"name": "name", "type": "STRING"},
                                {"name": "age", "type": "INT"}
                            ]
                        }
                    ],
                    "edge_types": [
                        {
                            "name": "FOLLOWS",
                            "from_vertex": "Person",
                            "to_vertex": "Person"
                        }
                    ]
                }
            }
        ]
    ),
    
    "tigergraph__get_graph_schema": ToolMetadata(
        category=ToolCategory.SCHEMA,
        prerequisites=[],
        related_tools=["tigergraph__show_graph_details"],
        common_next_steps=["tigergraph__add_node", "tigergraph__run_query"],
        use_cases=[
            "Getting raw JSON schema for programmatic processing",
            "Detailed schema inspection for advanced use cases"
        ],
        complexity="intermediate",
        keywords=["schema", "json", "raw", "detailed"],
        examples=[{"description": "Get raw schema", "parameters": {}}]
    ),
    
    # Node Operations
    "tigergraph__add_node": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=["tigergraph__show_graph_details"],
        related_tools=["tigergraph__add_nodes", "tigergraph__get_node", "tigergraph__delete_node"],
        common_next_steps=["tigergraph__get_node", "tigergraph__add_edge", "tigergraph__get_node_edges"],
        use_cases=[
            "Creating a single vertex in the graph",
            "Updating an existing vertex's attributes",
            "Adding individual entities (users, products, etc.)"
        ],
        complexity="basic",
        keywords=["add", "create", "insert", "node", "vertex", "single"],
        examples=[
            {
                "description": "Add a person node",
                "parameters": {
                    "vertex_type": "Person",
                    "vertex_id": "user123",
                    "attributes": {"name": "Alice", "age": 30, "city": "San Francisco"}
                }
            },
            {
                "description": "Add a product node",
                "parameters": {
                    "vertex_type": "Product",
                    "vertex_id": "prod456",
                    "attributes": {"name": "Laptop", "price": 999.99, "category": "Electronics"}
                }
            }
        ]
    ),
    
    "tigergraph__add_nodes": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=["tigergraph__show_graph_details"],
        related_tools=["tigergraph__add_node", "tigergraph__get_nodes"],
        common_next_steps=["tigergraph__get_vertex_count", "tigergraph__add_edges"],
        use_cases=[
            "Batch loading multiple vertices efficiently",
            "Importing data from CSV or JSON",
            "Initial data population"
        ],
        complexity="basic",
        keywords=["add", "create", "insert", "batch", "multiple", "bulk", "nodes", "vertices"],
        examples=[
            {
                "description": "Add multiple person nodes",
                "parameters": {
                    "vertex_type": "Person",
                    "vertices": [
                        {"id": "user1", "name": "Alice", "age": 30},
                        {"id": "user2", "name": "Bob", "age": 25},
                        {"id": "user3", "name": "Carol", "age": 35}
                    ]
                }
            }
        ]
    ),
    
    "tigergraph__get_node": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__get_nodes", "tigergraph__has_node"],
        common_next_steps=["tigergraph__get_node_edges", "tigergraph__delete_node"],
        use_cases=[
            "Retrieving a specific vertex by ID",
            "Verifying a vertex was created",
            "Checking vertex attributes"
        ],
        complexity="basic",
        keywords=["get", "retrieve", "fetch", "read", "node", "vertex", "single"],
        examples=[
            {
                "description": "Get a person node",
                "parameters": {
                    "vertex_type": "Person",
                    "vertex_id": "user123"
                }
            }
        ]
    ),
    
    "tigergraph__get_nodes": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__get_node", "tigergraph__get_vertex_count"],
        common_next_steps=["tigergraph__get_edges"],
        use_cases=[
            "Retrieving multiple vertices of a type",
            "Exploring graph data",
            "Data export and analysis"
        ],
        complexity="basic",
        keywords=["get", "retrieve", "fetch", "list", "multiple", "nodes", "vertices"],
        examples=[
            {
                "description": "Get all person nodes (limited)",
                "parameters": {
                    "vertex_type": "Person",
                    "limit": 100
                }
            }
        ]
    ),
    
    # Edge Operations
    "tigergraph__add_edge": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=["tigergraph__add_node", "tigergraph__show_graph_details"],
        related_tools=["tigergraph__add_edges", "tigergraph__get_edge"],
        common_next_steps=["tigergraph__get_node_edges", "tigergraph__get_neighbors"],
        use_cases=[
            "Creating a relationship between two vertices",
            "Connecting entities in the graph",
            "Building graph structure"
        ],
        complexity="basic",
        keywords=["add", "create", "connect", "relationship", "edge", "link"],
        examples=[
            {
                "description": "Create a friendship edge",
                "parameters": {
                    "edge_type": "FOLLOWS",
                    "from_vertex_type": "Person",
                    "from_vertex_id": "user1",
                    "to_vertex_type": "Person",
                    "to_vertex_id": "user2",
                    "attributes": {"since": "2024-01-15"}
                }
            }
        ]
    ),
    
    "tigergraph__add_edges": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=["tigergraph__add_nodes", "tigergraph__show_graph_details"],
        related_tools=["tigergraph__add_edge"],
        common_next_steps=["tigergraph__get_edge_count"],
        use_cases=[
            "Batch loading multiple edges",
            "Building graph structure efficiently",
            "Importing relationship data"
        ],
        complexity="basic",
        keywords=["add", "create", "batch", "multiple", "edges", "relationships", "bulk"],
        examples=[]
    ),
    
    # Query Operations
    "tigergraph__run_query": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=["tigergraph__show_graph_details"],
        related_tools=["tigergraph__run_installed_query", "tigergraph__get_neighbors"],
        common_next_steps=[],
        use_cases=[
            "Ad-hoc querying without installing",
            "Testing queries before installation",
            "Simple data retrieval operations",
            "Running openCypher or GSQL queries"
        ],
        complexity="intermediate",
        keywords=["query", "search", "find", "select", "interpret", "gsql", "cypher"],
        examples=[
            {
                "description": "Simple GSQL query",
                "parameters": {
                    "query_text": "INTERPRET QUERY () FOR GRAPH MyGraph { SELECT v FROM Person:v LIMIT 5; PRINT v; }"
                }
            },
            {
                "description": "openCypher query",
                "parameters": {
                    "query_text": "INTERPRET OPENCYPHER QUERY () FOR GRAPH MyGraph { MATCH (n:Person) RETURN n LIMIT 5 }"
                }
            }
        ]
    ),
    
    "tigergraph__get_neighbors": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=[],
        related_tools=["tigergraph__get_node_edges", "tigergraph__run_query"],
        common_next_steps=[],
        use_cases=[
            "Finding vertices connected to a given vertex",
            "1-hop graph traversal",
            "Discovering relationships"
        ],
        complexity="basic",
        keywords=["neighbors", "connected", "adjacent", "traverse", "related"],
        examples=[
            {
                "description": "Get friends of a person",
                "parameters": {
                    "vertex_type": "Person",
                    "vertex_id": "user1",
                    "edge_type": "FOLLOWS"
                }
            }
        ]
    ),
    
    # Vector Operations
    "tigergraph__add_vector_attribute": ToolMetadata(
        category=ToolCategory.VECTOR,
        prerequisites=["tigergraph__show_graph_details"],
        related_tools=["tigergraph__drop_vector_attribute", "tigergraph__get_vector_index_status"],
        common_next_steps=["tigergraph__get_vector_index_status", "tigergraph__upsert_vectors"],
        use_cases=[
            "Adding vector/embedding support to existing vertex types",
            "Setting up semantic search capabilities",
            "Enabling similarity-based queries"
        ],
        complexity="intermediate",
        keywords=["vector", "embedding", "add", "attribute", "similarity", "semantic"],
        examples=[
            {
                "description": "Add embedding attribute for documents",
                "parameters": {
                    "vertex_type": "Document",
                    "vector_name": "embedding",
                    "dimension": 384,
                    "metric": "COSINE"
                }
            },
            {
                "description": "Add embedding for products (higher dimension)",
                "parameters": {
                    "vertex_type": "Product",
                    "vector_name": "feature_vector",
                    "dimension": 1536,
                    "metric": "L2"
                }
            }
        ]
    ),
    
    "tigergraph__upsert_vectors": ToolMetadata(
        category=ToolCategory.VECTOR,
        prerequisites=["tigergraph__add_vector_attribute", "tigergraph__get_vector_index_status"],
        related_tools=["tigergraph__search_top_k_similarity", "tigergraph__fetch_vector"],
        common_next_steps=["tigergraph__get_vector_index_status", "tigergraph__search_top_k_similarity"],
        use_cases=[
            "Loading embedding vectors into the graph",
            "Updating vector data for vertices",
            "Populating semantic search index"
        ],
        complexity="intermediate",
        keywords=["vector", "embedding", "upsert", "load", "insert", "update"],
        examples=[
            {
                "description": "Upsert document embeddings",
                "parameters": {
                    "vertex_type": "Document",
                    "vector_attribute": "embedding",
                    "vectors": [
                        {
                            "vertex_id": "doc1",
                            "vector": [0.1, 0.2, 0.3],
                            "attributes": {"title": "Document 1"}
                        }
                    ]
                }
            }
        ]
    ),
    
    "tigergraph__search_top_k_similarity": ToolMetadata(
        category=ToolCategory.VECTOR,
        prerequisites=["tigergraph__upsert_vectors", "tigergraph__get_vector_index_status"],
        related_tools=["tigergraph__fetch_vector"],
        common_next_steps=[],
        use_cases=[
            "Finding similar documents or items",
            "Semantic search operations",
            "Recommendation based on similarity"
        ],
        complexity="intermediate",
        keywords=["vector", "search", "similarity", "nearest", "semantic", "find", "similar"],
        examples=[
            {
                "description": "Find similar documents",
                "parameters": {
                    "vertex_type": "Document",
                    "vector_attribute": "embedding",
                    "query_vector": [0.1, 0.2, 0.3],
                    "top_k": 10
                }
            }
        ]
    ),
    
    # Loading Operations
    "tigergraph__create_loading_job": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=["tigergraph__show_graph_details"],
        related_tools=["tigergraph__run_loading_job_with_file", "tigergraph__run_loading_job_with_data"],
        common_next_steps=["tigergraph__run_loading_job_with_file", "tigergraph__get_loading_jobs"],
        use_cases=[
            "Setting up data ingestion from CSV/JSON files",
            "Defining how file columns map to vertex/edge attributes",
            "Preparing for bulk data loading"
        ],
        complexity="advanced",
        keywords=["loading", "job", "create", "define", "ingest", "import"],
        examples=[]
    ),
    
    "tigergraph__run_loading_job_with_file": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=["tigergraph__create_loading_job"],
        related_tools=["tigergraph__run_loading_job_with_data", "tigergraph__get_loading_job_status"],
        common_next_steps=["tigergraph__get_loading_job_status", "tigergraph__get_vertex_count"],
        use_cases=[
            "Loading data from CSV or JSON files",
            "Bulk import of graph data",
            "ETL operations"
        ],
        complexity="intermediate",
        keywords=["loading", "job", "run", "file", "import", "bulk"],
        examples=[]
    ),
    
    # Statistics
    "tigergraph__get_vertex_count": ToolMetadata(
        category=ToolCategory.UTILITY,
        prerequisites=[],
        related_tools=["tigergraph__get_edge_count", "tigergraph__get_nodes"],
        common_next_steps=[],
        use_cases=[
            "Verifying data was loaded",
            "Monitoring graph size",
            "Data validation"
        ],
        complexity="basic",
        keywords=["count", "statistics", "size", "vertex", "node", "total"],
        examples=[
            {
                "description": "Count all vertices",
                "parameters": {}
            },
            {
                "description": "Count specific vertex type",
                "parameters": {"vertex_type": "Person"}
            }
        ]
    ),
    
    "tigergraph__get_edge_count": ToolMetadata(
        category=ToolCategory.UTILITY,
        prerequisites=[],
        related_tools=["tigergraph__get_vertex_count"],
        common_next_steps=[],
        use_cases=[
            "Verifying relationships were created",
            "Monitoring graph connectivity",
            "Data validation"
        ],
        complexity="basic",
        keywords=["count", "statistics", "size", "edge", "relationship", "total"],
        examples=[]
    ),

    # New tools (1.1.0)

    "tigergraph__update_schema": ToolMetadata(
        category=ToolCategory.SCHEMA,
        prerequisites=["tigergraph__get_graph_schema"],
        related_tools=["tigergraph__create_graph", "tigergraph__get_graph_schema", "tigergraph__validate_schema_names"],
        common_next_steps=["tigergraph__get_graph_schema", "tigergraph__show_graph_details"],
        use_cases=[
            "Adding new vertex or edge types to an existing graph",
            "Dropping vertex or edge types no longer needed",
            "Adding or removing attributes on existing vertex types",
            "Incremental schema evolution without recreating the graph"
        ],
        complexity="intermediate",
        keywords=["schema", "alter", "modify", "update", "add", "drop", "attribute", "vertex", "edge"],
        examples=[
            {
                "description": "Add a new vertex type",
                "parameters": {
                    "graph_name": "MyGraph",
                    "add_vertex_types": [{"name": "Product", "attributes": [{"name": "price", "type": "FLOAT"}]}]
                }
            },
            {
                "description": "Add an attribute to an existing vertex type",
                "parameters": {
                    "graph_name": "MyGraph",
                    "add_vertex_attributes": {"Person": [{"name": "score", "type": "FLOAT"}]}
                }
            }
        ]
    ),

    "tigergraph__validate_schema_names": ToolMetadata(
        category=ToolCategory.SCHEMA,
        prerequisites=[],
        related_tools=["tigergraph__create_graph", "tigergraph__update_schema"],
        common_next_steps=["tigergraph__create_graph"],
        use_cases=[
            "Pre-validating schema names before graph creation",
            "Checking for GSQL reserved keyword conflicts",
            "Validating naming conventions in user-supplied schemas"
        ],
        complexity="basic",
        keywords=["validate", "check", "reserved", "keyword", "name", "schema", "conflict"],
        examples=[
            {
                "description": "Validate vertex names",
                "parameters": {
                    "vertex_types": [{"name": "SELECT", "attributes": [{"name": "count", "type": "INT"}]}]
                }
            }
        ]
    ),

    # Global schema
    "tigergraph__get_global_schema": ToolMetadata(
        category=ToolCategory.SCHEMA,
        prerequisites=[],
        related_tools=["tigergraph__list_graphs", "tigergraph__show_graph_details"],
        common_next_steps=["tigergraph__show_graph_details"],
        use_cases=[
            "Seeing all graphs and global types at once",
            "Database-level schema exploration via raw GSQL LS output"
        ],
        complexity="basic",
        keywords=["global", "schema", "ls", "all", "database"],
        examples=[{"description": "Get global schema", "parameters": {}}]
    ),

    # Graph operations
    "tigergraph__drop_graph": ToolMetadata(
        category=ToolCategory.SCHEMA,
        prerequisites=["tigergraph__list_graphs"],
        related_tools=["tigergraph__create_graph", "tigergraph__clear_graph_data"],
        common_next_steps=["tigergraph__list_graphs"],
        use_cases=["Removing a graph permanently", "Cleaning up test graphs"],
        complexity="basic",
        keywords=["drop", "delete", "remove", "graph", "destroy"],
        examples=[{"description": "Drop a graph", "parameters": {"graph_name": "TestGraph"}}]
    ),

    "tigergraph__clear_graph_data": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=["tigergraph__list_graphs"],
        related_tools=["tigergraph__drop_graph", "tigergraph__get_vertex_count"],
        common_next_steps=["tigergraph__get_vertex_count"],
        use_cases=["Resetting data while keeping schema", "Clearing test data"],
        complexity="basic",
        keywords=["clear", "reset", "empty", "data", "keep", "schema"],
        examples=[{"description": "Clear all data", "parameters": {"graph_name": "MyGraph", "confirm": True}}]
    ),

    # Node operations (missing)
    "tigergraph__delete_node": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__delete_nodes", "tigergraph__get_node"],
        common_next_steps=["tigergraph__get_vertex_count"],
        use_cases=["Deleting a single vertex by ID", "Removing specific entities"],
        complexity="basic",
        keywords=["delete", "remove", "node", "vertex", "single"],
        examples=[{"description": "Delete a person node", "parameters": {"vertex_type": "Person", "vertex_id": "user123"}}]
    ),

    "tigergraph__delete_nodes": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__delete_node", "tigergraph__clear_graph_data"],
        common_next_steps=["tigergraph__get_vertex_count"],
        use_cases=["Batch deleting vertices", "Removing filtered vertex sets"],
        complexity="basic",
        keywords=["delete", "remove", "batch", "multiple", "nodes", "vertices"],
        examples=[]
    ),

    "tigergraph__has_node": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__get_node"],
        common_next_steps=["tigergraph__get_node"],
        use_cases=["Checking if a vertex exists before operations", "Existence validation"],
        complexity="basic",
        keywords=["exists", "check", "has", "node", "vertex"],
        examples=[{"description": "Check if user exists", "parameters": {"vertex_type": "Person", "vertex_id": "user123"}}]
    ),

    "tigergraph__get_node_edges": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__get_neighbors", "tigergraph__get_edges"],
        common_next_steps=["tigergraph__get_neighbors"],
        use_cases=["Finding all edges connected to a vertex", "Exploring local graph structure"],
        complexity="basic",
        keywords=["edges", "connected", "node", "adjacent", "relationships"],
        examples=[{"description": "Get edges of a person", "parameters": {"vertex_type": "Person", "vertex_id": "user123"}}]
    ),

    # Edge operations (missing)
    "tigergraph__get_edge": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__get_edges", "tigergraph__has_edge"],
        common_next_steps=[],
        use_cases=["Retrieving a specific edge", "Checking edge attributes"],
        complexity="basic",
        keywords=["get", "retrieve", "edge", "relationship", "single"],
        examples=[]
    ),

    "tigergraph__get_edges": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__get_edge", "tigergraph__get_edge_count"],
        common_next_steps=[],
        use_cases=["Retrieving multiple edges", "Exploring relationships"],
        complexity="basic",
        keywords=["get", "retrieve", "list", "edges", "relationships", "multiple"],
        examples=[]
    ),

    "tigergraph__delete_edge": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__delete_edges"],
        common_next_steps=["tigergraph__get_edge_count"],
        use_cases=["Removing a single relationship"],
        complexity="basic",
        keywords=["delete", "remove", "edge", "relationship"],
        examples=[]
    ),

    "tigergraph__delete_edges": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__delete_edge"],
        common_next_steps=["tigergraph__get_edge_count"],
        use_cases=["Batch deleting edges"],
        complexity="basic",
        keywords=["delete", "remove", "batch", "edges", "relationships"],
        examples=[]
    ),

    "tigergraph__has_edge": ToolMetadata(
        category=ToolCategory.DATA,
        prerequisites=[],
        related_tools=["tigergraph__get_edge"],
        common_next_steps=["tigergraph__get_edge"],
        use_cases=["Checking if a relationship exists"],
        complexity="basic",
        keywords=["exists", "check", "has", "edge", "relationship"],
        examples=[]
    ),

    # Query operations (missing)
    "tigergraph__run_installed_query": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=["tigergraph__install_query"],
        related_tools=["tigergraph__run_query", "tigergraph__install_query"],
        common_next_steps=[],
        use_cases=["Running a pre-installed query with parameters", "Production query execution"],
        complexity="basic",
        keywords=["run", "execute", "installed", "query", "parameters"],
        examples=[{"description": "Run an installed query", "parameters": {"graph_name": "MyGraph", "query_name": "myQuery", "params": {"p1": "value"}}}]
    ),

    "tigergraph__install_query": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=["tigergraph__show_graph_details"],
        related_tools=["tigergraph__run_installed_query", "tigergraph__drop_query"],
        common_next_steps=["tigergraph__run_installed_query"],
        use_cases=["Installing a GSQL query for production use", "Compiling queries for better performance"],
        complexity="advanced",
        keywords=["install", "compile", "query", "gsql", "create"],
        examples=[]
    ),

    "tigergraph__drop_query": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=[],
        related_tools=["tigergraph__install_query", "tigergraph__show_query"],
        common_next_steps=["tigergraph__show_graph_details"],
        use_cases=["Removing an installed query"],
        complexity="basic",
        keywords=["drop", "delete", "remove", "query"],
        examples=[]
    ),

    "tigergraph__show_query": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=[],
        related_tools=["tigergraph__get_query_metadata", "tigergraph__is_query_installed"],
        common_next_steps=["tigergraph__run_installed_query"],
        use_cases=["Viewing query source code", "Inspecting query definitions"],
        complexity="basic",
        keywords=["show", "view", "query", "source", "code"],
        examples=[]
    ),

    "tigergraph__get_query_metadata": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=[],
        related_tools=["tigergraph__show_query", "tigergraph__is_query_installed"],
        common_next_steps=["tigergraph__run_installed_query"],
        use_cases=["Getting query parameter types and signatures", "Query discovery"],
        complexity="basic",
        keywords=["metadata", "signature", "parameters", "query", "info"],
        examples=[]
    ),

    "tigergraph__is_query_installed": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=[],
        related_tools=["tigergraph__install_query", "tigergraph__show_query"],
        common_next_steps=["tigergraph__install_query", "tigergraph__run_installed_query"],
        use_cases=["Checking if a query is ready to run"],
        complexity="basic",
        keywords=["check", "installed", "query", "exists", "ready"],
        examples=[]
    ),

    # GSQL operations
    "tigergraph__gsql": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=[],
        related_tools=["tigergraph__run_query"],
        common_next_steps=[],
        use_cases=["Running arbitrary GSQL commands", "Schema DDL via raw GSQL", "Administrative commands"],
        complexity="advanced",
        keywords=["gsql", "command", "raw", "ddl", "admin"],
        examples=[]
    ),

    "tigergraph__generate_gsql": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=["tigergraph__show_graph_details"],
        related_tools=["tigergraph__gsql", "tigergraph__generate_cypher"],
        common_next_steps=["tigergraph__install_query"],
        use_cases=["AI-assisted GSQL query generation from natural language"],
        complexity="advanced",
        keywords=["generate", "ai", "gsql", "natural", "language"],
        examples=[]
    ),

    "tigergraph__generate_cypher": ToolMetadata(
        category=ToolCategory.QUERY,
        prerequisites=["tigergraph__show_graph_details"],
        related_tools=["tigergraph__generate_gsql", "tigergraph__run_query"],
        common_next_steps=["tigergraph__run_query"],
        use_cases=["AI-assisted openCypher query generation"],
        complexity="advanced",
        keywords=["generate", "ai", "cypher", "opencypher", "natural", "language"],
        examples=[]
    ),

    # Statistics (missing)
    "tigergraph__get_node_degree": ToolMetadata(
        category=ToolCategory.UTILITY,
        prerequisites=[],
        related_tools=["tigergraph__get_vertex_count", "tigergraph__get_edge_count"],
        common_next_steps=[],
        use_cases=["Finding connectivity of a specific vertex", "Identifying hub nodes"],
        complexity="basic",
        keywords=["degree", "connectivity", "node", "count", "edges"],
        examples=[]
    ),

    # Vector operations (missing)
    "tigergraph__drop_vector_attribute": ToolMetadata(
        category=ToolCategory.VECTOR,
        prerequisites=[],
        related_tools=["tigergraph__add_vector_attribute", "tigergraph__list_vector_attributes"],
        common_next_steps=["tigergraph__list_vector_attributes"],
        use_cases=["Removing vector attributes from vertex types"],
        complexity="basic",
        keywords=["vector", "drop", "remove", "attribute", "embedding"],
        examples=[]
    ),

    "tigergraph__list_vector_attributes": ToolMetadata(
        category=ToolCategory.VECTOR,
        prerequisites=[],
        related_tools=["tigergraph__add_vector_attribute", "tigergraph__get_vector_index_status"],
        common_next_steps=["tigergraph__upsert_vectors"],
        use_cases=["Listing all vector attributes in a graph"],
        complexity="basic",
        keywords=["vector", "list", "attributes", "embedding"],
        examples=[]
    ),

    "tigergraph__get_vector_index_status": ToolMetadata(
        category=ToolCategory.VECTOR,
        prerequisites=["tigergraph__add_vector_attribute"],
        related_tools=["tigergraph__add_vector_attribute", "tigergraph__upsert_vectors"],
        common_next_steps=["tigergraph__upsert_vectors", "tigergraph__search_top_k_similarity"],
        use_cases=["Checking if vector index is ready for queries"],
        complexity="basic",
        keywords=["vector", "index", "status", "ready", "online"],
        examples=[]
    ),

    "tigergraph__fetch_vector": ToolMetadata(
        category=ToolCategory.VECTOR,
        prerequisites=["tigergraph__upsert_vectors"],
        related_tools=["tigergraph__search_top_k_similarity", "tigergraph__upsert_vectors"],
        common_next_steps=[],
        use_cases=["Retrieving stored vector embeddings for a vertex"],
        complexity="basic",
        keywords=["vector", "fetch", "retrieve", "embedding", "get"],
        examples=[]
    ),

    "tigergraph__load_vectors_from_csv": ToolMetadata(
        category=ToolCategory.VECTOR,
        prerequisites=["tigergraph__add_vector_attribute"],
        related_tools=["tigergraph__load_vectors_from_json", "tigergraph__upsert_vectors"],
        common_next_steps=["tigergraph__get_vector_index_status"],
        use_cases=["Bulk loading vectors from CSV files"],
        complexity="intermediate",
        keywords=["vector", "load", "csv", "bulk", "import"],
        examples=[]
    ),

    "tigergraph__load_vectors_from_json": ToolMetadata(
        category=ToolCategory.VECTOR,
        prerequisites=["tigergraph__add_vector_attribute"],
        related_tools=["tigergraph__load_vectors_from_csv", "tigergraph__upsert_vectors"],
        common_next_steps=["tigergraph__get_vector_index_status"],
        use_cases=["Bulk loading vectors from JSON files"],
        complexity="intermediate",
        keywords=["vector", "load", "json", "bulk", "import"],
        examples=[]
    ),

    # Loading operations (missing)
    "tigergraph__run_loading_job_with_data": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=["tigergraph__create_loading_job"],
        related_tools=["tigergraph__run_loading_job_with_file", "tigergraph__get_loading_job_status"],
        common_next_steps=["tigergraph__get_loading_job_status", "tigergraph__get_vertex_count"],
        use_cases=["Loading inline data into the graph", "Small batch data ingestion"],
        complexity="intermediate",
        keywords=["loading", "job", "run", "data", "inline", "import"],
        examples=[]
    ),

    "tigergraph__get_loading_jobs": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=[],
        related_tools=["tigergraph__create_loading_job", "tigergraph__drop_loading_job"],
        common_next_steps=["tigergraph__run_loading_job_with_file"],
        use_cases=["Listing available loading jobs", "Discovering existing data pipelines"],
        complexity="basic",
        keywords=["loading", "jobs", "list", "available"],
        examples=[]
    ),

    "tigergraph__get_loading_job_status": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=["tigergraph__run_loading_job_with_file"],
        related_tools=["tigergraph__get_loading_jobs"],
        common_next_steps=["tigergraph__get_vertex_count"],
        use_cases=["Checking progress of a running loading job", "Monitoring data ingestion"],
        complexity="basic",
        keywords=["loading", "status", "progress", "monitor"],
        examples=[]
    ),

    "tigergraph__drop_loading_job": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=[],
        related_tools=["tigergraph__create_loading_job", "tigergraph__get_loading_jobs"],
        common_next_steps=["tigergraph__get_loading_jobs"],
        use_cases=["Removing a loading job definition"],
        complexity="basic",
        keywords=["loading", "drop", "delete", "remove", "job"],
        examples=[]
    ),

    # Data source operations
    "tigergraph__create_data_source": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=[],
        related_tools=["tigergraph__get_data_source", "tigergraph__update_data_source"],
        common_next_steps=["tigergraph__create_loading_job"],
        use_cases=["Configuring an S3, Kafka, or other external data source"],
        complexity="intermediate",
        keywords=["data", "source", "create", "s3", "kafka", "configure"],
        examples=[]
    ),

    "tigergraph__update_data_source": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=["tigergraph__create_data_source"],
        related_tools=["tigergraph__get_data_source"],
        common_next_steps=[],
        use_cases=["Updating data source credentials or configuration"],
        complexity="intermediate",
        keywords=["data", "source", "update", "modify", "config"],
        examples=[]
    ),

    "tigergraph__get_data_source": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=[],
        related_tools=["tigergraph__get_all_data_sources"],
        common_next_steps=[],
        use_cases=["Inspecting a data source configuration"],
        complexity="basic",
        keywords=["data", "source", "get", "inspect", "view"],
        examples=[]
    ),

    "tigergraph__drop_data_source": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=[],
        related_tools=["tigergraph__get_all_data_sources"],
        common_next_steps=["tigergraph__get_all_data_sources"],
        use_cases=["Removing a data source"],
        complexity="basic",
        keywords=["data", "source", "drop", "delete", "remove"],
        examples=[]
    ),

    "tigergraph__get_all_data_sources": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=[],
        related_tools=["tigergraph__create_data_source"],
        common_next_steps=[],
        use_cases=["Listing all configured data sources"],
        complexity="basic",
        keywords=["data", "sources", "list", "all"],
        examples=[]
    ),

    "tigergraph__drop_all_data_sources": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=[],
        related_tools=["tigergraph__get_all_data_sources"],
        common_next_steps=[],
        use_cases=["Removing all data sources"],
        complexity="basic",
        keywords=["data", "sources", "drop", "all", "delete"],
        examples=[]
    ),

    "tigergraph__preview_sample_data": ToolMetadata(
        category=ToolCategory.LOADING,
        prerequisites=["tigergraph__create_data_source"],
        related_tools=["tigergraph__create_loading_job"],
        common_next_steps=["tigergraph__create_loading_job"],
        use_cases=["Previewing first N rows of an S3 data file", "Data exploration before loading"],
        complexity="basic",
        keywords=["preview", "sample", "data", "s3", "explore", "inspect"],
        examples=[]
    ),

    # Connection operations
    "tigergraph__list_connections": ToolMetadata(
        category=ToolCategory.UTILITY,
        prerequisites=[],
        related_tools=["tigergraph__show_connection"],
        common_next_steps=["tigergraph__show_connection", "tigergraph__list_graphs"],
        use_cases=["Discovering available connection profiles"],
        complexity="basic",
        keywords=["connections", "profiles", "list", "available"],
        examples=[{"description": "List profiles", "parameters": {}}]
    ),

    "tigergraph__show_connection": ToolMetadata(
        category=ToolCategory.UTILITY,
        prerequisites=[],
        related_tools=["tigergraph__list_connections"],
        common_next_steps=["tigergraph__list_graphs"],
        use_cases=["Viewing connection details for a profile"],
        complexity="basic",
        keywords=["connection", "profile", "show", "details", "info"],
        examples=[]
    ),

    # Discovery operations
    "tigergraph__discover_tools": ToolMetadata(
        category=ToolCategory.DISCOVERY,
        prerequisites=[],
        related_tools=["tigergraph__get_tool_info", "tigergraph__get_workflow"],
        common_next_steps=["tigergraph__get_tool_info"],
        use_cases=["Finding relevant tools by keyword", "Exploring available capabilities"],
        complexity="basic",
        keywords=["discover", "find", "search", "tools", "capabilities"],
        examples=[]
    ),

    "tigergraph__get_workflow": ToolMetadata(
        category=ToolCategory.DISCOVERY,
        prerequisites=[],
        related_tools=["tigergraph__discover_tools", "tigergraph__get_tool_info"],
        common_next_steps=[],
        use_cases=["Getting step-by-step guidance for common workflows"],
        complexity="basic",
        keywords=["workflow", "guide", "steps", "how", "tutorial"],
        examples=[]
    ),

    "tigergraph__get_tool_info": ToolMetadata(
        category=ToolCategory.DISCOVERY,
        prerequisites=[],
        related_tools=["tigergraph__discover_tools"],
        common_next_steps=[],
        use_cases=["Getting detailed information about a specific tool"],
        complexity="basic",
        keywords=["tool", "info", "details", "help", "usage"],
        examples=[]
    ),
}


def get_tool_metadata(tool_name: str) -> Optional[ToolMetadata]:
    """Get metadata for a specific tool."""
    return TOOL_METADATA.get(tool_name)


def get_tools_by_category(category: ToolCategory) -> List[str]:
    """Get all tool names in a specific category."""
    return [
        tool_name for tool_name, metadata in TOOL_METADATA.items()
        if metadata.category == category
    ]


def search_tools_by_keywords(keywords: List[str]) -> List[str]:
    """Search for tools matching any of the provided keywords."""
    matching_tools = []
    keywords_lower = [k.lower() for k in keywords]
    
    for tool_name, metadata in TOOL_METADATA.items():
        # Check if any keyword matches
        for keyword in keywords_lower:
            if any(keyword in mk.lower() for mk in metadata.keywords):
                matching_tools.append(tool_name)
                break
            # Also check in use cases
            if any(keyword in uc.lower() for uc in metadata.use_cases):
                matching_tools.append(tool_name)
                break
    
    return matching_tools
