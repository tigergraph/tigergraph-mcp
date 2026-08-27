# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Data source operation tools for MCP."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from mcp.types import Tool, TextContent

from ..tool_names import TigerGraphToolName
from ..connection_manager import get_connection
from .datasource_types import (
    DATA_SOURCE_TYPES,
    DOC_URL,
    describe_all,
    find_spec,
    guidance,
    normalize_type,
    redact,
)


def _type_field_description() -> str:
    """Build the data_source_type description from the registry."""
    entries = ", ".join(
        f"'{spec.type_value}' ({spec.label})" for spec in DATA_SOURCE_TYPES.values()
    )
    return (
        f"Type of data source, normally one of: {entries}. "
        "'azure_blob' is accepted as an alias for 'abs'. Any other value is "
        "passed to TigerGraph unchanged, which decides whether it is valid. "
        "Call 'get_data_source_types' for the configuration keys each type needs."
    )


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class CreateDataSourceToolInput(BaseModel):
    """Input schema for creating a data source."""
    profile: Optional[str] = Field(None, description="Connection profile name. Omit to use the active default profile. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source.")
    data_source_type: str = Field(..., description=_type_field_description())
    config: Dict[str, Any] = Field(
        ...,
        description=(
            "Configuration for the data source, without the 'type' key. Key "
            "names are type-specific: Snowflake takes 'connection.url', "
            "'connection.user', and 'connection.password'; S3 takes 'access.key' "
            "and 'secret.key'. "
            "Call 'get_data_source_types' for each type's required keys and an example."
        ),
    )


class UpdateDataSourceToolInput(BaseModel):
    """Input schema for updating a data source."""
    profile: Optional[str] = Field(None, description="Connection profile name. Omit to use the active default profile. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source to update.")
    config: Dict[str, Any] = Field(..., description="Updated configuration for the data source.")
    data_source_type: Optional[str] = Field(
        None,
        description=(
            "Type of the data source. Optional; when given, the configuration is "
            "validated against that type before the update is sent."
        ),
    )


class GetDataSourceToolInput(BaseModel):
    """Input schema for getting a data source."""
    profile: Optional[str] = Field(None, description="Connection profile name. Omit to use the active default profile. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source.")


class DropDataSourceToolInput(BaseModel):
    """Input schema for dropping a data source."""
    profile: Optional[str] = Field(None, description="Connection profile name. Omit to use the active default profile. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source to drop.")
    graph_name: Optional[str] = Field(None, description="Name of the graph. If not provided, uses default connection.")


class GetAllDataSourcesToolInput(BaseModel):
    """Input schema for getting all data sources."""
    profile: Optional[str] = Field(None, description="Connection profile name. Omit to use the active default profile. Use 'list_connections' to see available profiles.")


class DropAllDataSourcesToolInput(BaseModel):
    """Input schema for dropping all data sources."""
    profile: Optional[str] = Field(None, description="Connection profile name. Omit to use the active default profile. Use 'list_connections' to see available profiles.")
    confirm: bool = Field(False, description="Must be True to confirm dropping all data sources.")


class PreviewSampleDataToolInput(BaseModel):
    """Input schema for previewing sample data."""
    profile: Optional[str] = Field(None, description="Connection profile name. Omit to use the active default profile. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source.")
    file_path: str = Field(
        ...,
        description=(
            "For an object store source, the path to the file within the data "
            "source (e.g. 's3a://bucket/data.csv'). For a warehouse source "
            "such as Snowflake, the SQL query to sample instead "
            "(e.g. 'SELECT * FROM <db>.<schema>.<table>')."
        ),
    )
    num_rows: int = Field(10, description="Number of sample rows to preview.")
    graph_name: Optional[str] = Field(None, description="Name of the graph context. If not provided, uses default connection.")


class GetDataSourceTypesToolInput(BaseModel):
    """Input schema for listing supported data source types."""
    family: Optional[str] = Field(
        None,
        description=(
            "Optional filter: 'object_store', 'warehouse', 'stream', or 'filesystem'. "
            "Omit to list every type."
        ),
    )


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

create_data_source_tool = Tool(
    name=TigerGraphToolName.CREATE_DATA_SOURCE,
    description=(
        "Create a new data source for loading data from object storage "
        "(S3, GCS, Azure Blob), a data warehouse (Snowflake, BigQuery, "
        "PostgreSQL), an Iceberg catalog, or Kafka. "
        "Call 'get_data_source_types' first if unsure which keys a type needs; "
        "if the server rejects the request, the response includes the keys that "
        "type requires."
    ),
    inputSchema=CreateDataSourceToolInput.model_json_schema(),
)

get_data_source_types_tool = Tool(
    name=TigerGraphToolName.GET_DATA_SOURCE_TYPES,
    description=(
        "List the data source types supported by 'create_data_source', with the "
        "required and optional configuration keys and an example config for each. "
        "Answers locally without contacting TigerGraph."
    ),
    inputSchema=GetDataSourceTypesToolInput.model_json_schema(),
)

update_data_source_tool = Tool(
    name=TigerGraphToolName.UPDATE_DATA_SOURCE,
    description="Update an existing data source configuration.",
    inputSchema=UpdateDataSourceToolInput.model_json_schema(),
)

get_data_source_tool = Tool(
    name=TigerGraphToolName.GET_DATA_SOURCE,
    description="Get information about a specific data source.",
    inputSchema=GetDataSourceToolInput.model_json_schema(),
)

drop_data_source_tool = Tool(
    name=TigerGraphToolName.DROP_DATA_SOURCE,
    description="Drop (delete) a data source.",
    inputSchema=DropDataSourceToolInput.model_json_schema(),
)

get_all_data_sources_tool = Tool(
    name=TigerGraphToolName.GET_ALL_DATA_SOURCES,
    description="Get information about all data sources.",
    inputSchema=GetAllDataSourcesToolInput.model_json_schema(),
)

drop_all_data_sources_tool = Tool(
    name=TigerGraphToolName.DROP_ALL_DATA_SOURCES,
    description="Drop all data sources. WARNING: This is a destructive operation.",
    inputSchema=DropAllDataSourcesToolInput.model_json_schema(),
)

preview_sample_data_tool = Tool(
    name=TigerGraphToolName.PREVIEW_SAMPLE_DATA,
    description="Preview sample data from a file in a data source.",
    inputSchema=PreviewSampleDataToolInput.model_json_schema(),
)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def create_data_source(
    data_source_name: str,
    data_source_type: str,
    config: Dict[str, Any],
    profile: Optional[str] = None,
) -> List[TextContent]:
    """Create a new data source.

    The type and config are forwarded to TigerGraph as given; the server is the
    authority on what it accepts. If it refuses, the local type registry is used
    to explain what the type usually needs.
    """
    from ..response_formatter import format_success, format_error

    type_value = normalize_type(data_source_type)
    spec = find_spec(type_value)
    # An explicit 'type' inside config must not silently override the argument.
    config = {k: v for k, v in config.items() if k != "type"}
    full_config = {"type": type_value, **config}

    try:
        conn = get_connection(profile=profile)
        result = await conn.createDataSource(dsName=data_source_name, config=full_config)
        result_str = result.get("message", str(result))

        follow_up = [f"View data source: get_data_source(data_source_name='{data_source_name}')"]
        if spec is not None and spec.family in ("warehouse", "lakehouse"):
            follow_up += [
                "Preview rows: preview_sample_data(data_source_name="
                f"'{data_source_name}', file_path='SELECT * FROM <db>.<schema>.<table>')",
                "Load with a query: create_loading_job(files=[{'file_alias': 'f1', "
                f"'data_source': '{data_source_name}', 'query': 'SELECT ...', ...}}])",
            ]
        else:
            follow_up.append("List all data sources: get_all_data_sources()")

        return format_success(
            operation="create_data_source",
            summary=f"Data source '{data_source_name}' of type '{type_value}' created successfully",
            data={
                "data_source_name": data_source_name,
                "data_source_type": type_value,
                "config": redact(type_value, full_config),
                "result": result_str,
            },
            suggestions=follow_up,
            metadata={"data_source_family": spec.family if spec else "unknown"},
        )
    except Exception as e:
        return format_error(
            operation="create_data_source",
            error=e,
            context={
                "data_source_name": data_source_name,
                "data_source_type": type_value,
                "config": redact(type_value, config),
            },
            suggestions=guidance(type_value, config),
        )


async def update_data_source(
    data_source_name: str,
    config: Dict[str, Any],
    profile: Optional[str] = None,
    data_source_type: Optional[str] = None,
) -> List[TextContent]:
    """Update an existing data source.

    Like create, the configuration is forwarded as given and the server decides.
    """
    from ..response_formatter import format_success, format_error

    declared_type = data_source_type or config.get("type")
    type_value = normalize_type(declared_type) if declared_type else None
    if type_value:
        config = {"type": type_value, **{k: v for k, v in config.items() if k != "type"}}

    try:
        conn = get_connection(profile=profile)
        result = await conn.updateDataSource(dsName=data_source_name, config=config)
        result_str = result.get("message", str(result))

        return format_success(
            operation="update_data_source",
            summary=f"Data source '{data_source_name}' updated successfully",
            data={
                "data_source_name": data_source_name,
                "config": redact(type_value, config),
                "result": result_str,
            },
        )
    except Exception as e:
        hints = ["An update replaces the whole configuration, so every required "
                 "key must be present even if unchanged."]
        if type_value:
            hints += guidance(type_value, {k: v for k, v in config.items() if k != "type"})
        else:
            hints.append(
                "Pass data_source_type to get type-specific guidance, or call "
                "get_data_source_types()."
            )
        return format_error(
            operation="update_data_source",
            error=e,
            context={"data_source_name": data_source_name},
            suggestions=hints,
        )


async def get_data_source(
    data_source_name: str,
    profile: Optional[str] = None,
) -> List[TextContent]:
    """Get information about a data source."""
    from ..response_formatter import format_success, format_error

    try:
        conn = get_connection(profile=profile)
        result = await conn.getDataSource(dsName=data_source_name)

        return format_success(
            operation="get_data_source",
            summary=f"Data source '{data_source_name}' details",
            data={"data_source_name": data_source_name, "details": redact(None, result)},
            metadata={"credentials_redacted": True},
        )
    except Exception as e:
        return format_error(
            operation="get_data_source",
            error=e,
            context={"data_source_name": data_source_name},
        )


async def drop_data_source(
    data_source_name: str,
    profile: Optional[str] = None,
    graph_name: Optional[str] = None,
) -> List[TextContent]:
    """Drop a data source."""
    from ..response_formatter import format_success, format_error

    try:
        conn = get_connection(profile=profile, graph_name=graph_name)
        result = await conn.dropDataSource(dsName=data_source_name)
        result_str = result.get("message", str(result))

        return format_success(
            operation="drop_data_source",
            summary=f"Data source '{data_source_name}' dropped successfully",
            data={"data_source_name": data_source_name, "result": result_str},
            suggestions=["List remaining: get_all_data_sources()"],
            metadata={"destructive": True},
        )
    except Exception as e:
        return format_error(
            operation="drop_data_source",
            error=e,
            context={"data_source_name": data_source_name},
        )


async def get_all_data_sources(
    profile: Optional[str] = None,
    **kwargs,
) -> List[TextContent]:
    """Get all data sources."""
    from ..response_formatter import format_success, format_error

    try:
        conn = get_connection(profile=profile)
        result = await conn.getDataSources()

        return format_success(
            operation="get_all_data_sources",
            summary="All data sources retrieved",
            data={"details": redact(None, result)},
            suggestions=[
                "Create a data source: create_data_source(...)",
                "See supported types and their keys: get_data_source_types()",
            ],
            metadata={"credentials_redacted": True},
        )
    except Exception as e:
        return format_error(
            operation="get_all_data_sources",
            error=e,
            context={},
        )


async def drop_all_data_sources(
    profile: Optional[str] = None,
    confirm: bool = False,
) -> List[TextContent]:
    """Drop all data sources."""
    from ..response_formatter import format_success, format_error

    if not confirm:
        return format_error(
            operation="drop_all_data_sources",
            error=ValueError("Confirmation required"),
            context={},
            suggestions=[
                "Set confirm=True to proceed with this destructive operation",
                "This will drop ALL data sources",
            ],
        )

    try:
        conn = get_connection(profile=profile)
        result = await conn.dropAllDataSources()
        result_str = result.get("message", str(result))

        return format_success(
            operation="drop_all_data_sources",
            summary="All data sources dropped successfully",
            data={"result": result_str},
            metadata={"destructive": True},
        )
    except Exception as e:
        return format_error(
            operation="drop_all_data_sources",
            error=e,
            context={},
        )


async def preview_sample_data(
    data_source_name: str,
    file_path: str,
    num_rows: int = 10,
    profile: Optional[str] = None,
    graph_name: Optional[str] = None,
) -> List[TextContent]:
    """Preview sample data from a file in a data source."""
    from ..response_formatter import format_success, format_error

    try:
        conn = get_connection(profile=profile, graph_name=graph_name)
        result = await conn.previewSampleData(
            dsName=data_source_name,
            path=file_path,
            size=num_rows,
        )

        return format_success(
            operation="preview_sample_data",
            summary=f"Sample data from '{file_path}' (first {num_rows} rows)",
            data={
                "data_source_name": data_source_name,
                "file_path": file_path,
                "preview": result,
            },
            metadata={"graph_name": conn.graphname},
        )
    except NotImplementedError as e:
        return format_error(
            operation="preview_sample_data",
            error=e,
            context={"data_source_name": data_source_name, "file_path": file_path},
            suggestions=[
                "File content preview requires TigerGraph 4.x.",
                "On 3.x, access the file directly via your cloud storage provider.",
            ],
        )
    except Exception as e:
        return format_error(
            operation="preview_sample_data",
            error=e,
            context={"data_source_name": data_source_name, "file_path": file_path},
        )


async def get_data_source_types(
    family: Optional[str] = None,
    **kwargs,
) -> List[TextContent]:
    """List supported data source types and their configuration keys."""
    from ..response_formatter import format_success, format_error

    families = sorted({spec.family for spec in DATA_SOURCE_TYPES.values()})
    if family is not None and family not in families:
        return format_error(
            operation="get_data_source_types",
            error=ValueError(f"Unknown family '{family}'"),
            context={"family": family},
            suggestions=[f"Valid families: {', '.join(families)}"],
        )

    types = describe_all(family)
    return format_success(
        operation="get_data_source_types",
        summary=(
            f"{len(types)} data source type(s) supported"
            + (f" in family '{family}'" if family else "")
        ),
        data={"types": types, "families": families},
        suggestions=[
            "Create one: create_data_source(data_source_name=..., "
            "data_source_type=..., config={...})",
            f"Reference: {DOC_URL}",
        ],
        metadata={"source": "local registry", "server_round_trip": False},
    )
