"""Tests for the command-line entry point.

``main()`` is what turns flags and environment into server configuration, and
what refuses a configuration the server cannot honour. ``serve`` is patched out
throughout: these tests are about what main decides, not about binding a port.

The negative cases matter most here — a deployment that mistypes a selector
should be told at startup, not discover at runtime that it is serving three
tools or logging nothing.
"""

import logging
import os
import sys
import unittest
from unittest import mock

from click.testing import CliRunner

from tigergraph_mcp import call_log, tool_filter
from tigergraph_mcp.main import main

# Settings main() mutates process-wide. Each test restores them.
_MANAGED_ENV = (
    "TG_LOG_TOOL_CALLS",
    "TG_LOG_CALLER_IDENTITY",
    "TG_ALLOWED_TOOLS",
    "TG_BLOCKED_TOOLS",
)


class _CliCase(unittest.TestCase):

    def setUp(self):
        prior_log = call_log.configured()
        prior_filter = tool_filter.configured()
        self.addCleanup(
            lambda: call_log.configure(enabled=prior_log[0], identity=prior_log[1])
        )
        self.addCleanup(
            lambda: tool_filter.configure(
                allowed=prior_filter[0], blocked=prior_filter[1]
            )
        )
        env = mock.patch.dict("os.environ", {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for var in _MANAGED_ENV:
            os.environ.pop(var, None)

        # Nothing here should actually start a server.
        self.serve = mock.patch("tigergraph_mcp.main.serve").start()
        self.addCleanup(mock.patch.stopall)

        self.runner = CliRunner()

    def run_cli(self, *args):
        return self.runner.invoke(main, list(args))

    def assert_served(self, result):
        """The CLI got far enough to hand off to the server."""
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(self.serve.called, "serve() was never reached")
        return self.serve.call_args.kwargs


class TestTransportWiring(_CliCase):

    def test_defaults_to_stdio(self):
        kwargs = self.assert_served(self.run_cli())
        self.assertEqual(kwargs["transport"], "stdio")

    def test_transport_is_lowercased(self):
        # click accepts the choice case-insensitively; serve() compares exactly.
        kwargs = self.assert_served(self.run_cli("--transport", "STREAMABLE-HTTP"))
        self.assertEqual(kwargs["transport"], "streamable-http")

    def test_host_port_and_mount_path_are_passed_through(self):
        kwargs = self.assert_served(self.run_cli(
            "--transport", "sse", "--host", "0.0.0.0",
            "--port", "9999", "--mount-path", "/tg",
        ))
        self.assertEqual(
            (kwargs["host"], kwargs["port"], kwargs["mount_path"]),
            ("0.0.0.0", 9999, "/tg"),
        )

    def test_unknown_transport_is_refused_by_the_parser(self):
        result = self.run_cli("--transport", "carrier-pigeon")
        self.assertEqual(result.exit_code, 2)
        self.assertFalse(self.serve.called)


class TestVerbosity(_CliCase):
    """What level main selects.

    Asserted through basicConfig rather than the root logger's level:
    basicConfig is a no-op once handlers exist, which is the case under
    pytest, so the global state would not move even when main is correct.
    """

    def setUp(self):
        super().setUp()
        self.basic_config = mock.patch("logging.basicConfig").start()

    def chosen_level(self):
        return self.basic_config.call_args.kwargs["level"]

    def test_default_is_quiet(self):
        self.assert_served(self.run_cli())
        self.assertEqual(self.chosen_level(), logging.WARN)

    def test_single_v_is_info(self):
        self.assert_served(self.run_cli("-v"))
        self.assertEqual(self.chosen_level(), logging.INFO)

    def test_double_v_is_debug(self):
        self.assert_served(self.run_cli("-vv"))
        self.assertEqual(self.chosen_level(), logging.DEBUG)

    def test_logs_go_to_stderr_not_stdout(self):
        # stdout carries the MCP protocol in stdio mode; a log line there
        # would corrupt the stream. Compared against the streams as they were
        # during the call: both the runner and pytest swap them afterwards.
        seen = {}

        def record(*_, **kwargs):
            seen.update(stream=kwargs.get("stream"),
                        stderr=sys.stderr, stdout=sys.stdout)

        self.basic_config.side_effect = record
        self.assert_served(self.run_cli())
        self.assertIs(seen["stream"], seen["stderr"])
        self.assertIsNot(seen["stream"], seen["stdout"])

    def test_the_sdk_logger_is_kept_quiet(self):
        # Its per-request INFO chatter would otherwise drown the server's own.
        self.assert_served(self.run_cli("-vv"))
        sdk = logging.getLogger("mcp.server.lowlevel.server")
        self.assertEqual(sdk.level, logging.WARNING)


class TestToolSelection(_CliCase):

    def test_allowed_tools_narrows_the_list(self):
        self.assert_served(self.run_cli("--allowed-tools", "read-only"))
        self.assertEqual(tool_filter.configured()[0], "read-only")

    def test_blocked_tools_is_recorded(self):
        self.assert_served(self.run_cli("--blocked-tools", "destructive"))
        self.assertEqual(tool_filter.configured()[1], "destructive")

    def test_environment_supplies_the_selection(self):
        with mock.patch.dict("os.environ", {"TG_ALLOWED_TOOLS": "schema"}):
            self.assert_served(self.run_cli())
        self.assertEqual(tool_filter.configured()[0], "schema")

    def test_flag_wins_over_the_environment(self):
        with mock.patch.dict("os.environ", {"TG_ALLOWED_TOOLS": "schema"}):
            self.assert_served(self.run_cli("--allowed-tools", "query"))
        self.assertEqual(tool_filter.configured()[0], "query")

    # ── negative ──────────────────────────────────────────────────────

    def test_unknown_selector_stops_startup(self):
        result = self.run_cli("--allowed-tools", "nope")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("nope", result.output)
        self.assertFalse(self.serve.called, "a bad selector must not serve")

    def test_unknown_selector_from_the_environment_also_stops_startup(self):
        with mock.patch.dict("os.environ", {"TG_BLOCKED_TOOLS": "not-a-category"}):
            result = self.run_cli()
        self.assertEqual(result.exit_code, 1)
        self.assertFalse(self.serve.called)

    def test_a_selection_that_serves_nothing_stops_startup(self):
        # Allowing and blocking the same set leaves an empty server, which is
        # a misconfiguration rather than a legitimate deployment.
        result = self.run_cli("--allowed-tools", "schema", "--blocked-tools", "schema")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("no tools", result.output.lower())
        self.assertFalse(self.serve.called)


class TestCallLogging(_CliCase):

    def test_off_by_default(self):
        self.assert_served(self.run_cli())
        self.assertFalse(call_log.enabled())
        self.assertEqual(call_log.identity(), call_log.IDENTITY_NONE)

    def test_flag_enables_it(self):
        self.assert_served(self.run_cli("--log-tool-calls"))
        self.assertTrue(call_log.enabled())

    def test_environment_enables_it(self):
        with mock.patch.dict("os.environ", {"TG_LOG_TOOL_CALLS": "true"}):
            self.assert_served(self.run_cli())
        self.assertTrue(call_log.enabled())

    def test_explicit_no_flag_overrides_the_environment(self):
        with mock.patch.dict("os.environ", {"TG_LOG_TOOL_CALLS": "true"}):
            self.assert_served(self.run_cli("--no-log-tool-calls"))
        self.assertFalse(call_log.enabled())

    def test_caller_identity_is_recorded(self):
        self.assert_served(self.run_cli("--log-tool-calls", "--log-caller", "username"))
        self.assertEqual(call_log.identity(), call_log.IDENTITY_USERNAME)

    def test_caller_identity_is_case_insensitive(self):
        self.assert_served(self.run_cli("--log-tool-calls", "--log-caller", "PROFILE"))
        self.assertEqual(call_log.identity(), call_log.IDENTITY_PROFILE)

    # ── negative ──────────────────────────────────────────────────────

    def test_identity_without_call_logging_is_off_and_warned_about(self):
        with self.assertLogs("tigergraph_mcp.main", level="WARNING") as logged:
            result = self.run_cli("--log-caller", "username")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(call_log.identity(), call_log.IDENTITY_NONE)
        self.assertFalse(call_log.logs_personal_data())
        self.assertIn("--log-tool-calls", "\n".join(logged.output))

    def test_unknown_identity_is_refused_by_the_parser(self):
        result = self.run_cli("--log-tool-calls", "--log-caller", "user-name")
        self.assertEqual(result.exit_code, 2)
        self.assertFalse(self.serve.called)

    def test_unknown_identity_from_the_environment_stops_startup(self):
        # The parser cannot police the env var, so main must.
        with mock.patch.dict("os.environ", {"TG_LOG_CALLER_IDENTITY": "user-name"}):
            result = self.run_cli("--log-tool-calls")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("user-name", result.output)
        self.assertFalse(self.serve.called)

    def test_logging_account_names_is_announced(self):
        # Turning this on makes the operator responsible for personal data in
        # their logs, so it must not happen silently.
        with self.assertLogs("tigergraph_mcp.main", level="WARNING") as logged:
            self.run_cli("--log-tool-calls", "--log-caller", "username")
        self.assertTrue(call_log.logs_personal_data())
        self.assertIn("account names", "\n".join(logged.output))

    def test_no_personal_data_warning_for_the_profile_level(self):
        with mock.patch.object(logging.getLogger("tigergraph_mcp.main"),
                               "warning") as warned:
            self.run_cli("--log-tool-calls", "--log-caller", "profile")
        self.assertFalse(warned.called)


class TestEnvFile(_CliCase):

    def test_missing_env_file_is_refused(self):
        result = self.run_cli("--env-file", "/no/such/.env")
        self.assertEqual(result.exit_code, 2)
        self.assertFalse(self.serve.called)

    def test_settings_may_come_from_the_env_file(self):
        with self.runner.isolated_filesystem():
            with open(".env", "w") as fh:
                fh.write("TG_LOG_TOOL_CALLS=true\nTG_LOG_CALLER_IDENTITY=profile\n")
            self.assert_served(self.run_cli("--env-file", ".env"))
        self.assertTrue(call_log.enabled())
        self.assertEqual(call_log.identity(), call_log.IDENTITY_PROFILE)


if __name__ == "__main__":
    unittest.main()
