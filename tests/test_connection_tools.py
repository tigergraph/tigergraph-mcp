"""Tests for tigergraph_mcp.tools.connection_tools."""

import os
import unittest
from unittest import mock
from unittest.mock import patch

from tests.mcp import MCPToolTestBase
from tigergraph_mcp.connection_manager import (
    ConnectionManager,
    SessionConnectionManager,
    get_connection,
    use_session_manager,
)
from pyTigerGraph import AsyncTigerGraphConnection

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
        # authenticate probes TigerGraph when it creates the connection; these
        # tests cover registration, not the probe.
        patcher = mock.patch(
            "tigergraph_mcp.tools.connection_tools.validate_connection",
            mock.AsyncMock(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
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


class TestAuthenticateTargetsTheDefaultProfile(unittest.IsolatedAsyncioTestCase):
    """authenticate must write to whichever profile "default" resolves to, or a
    tool call that omits the profile would not see the new credentials."""

    def setUp(self):
        # authenticate probes TigerGraph when it creates the connection; these
        # tests are about which profile is updated, not the probe.
        patcher = mock.patch(
            "tigergraph_mcp.tools.connection_tools.validate_connection",
            mock.AsyncMock(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    async def _authenticate_into(self, default_profile):
        env = {"TG_DEFAULT_PROFILE": default_profile or ""}
        slot = default_profile or "default"
        with mock.patch.dict(os.environ, env, clear=False):
            cm = SessionConnectionManager()
            cm.register_connection(slot, AsyncTigerGraphConnection(
                host="http://established", username="established", password="pw"))
            with use_session_manager(cm):
                result = await authenticate(
                    host="http://authenticated", username="alice", password="s3cr3t")
                conn = get_connection()
            return result, cm, conn

    async def test_with_an_explicit_default_profile(self):
        result, cm, conn = await self._authenticate_into("staging")
        self.assertIn('"success": true', result[0].text)
        self.assertEqual(sorted(cm._connection_pool), ["staging"])
        self.assertEqual(conn.host, "http://authenticated")

    async def test_with_no_default_profile_configured(self):
        result, cm, conn = await self._authenticate_into(None)
        self.assertIn('"success": true', result[0].text)
        self.assertEqual(sorted(cm._connection_pool), ["default"])
        self.assertEqual(conn.host, "http://authenticated")

    async def test_the_replaced_profile_is_reported(self):
        result, _, _ = await self._authenticate_into("staging")
        self.assertIn("staging", result[0].text)

    async def test_it_does_not_add_a_second_slot(self):
        _, cm, _ = await self._authenticate_into("staging")
        self.assertEqual(len(cm._connection_pool), 1)


class TestAuthenticateTargetsOneProfile(unittest.IsolatedAsyncioTestCase):
    """Naming a profile must replace only that connection."""

    def setUp(self):
        # authenticate probes TigerGraph when it creates the connection; these
        # tests are about which profile is updated, not the probe.
        patcher = mock.patch(
            "tigergraph_mcp.tools.connection_tools.validate_connection",
            mock.AsyncMock(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    ENV = {
        "TG_DEFAULT_PROFILE": "staging",
        "STAGING_TG_HOST": "http://staging", "STAGING_TG_USERNAME": "su",
        "STAGING_TG_PASSWORD": "pw",
        "PROD_TG_HOST": "http://prod", "PROD_TG_USERNAME": "pu",
        "PROD_TG_PASSWORD": "pw",
    }

    async def _session(self):
        cm = SessionConnectionManager()
        cm.register_connection("staging", AsyncTigerGraphConnection(
            host="http://staging", username="su", password="pw"))
        cm.register_connection("prod", AsyncTigerGraphConnection(
            host="http://prod", username="pu", password="pw"), as_default=False)
        return cm

    async def test_named_profile_is_replaced(self):
        with mock.patch.dict(os.environ, self.ENV, clear=False):
            cm = await self._session()
            with use_session_manager(cm):
                await authenticate(host="http://new-prod", profile="prod",
                                   username="alice", password="s3cr3t")
                self.assertEqual(get_connection(profile="prod").host, "http://new-prod")

    async def test_other_profiles_are_untouched(self):
        with mock.patch.dict(os.environ, self.ENV, clear=False):
            cm = await self._session()
            with use_session_manager(cm):
                await authenticate(host="http://new-prod", profile="prod",
                                   username="alice", password="s3cr3t")
                self.assertEqual(get_connection().host, "http://staging")

    async def test_naming_the_default_profile_replaces_the_default(self):
        with mock.patch.dict(os.environ, self.ENV, clear=False):
            cm = await self._session()
            with use_session_manager(cm):
                await authenticate(host="http://new-staging", profile="staging",
                                   username="alice", password="s3cr3t")
                self.assertEqual(get_connection().host, "http://new-staging")

    async def test_passing_default_resolves_to_the_default_profile(self):
        with mock.patch.dict(os.environ, self.ENV, clear=False):
            cm = await self._session()
            with use_session_manager(cm):
                result = await authenticate(host="http://new", profile="default",
                                            username="alice", password="s3cr3t")
                self.assertIn("staging", result[0].text)
                self.assertEqual(get_connection().host, "http://new")

    async def test_the_pool_does_not_grow(self):
        with mock.patch.dict(os.environ, self.ENV, clear=False):
            cm = await self._session()
            with use_session_manager(cm):
                await authenticate(host="http://new-prod", profile="prod",
                                   username="alice", password="s3cr3t")
            self.assertEqual(sorted(cm._connection_pool), ["prod", "staging"])


class TestAuthenticateValidates(unittest.IsolatedAsyncioTestCase):
    """Credentials are proven where the connection is created, as they are for
    header-supplied credentials in HTTP mode."""

    def setUp(self):
        self.cm = SessionConnectionManager()
        self.existing = AsyncTigerGraphConnection(
            host="http://existing", username="existing", password="pw")
        self.cm.register_connection("default", self.existing)

    async def _authenticate(self, validator):
        with mock.patch.dict(os.environ, {"TG_DEFAULT_PROFILE": ""}, clear=False):
            with mock.patch(
                "tigergraph_mcp.tools.connection_tools.validate_connection",
                validator,
            ):
                with use_session_manager(self.cm):
                    return await authenticate(
                        host="http://new", username="alice", password="s3cr3t")

    async def test_valid_credentials_are_registered(self):
        result = await self._authenticate(mock.AsyncMock())
        self.assertIn('"success": true', result[0].text)
        self.assertEqual(self.cm._connection_pool["default"].host, "http://new")

    async def test_the_connection_is_probed(self):
        validator = mock.AsyncMock()
        await self._authenticate(validator)
        validator.assert_awaited_once()

    async def test_rejected_credentials_report_failure(self):
        result = await self._authenticate(
            mock.AsyncMock(side_effect=Exception("User authentication failed")))
        self.assertIn('"success": false', result[0].text)
        self.assertIn("rejected the credentials", result[0].text)

    async def test_rejected_credentials_leave_the_existing_connection(self):
        # Replacing a working connection with a broken one would strand the
        # session; the prior connection must survive a failed authenticate.
        await self._authenticate(mock.AsyncMock(side_effect=Exception("nope")))
        self.assertIs(self.cm._connection_pool["default"], self.existing)

    async def test_an_unreachable_host_is_reported(self):
        result = await self._authenticate(
            mock.AsyncMock(side_effect=OSError("Cannot connect to host")))
        self.assertIn('"success": false', result[0].text)


if __name__ == "__main__":
    unittest.main()
