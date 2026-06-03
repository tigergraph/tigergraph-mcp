"""Tests for tigergraph_mcp.tools.connection_tools."""

import os
import unittest
from unittest.mock import patch

from tests.mcp import MCPToolTestBase
from tigergraph_mcp.connection_manager import (
    ConnectionManager,
    SessionConnectionManager,
    use_session_manager,
)
from tigergraph_mcp.tools.connection_tools import (
    list_connections,
    show_connection,
    authenticate,
)


class TestListConnections(MCPToolTestBase):

    def setUp(self):
        super().setUp()
        ConnectionManager._profiles = set()
        ConnectionManager._connection_pool = {}
        ConnectionManager._default_connection = None

    @patch.dict(
        os.environ,
        {
            "TG_HOST": "http://default",
            "STAGING_TG_HOST": "http://staging",
        },
        clear=True,
    )
    async def test_lists_discovered_profiles(self):
        ConnectionManager.load_profiles()

        result = await list_connections()
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["count"], 2)
        profile_names = [p["profile"] for p in resp["data"]["profiles"]]
        self.assertIn("default", profile_names)
        self.assertIn("staging", profile_names)

    @patch.dict(os.environ, {}, clear=True)
    async def test_lists_default_only(self):
        ConnectionManager._profiles = set()
        result = await list_connections()
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["count"], 1)
        self.assertEqual(resp["data"]["profiles"][0]["profile"], "default")

    @patch.dict(
        os.environ,
        {
            "TG_HOST": "http://default",
            "STAGING_TG_HOST": "http://staging",
            "ANALYTICS_TG_HOST": "http://analytics",
        },
        clear=True,
    )
    async def test_three_profiles(self):
        ConnectionManager.load_profiles()
        result = await list_connections()
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["count"], 3)


class TestShowConnection(MCPToolTestBase):

    def setUp(self):
        super().setUp()
        ConnectionManager._profiles = set()
        ConnectionManager._connection_pool = {}
        ConnectionManager._default_connection = None

    @patch.dict(
        os.environ,
        {
            "TG_HOST": "http://my-host",
            "TG_USERNAME": "admin",
            "TG_GRAPHNAME": "MyGraph",
            "TG_PASSWORD": "secret123",
        },
        clear=True,
    )
    async def test_shows_default_profile(self):
        result = await show_connection()
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["host"], "http://my-host")
        self.assertEqual(resp["data"]["username"], "admin")
        self.assertEqual(resp["data"]["graphname"], "MyGraph")
        self.assertNotIn("password", resp["data"])

    @patch.dict(
        os.environ,
        {
            "STAGING_TG_HOST": "http://staging-host",
            "STAGING_TG_USERNAME": "stg_admin",
        },
        clear=True,
    )
    async def test_shows_named_profile(self):
        result = await show_connection(profile="staging")
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["host"], "http://staging-host")
        self.assertEqual(resp["data"]["username"], "stg_admin")
        self.assertEqual(resp["data"]["profile"], "staging")

    @patch.dict(
        os.environ,
        {"TG_HOST": "http://default", "TG_PROFILE": "default"},
        clear=True,
    )
    async def test_falls_back_to_tg_profile_env(self):
        result = await show_connection(profile=None)
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["profile"], "default")
        self.assertEqual(resp["data"]["host"], "http://default")


class TestAuthenticate(MCPToolTestBase):
    """Tests for the authenticate tool that registers session credentials."""

    def setUp(self):
        super().setUp()
        ConnectionManager._profiles = set()
        ConnectionManager._connection_pool = {}
        ConnectionManager._default_connection = None

    async def test_rejects_when_no_credentials(self):
        cm = SessionConnectionManager()
        with use_session_manager(cm):
            result = await authenticate(host="https://acme.example.com")
        self.assert_error(result)

    async def test_rejects_in_stdio_mode(self):
        # Without a bound SessionConnectionManager, authenticate must error.
        result = await authenticate(
            host="https://acme.example.com",
            api_token="tok",
        )
        self.assert_error(result)

    async def test_registers_token_credentials_into_session_pool(self):
        cm = SessionConnectionManager()
        with use_session_manager(cm):
            result = await authenticate(
                host="https://acme.example.com",
                api_token="my-token",
                graphname="MyGraph",
            )
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["host"], "https://acme.example.com")
        self.assertEqual(resp["data"]["auth_mode"], "token (API)")
        # The session's default connection should now exist and match the host.
        conn = cm.get_default_connection()
        self.assertIsNotNone(conn)
        self.assertIn("default", cm._connection_pool)
        # Process-global pool should be untouched.
        self.assertEqual(ConnectionManager._connection_pool, {})

    async def test_registers_password_credentials(self):
        cm = SessionConnectionManager()
        with use_session_manager(cm):
            result = await authenticate(
                host="https://acme.example.com",
                username="alice",
                password="secret",
            )
        resp = self.assert_success(result)
        self.assertEqual(resp["data"]["auth_mode"], "password")

    async def test_replaces_prior_credentials_in_same_session(self):
        cm = SessionConnectionManager()
        with use_session_manager(cm):
            await authenticate(host="https://first.example.com", api_token="t1")
            first_conn = cm.get_default_connection()
            await authenticate(host="https://second.example.com", api_token="t2")
            second_conn = cm.get_default_connection()
        self.assertIsNot(first_conn, second_conn)
        self.assertEqual(len(cm._connection_pool), 1)


if __name__ == "__main__":
    unittest.main()
