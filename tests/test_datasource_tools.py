"""Tests for tigergraph_mcp.tools.datasource_tools."""

import unittest
from unittest.mock import patch

from tests.mcp import MCPToolTestBase
from tigergraph_mcp.tools.datasource_tools import (
    create_data_source,
    get_data_source_types,
    drop_all_data_sources,
    drop_data_source,
    get_all_data_sources,
    get_data_source,
    preview_sample_data,
    update_data_source,
)

PATCH_TARGET = "tigergraph_mcp.tools.datasource_tools.get_connection"


class TestCreateDataSource(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.return_value = {"error": False, "message": "Successfully created data source"}

        result = await create_data_source(
            data_source_name="my_s3",
            data_source_type="s3",
            config={"access.key": "AKIA", "secret.key": "shh"},
        )
        resp = self.assert_success(result)
        self.assertIn("my_s3", resp["summary"])

    @patch(PATCH_TARGET)
    async def test_gsql_error(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.side_effect = Exception("Data source already exists")

        result = await create_data_source(
            data_source_name="dup", data_source_type="s3", config={}
        )
        self.assert_error(result)


class TestUpdateDataSource(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.updateDataSource.return_value = {"error": False, "message": "Data source updated"}

        result = await update_data_source(
            data_source_name="my_s3", config={"bucket": "new-bucket"}
        )
        self.assert_success(result)

    @patch(PATCH_TARGET)
    async def test_exception(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.updateDataSource.side_effect = Exception("Data source not found")

        result = await update_data_source(
            data_source_name="nope", config={}
        )
        self.assert_error(result)


class TestGetDataSource(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getDataSource.return_value = {"name": "my_s3", "type": "S3"}

        result = await get_data_source(data_source_name="my_s3")
        resp = self.assert_success(result)
        self.assertIn("my_s3", resp["summary"])

    @patch(PATCH_TARGET)
    async def test_not_found(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getDataSource.side_effect = Exception("Data source 'nope' does not exist")

        result = await get_data_source(data_source_name="nope")
        self.assert_error(result)


class TestDropDataSource(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.dropDataSource.return_value = {"error": False, "message": "Successfully dropped data source"}

        result = await drop_data_source(data_source_name="old_ds")
        self.assert_success(result)

    @patch(PATCH_TARGET)
    async def test_exception(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.dropDataSource.side_effect = Exception("Data source does not exist")

        result = await drop_data_source(data_source_name="nope")
        self.assert_error(result)


class TestGetAllDataSources(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getDataSources.return_value = [{"name": "s3_1"}, {"name": "local_1"}]

        result = await get_all_data_sources()
        self.assert_success(result)

    @patch(PATCH_TARGET)
    async def test_exception(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getDataSources.side_effect = Exception("connection error")

        result = await get_all_data_sources()
        self.assert_error(result)


class TestDropAllDataSources(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_requires_confirm(self, mock_gc):
        mock_gc.return_value = self.mock_conn

        result = await drop_all_data_sources(confirm=False)
        self.assert_error(result)

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.dropAllDataSources.return_value = {"error": False, "message": "All data sources dropped"}

        result = await drop_all_data_sources(confirm=True)
        self.assert_success(result)

    @patch(PATCH_TARGET)
    async def test_exception(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.dropAllDataSources.side_effect = Exception("permission denied")

        result = await drop_all_data_sources(confirm=True)
        self.assert_error(result)


class TestPreviewSampleData(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.previewSampleData.return_value = "col1|col2\nval1|val2"

        result = await preview_sample_data(
            data_source_name="my_s3",
            file_path="/data/sample.csv",
            num_rows=5,
        )
        resp = self.assert_success(result)
        self.assertIn("5", resp["summary"])

    @patch(PATCH_TARGET)
    async def test_file_not_found(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.previewSampleData.side_effect = Exception("File does not exist")

        result = await preview_sample_data(
            data_source_name="my_s3", file_path="/no/file.csv"
        )
        self.assert_error(result)


class TestProfilePropagation(MCPToolTestBase):
    """Verify profile is forwarded to get_connection for datasource tools."""

    @patch(PATCH_TARGET)
    async def test_create_data_source_with_profile(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.return_value = {"error": False, "message": "Successfully created data source"}

        result = await create_data_source(
            data_source_name="my_s3",
            data_source_type="s3",
            config={"access.key": "AKIA", "secret.key": "shh"},
            profile="staging",
        )
        self.assert_success(result)
        mock_gc.assert_called_with(profile="staging")

    @patch(PATCH_TARGET)
    async def test_get_all_data_sources_with_profile(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getDataSources.return_value = []

        result = await get_all_data_sources(profile="analytics")
        mock_gc.assert_called_with(profile="analytics")


SNOWFLAKE_URL = (
    "jdbc:snowflake:/https:/ab12345.snowflakecomputing.com/"
    "?db=MYDB&schema=PUBLIC&role=LOADER"
)
SNOWFLAKE_CONFIG = {
    "connection.url": SNOWFLAKE_URL,
    "connection.user": "tg_loader",
    "connection.password": "s3cr3t",
}


class TestCreateSnowflakeDataSource(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success_sends_type_and_full_config(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.return_value = {"error": False, "message": "created"}

        result = await create_data_source(
            data_source_name="sf1",
            data_source_type="snowflake",
            config=dict(SNOWFLAKE_CONFIG),
        )
        self.assert_success(result)
        sent = self.mock_conn.createDataSource.call_args.kwargs["config"]
        self.assertEqual(sent, {"type": "snowflake", **SNOWFLAKE_CONFIG})

    @patch(PATCH_TARGET)
    async def test_type_name_is_case_insensitive(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.return_value = {"error": False, "message": "created"}

        await create_data_source(
            data_source_name="sf1",
            data_source_type="SnowFlake",
            config=dict(SNOWFLAKE_CONFIG),
        )
        self.assertEqual(
            self.mock_conn.createDataSource.call_args.kwargs["config"]["type"], "snowflake"
        )

    @patch(PATCH_TARGET)
    async def test_password_is_masked_in_the_response(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.return_value = {"error": False, "message": "created"}

        result = await create_data_source(
            data_source_name="sf1",
            data_source_type="snowflake",
            config=dict(SNOWFLAKE_CONFIG),
        )
        self.assertNotIn("s3cr3t", result[0].text)

    @patch(PATCH_TARGET)
    async def test_incomplete_config_is_still_sent_to_the_server(self, mock_gc):
        # TigerGraph decides what it accepts; the client never pre-empts it.
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.side_effect = Exception(
            'Semantic Check Fails: "connection.url" is not found as STRING'
        )

        result = await create_data_source(
            data_source_name="sf1",
            data_source_type="snowflake",
            config={"connection.user": "tg_loader"},
        )
        self.assert_error(result)
        self.mock_conn.createDataSource.assert_called_once()

    @patch(PATCH_TARGET)
    async def test_server_rejection_is_enriched_with_key_guidance(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.side_effect = Exception(
            'Semantic Check Fails: "connection.url" is not found as STRING'
        )

        result = await create_data_source(
            data_source_name="sf1",
            data_source_type="snowflake",
            config={"connection.user": "tg_loader"},
        )
        text = result[0].text
        # The server's own words survive, with our key list added.
        self.assertIn("Semantic Check Fails", text)
        self.assertIn("Required keys for Snowflake", text)

    @patch(PATCH_TARGET)
    async def test_unknown_type_is_forwarded_not_blocked(self, mock_gc):
        # A type this table does not know may still be valid on a newer server.
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.return_value = {"error": False, "message": "created"}

        result = await create_data_source(
            data_source_name="x", data_source_type="redshift", config={"host": "h"}
        )
        self.assert_success(result)
        self.assertEqual(
            self.mock_conn.createDataSource.call_args.kwargs["config"]["type"], "redshift"
        )

    @patch(PATCH_TARGET)
    async def test_databricks_reaches_the_server_and_its_error_is_explained(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.side_effect = Exception(
            'SemanticException: "type" must be one of following: KAFKA, S3, SNOWFLAKE'
        )

        result = await create_data_source(
            data_source_name="dbx", data_source_type="databricks", config={}
        )
        self.assert_error(result)
        self.mock_conn.createDataSource.assert_called_once()
        self.assertIn("get_data_source_types", result[0].text)

    @patch(PATCH_TARGET)
    async def test_config_type_key_does_not_override_the_argument(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.return_value = {"error": False, "message": "created"}

        await create_data_source(
            data_source_name="sf1",
            data_source_type="snowflake",
            config={**SNOWFLAKE_CONFIG, "type": "s3"},
        )
        self.assertEqual(
            self.mock_conn.createDataSource.call_args.kwargs["config"]["type"], "snowflake"
        )

    @patch(PATCH_TARGET)
    async def test_azure_blob_alias_is_sent_as_abs(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.createDataSource.return_value = {"error": False, "message": "created"}

        await create_data_source(
            data_source_name="az",
            data_source_type="azure_blob",
            config={"client.id": "c", "client.secret": "s", "tenant.id": "t"},
        )
        self.assertEqual(
            self.mock_conn.createDataSource.call_args.kwargs["config"]["type"], "abs"
        )


class TestRedactionOnRead(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_get_data_source_masks_password(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getDataSource.return_value = {
            "name": "sf1", "type": "snowflake", **SNOWFLAKE_CONFIG
        }

        result = await get_data_source(data_source_name="sf1")
        self.assert_success(result)
        self.assertNotIn("s3cr3t", result[0].text)

    @patch(PATCH_TARGET)
    async def test_get_all_data_sources_masks_password(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getDataSources.return_value = [
            {"name": "sf1", "type": "snowflake", **SNOWFLAKE_CONFIG}
        ]

        result = await get_all_data_sources()
        self.assert_success(result)
        self.assertNotIn("s3cr3t", result[0].text)


class TestUpdateDataSourceValidation(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_partial_update_is_sent_and_its_error_explained(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.updateDataSource.side_effect = Exception(
            'Semantic Check Fails: "connection.url" is not found as STRING'
        )

        result = await update_data_source(
            data_source_name="sf1",
            config={"connection.user": "new_user"},
            data_source_type="snowflake",
        )
        self.assert_error(result)
        self.mock_conn.updateDataSource.assert_called_once()
        self.assertIn("replaces the whole configuration", result[0].text)

    @patch(PATCH_TARGET)
    async def test_untyped_update_is_passed_through(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.updateDataSource.return_value = {"error": False, "message": "updated"}

        result = await update_data_source(
            data_source_name="my_s3", config={"bucket": "new-bucket"}
        )
        self.assert_success(result)
        self.mock_conn.updateDataSource.assert_called_once()

    @patch(PATCH_TARGET)
    async def test_type_inside_config_is_normalized(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.updateDataSource.return_value = {"error": False, "message": "updated"}

        await update_data_source(
            data_source_name="az", config={"type": "azure_blob", "client.id": "c"}
        )
        self.assertEqual(
            self.mock_conn.updateDataSource.call_args.kwargs["config"]["type"], "abs"
        )


class TestGetDataSourceTypes(MCPToolTestBase):

    async def test_lists_types_without_a_connection(self):
        result = await get_data_source_types()
        resp = self.assert_success(result)
        types = [t["type"] for t in resp["data"]["types"]]
        self.assertIn("snowflake", types)
        self.assertIn("s3", types)

    async def test_family_filter_returns_only_warehouses(self):
        result = await get_data_source_types(family="warehouse")
        resp = self.assert_success(result)
        self.assertEqual(
            [t["type"] for t in resp["data"]["types"]],
            ["snowflake", "bigquery", "postgresql"],
        )

    async def test_unknown_family_is_an_error(self):
        result = await get_data_source_types(family="nosuchfamily")
        self.assert_error(result)


if __name__ == "__main__":
    unittest.main()
