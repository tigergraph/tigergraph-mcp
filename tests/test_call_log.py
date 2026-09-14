"""Tests for tool-call logging and the caller identity it may carry.

The identity settings decide whether an account name is written to an
operator's logs, so the cases that matter are the ones where a name must
*not* appear: identity off, and token auth where no account was named.
"""

import logging
import os
import unittest
from unittest import mock

from tigergraph_mcp import call_log


def _creds(**overrides):
    """Credentials shaped like the ones the HTTP middleware resolves."""
    creds = {
        "profile": "staging",
        "host": "https://acme.tgcloud.io",
        "graphname": "Social",
        "auth_mode": "password",
        "username_supplied": True,
        "username": "alice",
        "password": "s3cret",
        "secret": "",
        "api_token": "",
        "jwt_token": "",
        "session_id": "sess-42",
    }
    creds.update(overrides)
    return creds


class _CallLogCase(unittest.TestCase):
    """Restores the module's global settings, which configure() mutates."""

    def setUp(self):
        prior = call_log.configured()
        self.addCleanup(
            lambda: call_log.configure(enabled=prior[0], identity=prior[1])
        )
        # configure() consults the environment for anything not passed, so
        # start each test from an unset one.
        env = mock.patch.dict("os.environ", {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for var in ("TG_LOG_TOOL_CALLS", "TG_LOG_CALLER_IDENTITY"):
            os.environ.pop(var, None)

    def lines(self, tool="tigergraph__get_graph_schema", creds=None, **kwargs):
        """Capture the log lines one call produces."""
        with self.assertLogs(call_log.logger, level=logging.INFO) as captured:
            call_log.log_call(tool, creds, **kwargs)
            # assertLogs fails an empty capture, so guarantee one record.
            call_log.logger.info("sentinel")
        return [r for r in captured.output if "sentinel" not in r]


class TestConfiguration(_CallLogCase):

    def test_off_by_default(self):
        call_log.configure()
        self.assertFalse(call_log.enabled())
        self.assertEqual(call_log.identity(), call_log.IDENTITY_NONE)

    def test_environment_enables_it(self):
        with mock.patch.dict("os.environ", {"TG_LOG_TOOL_CALLS": "true"}):
            call_log.configure()
        self.assertTrue(call_log.enabled())

    def test_environment_boolean_forms(self):
        for raw, expected in [
            ("1", True), ("yes", True), ("ON", True), ("True", True),
            ("0", False), ("no", False), ("off", False), ("garbage", False),
        ]:
            with mock.patch.dict("os.environ", {"TG_LOG_TOOL_CALLS": raw}):
                call_log.configure()
            self.assertEqual(call_log.enabled(), expected, raw)

    def test_flag_wins_over_environment(self):
        with mock.patch.dict("os.environ", {"TG_LOG_TOOL_CALLS": "true"}):
            call_log.configure(enabled=False)
        self.assertFalse(call_log.enabled())

    def test_identity_comes_from_environment(self):
        with mock.patch.dict("os.environ", {"TG_LOG_TOOL_CALLS": "true",
                                            "TG_LOG_CALLER_IDENTITY": "username"}):
            call_log.configure()
        self.assertEqual(call_log.identity(), call_log.IDENTITY_USERNAME)

    def test_unknown_identity_is_rejected(self):
        # A typo must fail at startup, not silently log no identity.
        with self.assertRaises(ValueError) as ctx:
            call_log.configure(identity="user-name")
        self.assertIn("user-name", str(ctx.exception))

    def test_identity_is_case_insensitive(self):
        call_log.configure(enabled=True, identity="PROFILE")
        self.assertEqual(call_log.identity(), call_log.IDENTITY_PROFILE)

    def test_enabling_raises_the_logger_above_the_default_level(self):
        # The server defaults to WARNING; the flag has to be enough on its own.
        call_log.logger.setLevel(logging.NOTSET)
        call_log.configure(enabled=True)
        self.assertTrue(call_log.logger.isEnabledFor(logging.INFO))

    def test_logs_personal_data_only_for_username(self):
        call_log.configure(enabled=True, identity="none")
        self.assertFalse(call_log.logs_personal_data())
        call_log.configure(enabled=True, identity="profile")
        self.assertFalse(call_log.logs_personal_data())
        call_log.configure(enabled=True, identity="username")
        self.assertTrue(call_log.logs_personal_data())
        # Identity alone writes nothing.
        call_log.configure(enabled=False, identity="username")
        self.assertFalse(call_log.logs_personal_data())


class TestIdentityRequiresCallLogging(_CallLogCase):
    """An identity is off unless the calls it identifies are being logged."""

    def test_identity_is_off_when_call_logging_is_off(self):
        call_log.configure(enabled=False, identity="username")
        self.assertEqual(call_log.identity(), call_log.IDENTITY_NONE)
        self.assertEqual(call_log.configured(), (False, call_log.IDENTITY_NONE))

    def test_profile_identity_is_off_too(self):
        call_log.configure(enabled=False, identity="profile")
        self.assertEqual(call_log.identity(), call_log.IDENTITY_NONE)

    def test_environment_identity_is_off_without_call_logging(self):
        with mock.patch.dict("os.environ",
                             {"TG_LOG_CALLER_IDENTITY": "username"}):
            call_log.configure()
        self.assertEqual(call_log.identity(), call_log.IDENTITY_NONE)

    def test_the_ignored_setting_is_reported(self):
        call_log.configure(enabled=False, identity="username")
        self.assertTrue(call_log.identity_ignored())

    def test_nothing_is_reported_when_no_identity_was_asked_for(self):
        call_log.configure(enabled=False, identity="none")
        self.assertFalse(call_log.identity_ignored())

    def test_nothing_is_reported_when_the_identity_is_in_use(self):
        call_log.configure(enabled=True, identity="username")
        self.assertFalse(call_log.identity_ignored())

    def test_a_typo_is_still_rejected_when_call_logging_is_off(self):
        # Caught at startup rather than the day logging is turned on.
        with self.assertRaises(ValueError):
            call_log.configure(enabled=False, identity="user-name")

    def test_enabling_later_does_not_resurrect_the_identity(self):
        # The gated value is not remembered: turning logging on must not
        # start writing account names on its own.
        call_log.configure(enabled=False, identity="username")
        call_log.configure(enabled=True)
        self.assertEqual(call_log.identity(), call_log.IDENTITY_NONE)
        self.assertFalse(call_log.logs_personal_data())


class TestDisabled(_CallLogCase):

    def test_nothing_is_logged_when_off(self):
        call_log.configure(enabled=False)
        self.assertEqual(self.lines(creds=_creds()), [])

    def test_nothing_is_logged_when_off_even_with_identity(self):
        call_log.configure(enabled=False, identity="username")
        self.assertEqual(self.lines(creds=_creds()), [])


class TestToolAndSession(_CallLogCase):

    def setUp(self):
        super().setUp()
        call_log.configure(enabled=True, identity="none")

    def test_tool_name_and_session_are_logged(self):
        line = self.lines(creds=_creds())[0]
        self.assertIn("tool=tigergraph__get_graph_schema", line)
        self.assertIn("session=sess-42", line)

    def test_host_is_logged(self):
        # Infrastructure, not personal data: safe without opting in.
        self.assertIn("host=https://acme.tgcloud.io", self.lines(creds=_creds())[0])

    def test_no_identity_without_opting_in(self):
        line = self.lines(creds=_creds())[0]
        self.assertNotIn("alice", line)
        self.assertNotIn("profile=", line)
        self.assertNotIn("user=", line)

    def test_explicit_session_id_overrides_the_credentials(self):
        line = self.lines(creds=_creds(), session_id="sess-99")[0]
        self.assertIn("session=sess-99", line)

    def test_missing_session_is_marked_unknown(self):
        # The establishing request has no session id yet.
        line = self.lines(creds=_creds(session_id=""))[0]
        self.assertIn("session=-", line)

    def test_arguments_are_never_logged(self):
        # Tool arguments carry query text and vertex payloads.
        line = self.lines(creds=_creds())[0]
        self.assertNotIn("arguments", line)


class TestCredentialsNeverLeak(_CallLogCase):

    def test_no_secret_material_in_any_identity_mode(self):
        creds = _creds(
            password="s3cret", secret="gsql-secret",
            api_token="api-tok", jwt_token="jwt-tok",
        )
        for mode in call_log.IDENTITY_CHOICES:
            call_log.configure(enabled=True, identity=mode)
            line = self.lines(creds=creds)[0]
            for material in ("s3cret", "gsql-secret", "api-tok", "jwt-tok"):
                self.assertNotIn(material, line, mode)


class TestProfileIdentity(_CallLogCase):

    def setUp(self):
        super().setUp()
        call_log.configure(enabled=True, identity="profile")

    def test_profile_is_logged(self):
        self.assertIn("profile=staging", self.lines(creds=_creds())[0])

    def test_account_name_is_not_logged(self):
        line = self.lines(creds=_creds())[0]
        self.assertNotIn("alice", line)
        self.assertNotIn("user=", line)


class TestUsernameIdentity(_CallLogCase):

    def setUp(self):
        super().setUp()
        call_log.configure(enabled=True, identity="username")

    def test_username_and_auth_mode_are_logged(self):
        line = self.lines(creds=_creds())[0]
        self.assertIn("user=alice", line)
        self.assertIn("auth=password", line)
        self.assertIn("profile=staging", line)

    def test_token_auth_reports_an_unknown_account(self):
        # Token auth does not name an account, and the credentials carry a
        # placeholder. Logging it would record a name nobody authenticated as.
        creds = _creds(
            username_supplied=False, username="tigergraph",
            auth_mode="jwt", jwt_token="jwt-tok", password="",
        )
        line = self.lines(creds=creds)[0]
        self.assertIn("user=-", line)
        self.assertIn("auth=jwt", line)
        self.assertNotIn("user=tigergraph", line)

    def test_password_auth_that_minted_a_token_still_reports_password(self):
        # Validation stores the minted token on the credentials, so the mode
        # cannot be re-derived from them afterwards.
        creds = _creds(auth_mode="password", api_token="minted-tok")
        line = self.lines(creds=creds)[0]
        self.assertIn("auth=password", line)

    def test_stdio_falls_back_to_the_configured_profile(self):
        # No per-request identity in stdio mode; the server's own profile is
        # the only identity there is.
        env = {"TG_DEFAULT_PROFILE": "prod", "PROD_TG_USERNAME": "svc_agent"}
        with mock.patch.dict("os.environ", env):
            line = self.lines(creds=None)[0]
        self.assertIn("profile=prod", line)
        self.assertIn("user=svc_agent", line)

    def test_stdio_with_no_configured_username(self):
        env = {"TG_DEFAULT_PROFILE": "prod"}
        with mock.patch.dict("os.environ", env, clear=False):
            os.environ.pop("PROD_TG_USERNAME", None)
            os.environ.pop("TG_USERNAME", None)
            line = self.lines(creds=None)[0]
        self.assertIn("user=-", line)


if __name__ == "__main__":
    unittest.main()
