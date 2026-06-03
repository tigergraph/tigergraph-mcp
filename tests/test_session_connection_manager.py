"""Tests for SessionConnectionManager and the active-manager ContextVar.

These cover the M2 refactor: each session gets its own connection pool
and the module-level ``get_connection()`` resolves to the active session
manager when one is bound via ``use_session_manager``.
"""

import asyncio
import os
import unittest
from unittest import mock

from tigergraph_mcp.connection_manager import (
    ConnectionManager,
    SessionConnectionManager,
    get_active_manager,
    get_connection,
    use_session_manager,
)


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
        conn1 = cm.get_connection_for_profile("default")
        conn2 = cm.get_connection_for_profile("default")
        self.assertIs(conn1, conn2)

    def test_default_profile_sets_default_connection(self):
        cm = SessionConnectionManager()
        conn = cm.get_connection_for_profile("default")
        self.assertIs(cm.get_default_connection(), conn)

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
        session_conn = cm.get_connection_for_profile("default")
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
