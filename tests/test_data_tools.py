"""Tests for tigergraph_mcp.tools.data_tools."""

import unittest
from unittest.mock import patch

from tests.mcp import MCPToolTestBase
from tigergraph_mcp.tools.data_tools import (
    _generate_loading_job_gsql,
    _validate_file_configs,
    create_loading_job,
    drop_loading_job,
    get_loading_jobs,
    get_loading_job_status,
    run_loading_job_with_data,
    run_loading_job_with_file,
)

PATCH_TARGET = "tigergraph_mcp.tools.data_tools.get_connection"


class TestGenerateLoadingJobGsql(unittest.TestCase):
    """Pure-function tests for GSQL generation logic."""

    def test_node_mapping(self):
        gsql_str = _generate_loading_job_gsql(
            graph_name="G",
            job_name="load_people",
            files=[{
                "file_alias": "f1",
                "file_path": "/data/people.csv",
                "node_mappings": [
                    {
                        "vertex_type": "Person",
                        "attribute_mappings": {"id": 0, "name": 1, "age": 2},
                    }
                ],
            }],
        )
        self.assertIn("CREATE LOADING JOB load_people", gsql_str)
        self.assertIn("Person", gsql_str)
        self.assertIn("$0", gsql_str)
        self.assertIn("$1", gsql_str)

    def test_edge_mapping(self):
        gsql_str = _generate_loading_job_gsql(
            graph_name="G",
            job_name="load_follows",
            files=[{
                "file_alias": "f1",
                "file_path": "/data/follows.csv",
                "edge_mappings": [
                    {
                        "edge_type": "FOLLOWS",
                        "source_column": 0,
                        "target_column": 1,
                    }
                ],
            }],
        )
        self.assertIn("CREATE LOADING JOB load_follows", gsql_str)
        self.assertIn("FOLLOWS", gsql_str)
        self.assertIn("$0", gsql_str)
        self.assertIn("$1", gsql_str)

    def test_header_columns(self):
        gsql_str = _generate_loading_job_gsql(
            graph_name="G",
            job_name="load_h",
            files=[{
                "file_alias": "f",
                "file_path": "/data/h.csv",
                "header": "true",
                "node_mappings": [
                    {
                        "vertex_type": "V",
                        "attribute_mappings": {"id": "id", "name": "name"},
                    }
                ],
            }],
        )
        self.assertIn("HEADER", gsql_str)
        self.assertIn('$"id"', gsql_str)

    def test_custom_separator(self):
        gsql_str = _generate_loading_job_gsql(
            graph_name="G",
            job_name="tsv_job",
            files=[{
                "file_alias": "f",
                "file_path": "/data/tab.tsv",
                "separator": "\\t",
                "node_mappings": [
                    {"vertex_type": "V", "attribute_mappings": {"id": 0}}
                ],
            }],
        )
        self.assertIn("\\t", gsql_str)

    def test_mixed_vertex_and_edge(self):
        gsql_str = _generate_loading_job_gsql(
            graph_name="G",
            job_name="mixed",
            files=[{
                "file_alias": "f",
                "file_path": "/data/m.csv",
                "node_mappings": [
                    {"vertex_type": "Person", "attribute_mappings": {"id": 0, "name": 1}}
                ],
                "edge_mappings": [
                    {
                        "edge_type": "KNOWS",
                        "source_column": 0,
                        "target_column": 2,
                    }
                ],
            }],
        )
        self.assertIn("Person", gsql_str)
        self.assertIn("KNOWS", gsql_str)
        self.assertIn("$0", gsql_str)
        self.assertIn("$2", gsql_str)


class TestCreateLoadingJob(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.gsql.return_value = "Successfully created loading job"

        result = await create_loading_job(
            job_name="load_test",
            files=[{
                "file_alias": "f1",
                "file_path": "/data/test.csv",
                "node_mappings": [
                    {"vertex_type": "Person", "attribute_mappings": {"id": 0, "name": 1}}
                ],
            }],
        )
        resp = self.assert_success(result)
        self.assertIn("load_test", resp["summary"])

    @patch(PATCH_TARGET)
    async def test_with_run(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.gsql.return_value = "Successfully created and ran"

        result = await create_loading_job(
            job_name="load_run",
            files=[{
                "file_alias": "f1",
                "node_mappings": [
                    {"vertex_type": "V", "attribute_mappings": {"id": 0}}
                ],
            }],
            run_job=True,
        )
        resp = self.assert_success(result)
        gsql_arg = self.mock_conn.gsql.call_args[0][0]
        self.assertIn("RUN LOADING JOB load_run", gsql_arg)

    @patch(PATCH_TARGET)
    async def test_with_drop_after_run(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.gsql.return_value = "Successfully created, ran, and dropped"

        result = await create_loading_job(
            job_name="load_drop",
            files=[{
                "file_alias": "f1",
                "node_mappings": [
                    {"vertex_type": "V", "attribute_mappings": {"id": 0}}
                ],
            }],
            run_job=True,
            drop_after_run=True,
        )
        resp = self.assert_success(result)
        gsql_arg = self.mock_conn.gsql.call_args[0][0]
        self.assertIn("DROP JOB load_drop", gsql_arg)

    @patch(PATCH_TARGET)
    async def test_gsql_error(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.gsql.return_value = "SEMANTIC ERROR: bad schema"

        result = await create_loading_job(
            job_name="bad",
            files=[{
                "file_alias": "f",
                "node_mappings": [
                    {"vertex_type": "V", "attribute_mappings": {"id": 0}}
                ],
            }],
        )
        self.assert_error(result)


class TestRunLoadingJobWithFile(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runLoadingJobWithFile.return_value = {"loaded": 500}

        result = await run_loading_job_with_file(
            job_name="my_job",
            file_path="/data/file.csv",
            file_tag="f1",
        )
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["result"]["loaded"], 500)

    @patch(PATCH_TARGET)
    async def test_no_result(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runLoadingJobWithFile.return_value = None

        result = await run_loading_job_with_file(
            job_name="my_job",
            file_path="/data/file.csv",
            file_tag="f1",
        )
        self.assert_error(result)

    @patch(PATCH_TARGET)
    async def test_exception(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runLoadingJobWithFile.side_effect = Exception("file not found")

        result = await run_loading_job_with_file(
            job_name="my_job",
            file_path="/missing.csv",
            file_tag="f1",
        )
        self.assert_error(result)


class TestRunLoadingJobWithData(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runLoadingJobWithData.return_value = {"loaded": 3}

        result = await run_loading_job_with_data(
            job_name="inline_job",
            data="v1,Alice\nv2,Bob",
            file_tag="f1",
        )
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["result"]["loaded"], 3)

    @patch(PATCH_TARGET)
    async def test_exception(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runLoadingJobWithData.side_effect = Exception("parse error")

        result = await run_loading_job_with_data(
            job_name="bad",
            data="garbage",
            file_tag="f1",
        )
        self.assert_error(result)


class TestGetLoadingJobs(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_with_results(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getLoadingJobs.return_value = [
            {"jobName": "load_people"},
            {"jobName": "load_orders"},
        ]

        result = await get_loading_jobs()
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["count"], 2)

    @patch(PATCH_TARGET)
    async def test_empty(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getLoadingJobs.return_value = []

        result = await get_loading_jobs()
        self.assert_success(result)

    @patch(PATCH_TARGET)
    async def test_exception(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getLoadingJobs.side_effect = Exception("connection error")

        result = await get_loading_jobs()
        self.assert_error(result)


class TestGetLoadingJobStatus(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_with_status(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getLoadingJobStatus.return_value = {
            "status": "RUNNING",
            "progress": "50%",
        }

        result = await get_loading_job_status(job_id="job_123")
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["job_id"], "job_123")

    @patch(PATCH_TARGET)
    async def test_no_status(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getLoadingJobStatus.return_value = None

        result = await get_loading_job_status(job_id="missing_job")
        self.assert_error(result)

    @patch(PATCH_TARGET)
    async def test_exception(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.getLoadingJobStatus.side_effect = Exception("invalid job id")

        result = await get_loading_job_status(job_id="bad")
        self.assert_error(result)


class TestDropLoadingJob(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_success(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.dropLoadingJob.return_value = "OK"

        result = await drop_loading_job(job_name="old_job")
        self.assert_success(result)

    @patch(PATCH_TARGET)
    async def test_not_found(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.dropLoadingJob.side_effect = Exception(
            "Loading job 'old_job' does not exist"
        )

        result = await drop_loading_job(job_name="old_job")
        self.assert_error(result)


class TestProfilePropagation(MCPToolTestBase):
    """Verify profile is forwarded to get_connection for data tools."""

    @patch(PATCH_TARGET)
    async def test_create_loading_job_with_profile(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.gsql.return_value = "Successfully created loading job"

        result = await create_loading_job(
            job_name="load_people",
            files=[{
                "file_alias": "f1",
                "file_path": "/data/people.csv",
                "node_mappings": [{"vertex_type": "Person", "attribute_mappings": {"id": 0}}],
            }],
            profile="staging",
            graph_name="StgGraph",
        )
        self.assert_success(result)
        mock_gc.assert_called_with(profile="staging", graph_name="StgGraph")

    @patch(PATCH_TARGET)
    async def test_run_loading_job_with_profile(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.runLoadingJobWithFile.return_value = {"statistics": {}}

        result = await run_loading_job_with_file(
            job_name="load_people",
            file_path="/data/people.csv",
            file_tag="f1",
            profile="analytics",
        )
        mock_gc.assert_called_with(profile="analytics", graph_name=None)


class TestWarehouseLoadingJobGsql(unittest.TestCase):
    """A file entry backed by a data source query instead of a path."""

    WAREHOUSE_FILE = {
        "file_alias": "f_person",
        "data_source": "sf1",
        "query": "SELECT id, name FROM MYDB.PUBLIC.PERSON",
        "separator": "|",
        "node_mappings": [
            {"vertex_type": "Person", "attribute_mappings": {"id": 0, "name": 1}}
        ],
    }

    def test_define_filename_uses_the_data_source_query_form(self):
        gsql = _generate_loading_job_gsql("G", "load_sf", [self.WAREHOUSE_FILE])
        self.assertIn(
            'DEFINE FILENAME f_person = "$sf1:SELECT id, name FROM MYDB.PUBLIC.PERSON";',
            gsql,
        )

    def test_using_clause_omits_header_and_eol(self):
        gsql = _generate_loading_job_gsql("G", "load_sf", [self.WAREHOUSE_FILE])
        self.assertIn('USING SEPARATOR="|"', gsql)
        self.assertNotIn("HEADER", gsql)
        self.assertNotIn("EOL", gsql)

    def test_columns_are_positional(self):
        gsql = _generate_loading_job_gsql("G", "load_sf", [self.WAREHOUSE_FILE])
        self.assertIn("TO VERTEX Person VALUES($0, $1)", gsql)

    def test_file_backed_entry_keeps_header_and_eol(self):
        gsql = _generate_loading_job_gsql("G", "load_csv", [{
            "file_alias": "f1",
            "file_path": "/data/people.csv",
            "node_mappings": [
                {"vertex_type": "Person", "attribute_mappings": {"id": 0}}
            ],
        }])
        self.assertIn("HEADER=", gsql)
        self.assertIn("EOL=", gsql)

    def test_mixed_file_and_warehouse_entries_in_one_job(self):
        gsql = _generate_loading_job_gsql("G", "mixed", [
            self.WAREHOUSE_FILE,
            {
                "file_alias": "f_csv",
                "file_path": "/data/extra.csv",
                "node_mappings": [
                    {"vertex_type": "Extra", "attribute_mappings": {"id": 0}}
                ],
            },
        ])
        self.assertIn('DEFINE FILENAME f_person = "$sf1:', gsql)
        self.assertIn('DEFINE FILENAME f_csv = "/data/extra.csv";', gsql)


class TestValidateFileConfigs(unittest.TestCase):

    def test_valid_warehouse_entry(self):
        self.assertEqual(_validate_file_configs([{
            "file_alias": "f",
            "data_source": "sf1",
            "query": "SELECT id FROM T",
            "node_mappings": [{"vertex_type": "P", "attribute_mappings": {"id": 0}}],
        }]), [])

    def test_valid_file_entry(self):
        self.assertEqual(
            _validate_file_configs([{"file_alias": "f", "file_path": "/a.csv"}]), []
        )

    def test_runtime_data_entry_needs_neither(self):
        self.assertEqual(_validate_file_configs([{"file_alias": "f"}]), [])

    def test_data_source_and_file_path_conflict(self):
        errors = _validate_file_configs([{
            "file_alias": "f", "file_path": "/a.csv",
            "data_source": "sf1", "query": "SELECT 1",
        }])
        self.assertTrue(any("both" in e for e in errors))

    def test_data_source_without_query(self):
        errors = _validate_file_configs([{"file_alias": "f", "data_source": "sf1"}])
        self.assertTrue(any("no 'query'" in e for e in errors))

    def test_query_without_data_source(self):
        errors = _validate_file_configs([{"file_alias": "f", "query": "SELECT 1"}])
        self.assertTrue(any("no 'data_source'" in e for e in errors))

    def test_named_columns_rejected_for_warehouse_node_mapping(self):
        errors = _validate_file_configs([{
            "file_alias": "f", "data_source": "sf1", "query": "SELECT id FROM T",
            "node_mappings": [
                {"vertex_type": "P", "attribute_mappings": {"id": "user_id"}}
            ],
        }])
        self.assertTrue(any("user_id" in e for e in errors))

    def test_named_columns_rejected_for_warehouse_edge_endpoints(self):
        errors = _validate_file_configs([{
            "file_alias": "f", "data_source": "sf1", "query": "SELECT a, b FROM T",
            "edge_mappings": [
                {"edge_type": "KNOWS", "source_column": "from_id", "target_column": 1}
            ],
        }])
        self.assertTrue(any("from_id" in e for e in errors))

    def test_named_columns_allowed_for_file_backed_entry(self):
        self.assertEqual(_validate_file_configs([{
            "file_alias": "f", "file_path": "/a.csv",
            "node_mappings": [
                {"vertex_type": "P", "attribute_mappings": {"id": "user_id"}}
            ],
        }]), [])


class TestCreateLoadingJobWarehouseValidation(MCPToolTestBase):

    @patch(PATCH_TARGET)
    async def test_invalid_entry_fails_without_calling_the_server(self, mock_gc):
        mock_gc.return_value = self.mock_conn

        result = await create_loading_job(
            job_name="bad",
            files=[{"file_alias": "f", "data_source": "sf1"}],
        )
        self.assert_error(result)
        self.mock_conn.gsql.assert_not_called()

    @patch(PATCH_TARGET)
    async def test_warehouse_job_is_created(self, mock_gc):
        mock_gc.return_value = self.mock_conn
        self.mock_conn.gsql.return_value = "Successfully created loading jobs: [load_sf]."

        result = await create_loading_job(
            job_name="load_sf",
            files=[{
                "file_alias": "f_person",
                "data_source": "sf1",
                "query": "SELECT id, name FROM MYDB.PUBLIC.PERSON",
                "node_mappings": [
                    {"vertex_type": "Person", "attribute_mappings": {"id": 0, "name": 1}}
                ],
            }],
        )
        self.assert_success(result)
        self.assertIn("$sf1:SELECT", self.mock_conn.gsql.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
