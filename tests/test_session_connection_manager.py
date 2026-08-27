"""Tests for SessionConnectionManager and the active-manager ContextVar.

These cover the M2 refactor: each session gets its own connection pool
and the module-level ``get_connection()`` resolves to the active session
manager when one is bound via ``use_session_manager``.
"""

import asyncio
import os
import unittest
from unittest import mock

from pyTigerGraph import AsyncTigerGraphConnection

from tigergraph_mcp.connection_manager import (
    ConnectionManager,
    SessionConnectionManager,
    get_active_manager,
    get_connection,
    reset_pending_credentials,
    resolve_profile_name,
    set_pending_credentials,
    use_session_manager,
)


def _conn(host: str = "http://tg.example") -> AsyncTigerGraphConnection:
    """A connection object stand-in; constructing one contacts nothing."""
    return AsyncTigerGraphConnection(host=host, username="u", password="p")


class TestSessionConnectionManagerBasics(unittest.TestCase):
    def setUp(self):
        # Reset the process-global so tests don't leak state into each other.
        ConnectionManager._profiles = set()
        ConnectionManager._connection_pool = {}
        ConnectionManager._default_connection = None

    def test_fresh_instance_has_empty_state(self):
        cm = SessionConnectionManager()
        self.assertEqual(cm._connection_pool, {})
        self.assertEqual(cm._profiles, set())
        self.assertIsNone(cm.get_default_connection())

    def test_list_profiles_seeds_default(self):
        cm = SessionConnectionManager()
        self.assertEqual(cm.list_profiles(), ["default"])

    @mock.patch.dict(
        os.environ,
        {"STAGING_TG_HOST": "https://staging.example.com"},
        clear=False,
    )
    @mock.patch("tigergraph_mcp.connection_manager._load_env_file")
    def test_load_profiles_discovers_named_profile(self, _load):
        cm = SessionConnectionManager()
        cm.load_profiles()
        self.assertIn("staging", cm.list_profiles())
        self.assertIn("default", cm.list_profiles())

    def test_get_connection_for_profile_caches(self):
        cm = SessionConnectionManager()
        cm.register_connection("default", _conn())
        conn1 = cm.get_connection_for_profile("default")
        conn2 = cm.get_connection_for_profile("default")
        self.assertIs(conn1, conn2)

    def test_default_profile_sets_default_connection(self):
        cm = SessionConnectionManager()
        conn = _conn()
        cm.register_connection("default", conn)
        self.assertIs(cm.get_default_connection(), conn)

    def test_undefined_profile_is_refused(self):
        cm = SessionConnectionManager()
        with self.assertRaises(ValueError) as ctx:
            cm.get_connection_for_profile("nosuchprofile")
        self.assertIn("Unknown profile", str(ctx.exception))

    @mock.patch.dict(
        os.environ,
        {"REPORTS_TG_HOST": "https://reports.example.com"},
        clear=False,
    )
    def test_profile_with_no_credentials_anywhere_is_refused(self):
        # A profile inherits the unprefixed credentials; with none configured
        # anywhere there is no identity to connect as.
        with mock.patch.dict(os.environ, {"TG_USERNAME": "", "TG_PASSWORD": "",
                                          "TG_API_TOKEN": "", "TG_JWT_TOKEN": ""}):
            cm = SessionConnectionManager()
            with self.assertRaises(ValueError) as ctx:
                cm.get_connection_for_profile("reports")
        self.assertIn("defines no credentials", str(ctx.exception))

    @mock.patch.dict(
        os.environ,
        {
            "REPORTS_TG_HOST": "https://reports.example.com",
            "REPORTS_TG_USERNAME": "reader",
            "REPORTS_TG_PASSWORD": "pw",
        },
        clear=False,
    )
    def test_named_profile_opens_lazily_in_the_session(self):
        # Naming a configured profile creates that connection inside this
        # session's own pool, as it does for a stdio process.
        cm = SessionConnectionManager()
        cm.register_connection("demo", _conn("http://demo.tg"))
        conn = cm.get_connection_for_profile("reports")
        self.assertEqual(conn.host, "https://reports.example.com")
        self.assertEqual(sorted(cm._connection_pool), ["demo", "reports"])

    @mock.patch.dict(
        os.environ,
        {
            "REPORTS_TG_HOST": "https://reports.example.com",
            "REPORTS_TG_USERNAME": "reader",
            "REPORTS_TG_PASSWORD": "pw",
        },
        clear=False,
    )
    def test_opening_a_named_profile_keeps_the_established_connection(self):
        cm = SessionConnectionManager()
        demo = _conn("http://demo.tg")
        cm.register_connection("demo", demo)
        cm.get_connection_for_profile("reports")
        self.assertIs(cm.get_default_connection(), demo)

    def test_registering_does_not_touch_the_class_pool(self):
        cm = SessionConnectionManager()
        cm.register_connection("default", _conn())
        self.assertNotIn("default", ConnectionManager._connection_pool)

    def test_set_default_connection(self):
        cm = SessionConnectionManager()
        sentinel = object()
        cm.set_default_connection(sentinel)  # type: ignore[arg-type]
        self.assertIs(cm.get_default_connection(), sentinel)


class TestMultiInstanceIsolation(unittest.TestCase):
    def setUp(self):
        ConnectionManager._profiles = set()
        ConnectionManager._connection_pool = {}
        ConnectionManager._default_connection = None

    def test_two_sessions_do_not_share_pool(self):
        cm_a = SessionConnectionManager()
        cm_b = SessionConnectionManager()
        cm_a.register_connection("default", _conn())
        cm_b.register_connection("default", _conn())
        conn_a = cm_a.get_connection_for_profile("default")
        conn_b = cm_b.get_connection_for_profile("default")
        self.assertIsNot(conn_a, conn_b)
        self.assertEqual(list(cm_a._connection_pool.keys()), ["default"])
        self.assertEqual(list(cm_b._connection_pool.keys()), ["default"])

    def test_session_pool_isolated_from_class_pool(self):
        # Populate process-global pool.
        class_conn = ConnectionManager.get_connection_for_profile("default")
        # Populate a session pool.
        cm = SessionConnectionManager()
        session_conn = _conn()
        cm.register_connection("default", session_conn)
        self.assertIsNot(class_conn, session_conn)
        # Session default connection should not leak to the class default.
        self.assertIs(ConnectionManager.get_default_connection(), class_conn)
        self.assertIs(cm.get_default_connection(), session_conn)


class TestActiveManagerResolution(unittest.TestCase):
    def setUp(self):
        ConnectionManager._profiles = set()
        ConnectionManager._connection_pool = {}
        ConnectionManager._default_connection = None

    def test_without_binding_resolves_to_class(self):
        self.assertIs(get_active_manager(), ConnectionManager)

    def test_use_session_manager_overrides_active(self):
        cm = SessionConnectionManager()
        with use_session_manager(cm) as bound:
            self.assertIs(bound, cm)
            self.assertIs(get_active_manager(), cm)
        # After exiting, falls back to class.
        self.assertIs(get_active_manager(), ConnectionManager)

    def test_get_connection_uses_session_pool_when_bound(self):
        cm = SessionConnectionManager()
        cm.register_connection("default", _conn())
        with use_session_manager(cm):
            conn = get_connection(profile="default")
        # The connection must be in the session pool, not in the class pool.
        self.assertIn("default", cm._connection_pool)
        self.assertIs(cm._connection_pool["default"], conn)
        self.assertNotIn("default", ConnectionManager._connection_pool)

    def test_get_connection_uses_class_pool_when_unbound(self):
        get_connection(profile="default")
        self.assertIn("default", ConnectionManager._connection_pool)

    def test_nested_use_session_manager_restores_outer(self):
        outer = SessionConnectionManager()
        inner = SessionConnectionManager()
        with use_session_manager(outer):
            self.assertIs(get_active_manager(), outer)
            with use_session_manager(inner):
                self.assertIs(get_active_manager(), inner)
            self.assertIs(get_active_manager(), outer)
        self.assertIs(get_active_manager(), ConnectionManager)


class TestSessionProfileArgument(unittest.TestCase):
    """How a tool's ``profile=`` argument resolves inside an HTTP session."""

    def setUp(self):
        ConnectionManager._connection_pool = {}
        ConnectionManager._default_connection = None
        self.cm = SessionConnectionManager()
        self.conn = _conn("http://demo.tg")
        self.cm.register_connection("demo", self.conn)
        token = set_pending_credentials({"profile": "demo"})
        self.addCleanup(reset_pending_credentials, token)

    @mock.patch.dict(os.environ, {"TG_DEFAULT_PROFILE": "demo"}, clear=False)
    def test_omitted_profile_uses_the_servers_default_profile(self):
        with use_session_manager(self.cm):
            self.assertIs(get_connection(), self.conn)

    @mock.patch.dict(os.environ, {"TG_DEFAULT_PROFILE": "demo"}, clear=False)
    def test_explicit_default_resolves_the_same_way(self):
        with use_session_manager(self.cm):
            self.assertIs(get_connection(profile="default"), self.conn)

    def test_naming_the_request_profile_works(self):
        with use_session_manager(self.cm):
            self.assertIs(get_connection(profile="demo"), self.conn)

    def test_naming_an_undefined_profile_is_refused(self):
        with use_session_manager(self.cm):
            with self.assertRaises(ValueError):
                get_connection(profile="nosuchprofile")

    @mock.patch.dict(
        os.environ,
        {
            "REPORTS_TG_HOST": "https://reports.example.com",
            "REPORTS_TG_USERNAME": "reader",
            "REPORTS_TG_PASSWORD": "pw",
        },
        clear=False,
    )
    def test_naming_a_configured_profile_opens_it(self):
        with use_session_manager(self.cm):
            conn = get_connection(profile="reports")
        self.assertEqual(conn.host, "https://reports.example.com")
        # ...without displacing the session's default.
        self.assertIs(get_connection.__wrapped__ if False else self.cm.get_default_connection(), self.conn)


class TestDefaultProfileParity(unittest.TestCase):
    """Which profile "default" means is a server setting, and both transports
    must read it the same way."""

    def resolve(self, profile, env):
        with mock.patch.dict(os.environ, env, clear=False):
            return resolve_profile_name(profile)

    def test_unset_means_the_unprefixed_variables(self):
        env = {"TG_DEFAULT_PROFILE": "", "TG_PROFILE": ""}
        self.assertEqual(self.resolve(None, env), "default")
        self.assertEqual(self.resolve("default", env), "default")

    def test_tg_default_profile_selects_it(self):
        env = {"TG_DEFAULT_PROFILE": "staging", "TG_PROFILE": ""}
        self.assertEqual(self.resolve(None, env), "staging")
        self.assertEqual(self.resolve("default", env), "staging")

    def test_tg_profile_is_accepted_as_an_alias(self):
        env = {"TG_DEFAULT_PROFILE": "", "TG_PROFILE": "staging"}
        self.assertEqual(self.resolve(None, env), "staging")

    def test_tg_default_profile_wins_over_the_alias(self):
        env = {"TG_DEFAULT_PROFILE": "prod", "TG_PROFILE": "staging"}
        self.assertEqual(self.resolve(None, env), "prod")

    def test_a_named_profile_is_used_as_given(self):
        env = {"TG_DEFAULT_PROFILE": "staging", "TG_PROFILE": ""}
        self.assertEqual(self.resolve("prod", env), "prod")

    def test_name_is_case_insensitive(self):
        env = {"TG_DEFAULT_PROFILE": "", "TG_PROFILE": ""}
        self.assertEqual(self.resolve("PROD", env), "prod")


class TestActiveManagerUnderConcurrency(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        ConnectionManager._profiles = set()
        ConnectionManager._connection_pool = {}
        ConnectionManager._default_connection = None

    async def test_concurrent_sessions_do_not_cross_contaminate(self):
        # Two concurrent tasks each bind their own session manager; the
        # active-manager ContextVar must keep them isolated.
        cm_a = SessionConnectionManager()
        cm_b = SessionConnectionManager()
        cm_a.register_connection("default", _conn())
        cm_b.register_connection("default", _conn())
        seen: dict[str, object] = {}

        async def task(name, cm):
            with use_session_manager(cm):
                # Yield to give the other task a chance to interleave.
                await asyncio.sleep(0)
                conn = get_connection(profile="default")
                await asyncio.sleep(0)
                seen[name] = conn

        await asyncio.gather(task("a", cm_a), task("b", cm_b))
        self.assertIs(seen["a"], cm_a._connection_pool["default"])
        self.assertIs(seen["b"], cm_b._connection_pool["default"])
        self.assertIsNot(seen["a"], seen["b"])


if __name__ == "__main__":
    unittest.main()
