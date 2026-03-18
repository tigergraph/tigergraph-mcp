# Copyright 2025 TigerGraph Inc.
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


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class CreateDataSourceToolInput(BaseModel):
    """Input schema for creating a data source."""
    profile: Optional[str] = Field(None, description="Connection profile name. If not provided, uses TG_PROFILE env var or 'default'. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source.")
    data_source_type: str = Field(..., description="Type of data source: 's3', 'gcs', 'azure_blob', or 'local'.")
    config: Dict[str, Any] = Field(..., description="Configuration for the data source (e.g., bucket, credentials).")


class UpdateDataSourceToolInput(BaseModel):
    """Input schema for updating a data source."""
    profile: Optional[str] = Field(None, description="Connection profile name. If not provided, uses TG_PROFILE env var or 'default'. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source to update.")
    config: Dict[str, Any] = Field(..., description="Updated configuration for the data source.")


class GetDataSourceToolInput(BaseModel):
    """Input schema for getting a data source."""
    profile: Optional[str] = Field(None, description="Connection profile name. If not provided, uses TG_PROFILE env var or 'default'. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source.")


class DropDataSourceToolInput(BaseModel):
    """Input schema for dropping a data source."""
    profile: Optional[str] = Field(None, description="Connection profile name. If not provided, uses TG_PROFILE env var or 'default'. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source to drop.")


class GetAllDataSourcesToolInput(BaseModel):
    """Input schema for getting all data sources."""
    profile: Optional[str] = Field(None, description="Connection profile name. If not provided, uses TG_PROFILE env var or 'default'. Use 'list_connections' to see available profiles.")


class DropAllDataSourcesToolInput(BaseModel):
    """Input schema for dropping all data sources."""
    profile: Optional[str] = Field(None, description="Connection profile name. If not provided, uses TG_PROFILE env var or 'default'. Use 'list_connections' to see available profiles.")
    confirm: bool = Field(False, description="Must be True to confirm dropping all data sources.")


class PreviewSampleDataToolInput(BaseModel):
    """Input schema for previewing sample data."""
    profile: Optional[str] = Field(None, description="Connection profile name. If not provided, uses TG_PROFILE env var or 'default'. Use 'list_connections' to see available profiles.")
    data_source_name: str = Field(..., description="Name of the data source.")
    file_path: str = Field(..., description="Path to the file within the data source.")
    num_rows: int = Field(10, description="Number of sample rows to preview.")
    graph_name: Optional[str] = Field(None, description="Name of the graph context. If not provided, uses default connection.")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

create_data_source_tool = Tool(
    name=TigerGraphToolName.CREATE_DATA_SOURCE,
    description="Create a new data source for loading data (S3, GCS, Azure Blob, or local).",
    inputSchema=CreateDataSourceToolInput.model_json_schema(),
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
    """Create a new data source."""
    from ..response_formatter import format_success, format_error

    try:
        conn = get_connection(profile=profile)
        full_config = {"type": data_source_type.lower(), **config}
        result = await conn.createDataSource(dsName=data_source_name, config=full_config)
        result_str = result.get("message", str(result))

        return format_success(
            operation="create_data_source",
            summary=f"Data source '{data_source_name}' of type '{data_source_type}' created successfully",
            data={"data_source_name": data_source_name, "result": result_str},
            suggestions=[
                f"View data source: get_data_source(data_source_name='{data_source_name}')",
                "List all data sources: get_all_data_sources()",
            ],
        )
    except Exception as e:
        return format_error(
            operation="create_data_source",
            error=e,
            context={"data_source_name": data_source_name},
        )


async def update_data_source(
    data_source_name: str,
    config: Dict[str, Any],
    profile: Optional[str] = None,
) -> List[TextContent]:
    """Update an existing data source."""
    from ..response_formatter import format_success, format_error

    try:
        conn = get_connection(profile=profile)
        result = await conn.updateDataSource(dsName=data_source_name, config=config)
        result_str = result.get("message", str(result))

        return format_success(
            operation="update_data_source",
            summary=f"Data source '{data_source_name}' updated successfully",
            data={"data_source_name": data_source_name, "result": result_str},
        )
    except Exception as e:
        return format_error(
            operation="update_data_source",
            error=e,
            context={"data_source_name": data_source_name},
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
            data={"data_source_name": data_source_name, "details": result},
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
) -> List[TextContent]:
    """Drop a data source."""
    from ..response_formatter import format_success, format_error

    try:
        conn = get_connection(profile=profile)
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
            data={"details": result},
            suggestions=["Create a data source: create_data_source(...)"],
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
