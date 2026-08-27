"""Tests for the X-TG-* credential ASGI middleware.

The middleware is exercised at the ASGI scope/receive/send level so we
can verify the contract end-to-end without spinning up a real HTTP server.
"""

import asyncio
import os
import json
import unittest
from typing import Any, Dict, List, Tuple
from unittest import mock

from tigergraph_mcp import http_middleware
from tigergraph_mcp.connection_manager import (
    get_pending_credentials,
)
from pyTigerGraph.common.exception import TigerGraphException

from tigergraph_mcp.http_middleware import CredentialHeadersMiddleware


def _scope(headers: Dict[str, str]) -> Dict[str, Any]:
    return {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [
            (k.encode("latin-1"), v.encode("latin-1"))
            for k, v in headers.items()
        ],
    }


class _Inbox:
    """Capture every send() event so the test can assert on the response."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    async def __call__(self, event: Dict[str, Any]) -> None:
        self.events.append(event)


async def _noop_receive() -> Dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


class _CapturingApp:
    """Downstream ASGI app that records whether it was reached and what
    the pending credentials looked like at the time."""

    def __init__(self) -> None:
        self.called = False
        self.creds_seen: Dict[str, Any] | None = None

    async def __call__(self, scope, receive, send):
        self.called = True
        self.creds_seen = get_pending_credentials()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# Server-side profile configuration changes what the middleware accepts, so
# tests state the environment they assume rather than inheriting the shell's.
NO_SERVER_PROFILES = {
    k: "" for k in (
        "TG_HOST", "TG_USERNAME", "TG_PASSWORD", "TG_API_TOKEN",
        "TG_JWT_TOKEN", "TG_SECRET", "TG_GRAPHNAME",
    )
}


class TestCredentialHeadersMiddleware(unittest.TestCase):
    def setUp(self):
        # Bypass live validation in unit tests.
        self.middleware_kwargs = {"validate": False}
        patcher = mock.patch.dict(os.environ, NO_SERVER_PROFILES, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _build(self, app=None):
        return CredentialHeadersMiddleware(
            app or _CapturingApp(), **self.middleware_kwargs
        )

    def test_rejects_when_host_missing(self):
        app = _CapturingApp()
        mw = self._build(app)
        inbox = _Inbox()
        _run(mw(_scope({"x-tg-api-token": "tok"}), _noop_receive, inbox))
        self.assertFalse(app.called)
        # No resolvable host is a topology problem, not a credential one.
        starts = [e for e in inbox.events if e["type"] == "http.response.start"]
        bodies = [e for e in inbox.events if e["type"] == "http.response.body"]
        self.assertEqual(starts[0]["status"], 400)
        body = json.loads(bodies[0]["body"])
        self.assertIn("No TigerGraph host", body["error"])

    def test_rejects_when_credentials_missing(self):
        app = _CapturingApp()
        mw = self._build(app)
        inbox = _Inbox()
        _run(mw(_scope({"x-tg-host": "http://tg"}), _noop_receive, inbox))
        self.assertFalse(app.called)
        starts = [e for e in inbox.events if e["type"] == "http.response.start"]
        self.assertEqual(starts[0]["status"], 401)

    def test_passes_token_credentials_through(self):
        app = _CapturingApp()
        mw = self._build(app)
        inbox = _Inbox()
        _run(mw(
            _scope({"x-tg-host": "http://tg", "x-tg-api-token": "tok"}),
            _noop_receive,
            inbox,
        ))
        self.assertTrue(app.called)
        self.assertIsNotNone(app.creds_seen)
        self.assertEqual(app.creds_seen["host"], "http://tg")
        self.assertEqual(app.creds_seen["api_token"], "tok")

    def test_passes_password_credentials_through(self):
        app = _CapturingApp()
        mw = self._build(app)
        inbox = _Inbox()
        _run(mw(
            _scope({
                "x-tg-host": "http://tg",
                "x-tg-username": "alice",
                "x-tg-password": "secret",
            }),
            _noop_receive,
            inbox,
        ))
        self.assertTrue(app.called)
        self.assertEqual(app.creds_seen["username"], "alice")
        self.assertEqual(app.creds_seen["password"], "secret")

    def test_pending_credentials_reset_after_request(self):
        app = _CapturingApp()
        mw = self._build(app)
        inbox = _Inbox()
        _run(mw(
            _scope({"x-tg-host": "http://tg", "x-tg-api-token": "tok"}),
            _noop_receive,
            inbox,
        ))
        # After the request finishes, the ContextVar must be cleared.
        self.assertIsNone(get_pending_credentials())

    def test_optional_secret_and_tgcloud_headers(self):
        # X-TG-Secret and X-TG-Tgcloud mirror TG_SECRET and TG_TGCLOUD.
        app = _CapturingApp()
        mw = self._build(app)
        inbox = _Inbox()
        _run(mw(
            _scope({
                "x-tg-host": "http://tg",
                "x-tg-api-token": "tok",
                "x-tg-secret": "my-gsql-secret",
                "x-tg-tgcloud": "true",
            }),
            _noop_receive,
            inbox,
        ))
        self.assertTrue(app.called)
        self.assertEqual(app.creds_seen["secret"], "my-gsql-secret")
        self.assertTrue(app.creds_seen["tg_cloud"])

    def test_non_http_scope_passes_through_untouched(self):
        app = _CapturingApp()
        mw = self._build(app)
        inbox = _Inbox()
        # Lifespan scope — middleware must not interfere.
        _run(mw({"type": "lifespan"}, _noop_receive, inbox))
        self.assertTrue(app.called)


class TestCredentialHeadersMiddlewareValidation(unittest.TestCase):
    """Validation-on path: middleware calls into pyTigerGraph and 401s on failure."""

    def test_token_auth_validates_via_echo(self):
        # Build a fake AsyncTigerGraphConnection whose echo() succeeds.
        fake_conn = mock.AsyncMock()
        fake_conn.echo = mock.AsyncMock(return_value="Hello GSQL")
        fake_conn.aclose = mock.AsyncMock()

        with mock.patch.object(
            http_middleware, "AsyncTigerGraphConnection", return_value=fake_conn
        ):
            app = _CapturingApp()
            mw = CredentialHeadersMiddleware(app, validate=True)
            inbox = _Inbox()
            _run(mw(
                _scope({"x-tg-host": "http://tg", "x-tg-api-token": "tok"}),
                _noop_receive,
                inbox,
            ))

        self.assertTrue(app.called)
        fake_conn.echo.assert_awaited_once()

    def test_password_auth_mints_token_via_getToken(self):
        fake_conn = mock.AsyncMock()
        fake_conn.aclose = mock.AsyncMock()
        # A real connection built from a password holds no token until
        # getToken mints one, so the mock must start empty and fill in.
        fake_conn.apiToken = ""
        fake_conn.jwtToken = ""

        async def _mint(*args, **kwargs):
            fake_conn.apiToken = "minted-token"
            return "minted-token"

        fake_conn.getToken = mock.AsyncMock(side_effect=_mint)

        with mock.patch.object(
            http_middleware, "AsyncTigerGraphConnection", return_value=fake_conn
        ):
            app = _CapturingApp()
            mw = CredentialHeadersMiddleware(app, validate=True)
            inbox = _Inbox()
            _run(mw(
                _scope({
                    "x-tg-host": "http://tg",
                    "x-tg-username": "alice",
                    "x-tg-password": "secret",
                }),
                _noop_receive,
                inbox,
            ))

        self.assertTrue(app.called)
        fake_conn.getToken.assert_awaited_once()
        # The minted token must be propagated downstream so the session
        # manager builds the real connection with the token (not password).
        self.assertEqual(app.creds_seen["api_token"], "minted-token")

    def test_rejects_when_validation_raises(self):
        from pyTigerGraph.common.exception import TigerGraphException

        fake_conn = mock.AsyncMock()
        fake_conn.echo = mock.AsyncMock(side_effect=TigerGraphException("bad token", 401))
        fake_conn.aclose = mock.AsyncMock()

        with mock.patch.object(
            http_middleware, "AsyncTigerGraphConnection", return_value=fake_conn
        ):
            app = _CapturingApp()
            mw = CredentialHeadersMiddleware(app, validate=True)
            inbox = _Inbox()
            _run(mw(
                _scope({"x-tg-host": "http://tg", "x-tg-api-token": "bad"}),
                _noop_receive,
                inbox,
            ))

        self.assertFalse(app.called)
        starts = [e for e in inbox.events if e["type"] == "http.response.start"]
        self.assertEqual(starts[0]["status"], 401)


class TestValidationOnEstablishment(unittest.TestCase):
    """Credentials are proven when the session's connection is created.

    A client's headers are fixed for the life of its session, so probing on
    every request re-proves something that cannot have changed; the session's
    connection pool already holds the validated connection.
    """

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"TG_HOST": "http://tg"}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []

        async def fake_validate(creds):
            self.calls.append(creds["host"])
        p2 = mock.patch.object(http_middleware, "_validate", fake_validate)
        p2.start()
        self.addCleanup(p2.stop)

    def _request(self, headers):
        app = _CapturingApp()
        mw = CredentialHeadersMiddleware(app, validate=True)
        inbox = _Inbox()
        _run(mw(_scope(headers), _noop_receive, inbox))
        return app, inbox

    CREDS = {"x-tg-host": "http://tg", "x-tg-api-token": "tok"}

    def test_the_establishing_request_is_validated(self):
        self._request(self.CREDS)
        self.assertEqual(len(self.calls), 1)

    def test_later_requests_in_the_session_are_not(self):
        self._request(self.CREDS)
        for _ in range(5):
            self._request({**self.CREDS, "mcp-session-id": "abc123"})
        self.assertEqual(len(self.calls), 1)

    def test_a_new_session_is_validated_again(self):
        self._request(self.CREDS)
        self._request(self.CREDS)
        self.assertEqual(len(self.calls), 2)

    def test_later_requests_still_resolve_their_credentials(self):
        # Skipping the probe must not skip building the request's config.
        app, _ = self._request({**self.CREDS, "mcp-session-id": "abc123"})
        self.assertTrue(app.called)
        self.assertEqual(app.creds_seen["host"], "http://tg")

    def test_a_rejected_credential_never_establishes_a_session(self):
        async def always_fail(creds):
            self.calls.append(creds["host"])
            raise TigerGraphException("nope", None)
        with mock.patch.object(http_middleware, "_validate", always_fail):
            app, inbox = self._request(self.CREDS)
        self.assertFalse(app.called)
        starts = [e for e in inbox.events if e["type"] == "http.response.start"]
        self.assertEqual(starts[0]["status"], 401)

    def test_malformed_requests_are_refused_without_a_probe(self):
        # Resolution failures need no round trip to TigerGraph.
        app, inbox = self._request({"x-tg-profile": "nosuchprofile"})
        self.assertFalse(app.called)
        self.assertEqual(self.calls, [])


# Server-side profiles: 'demo' carries credentials, 'byoc' is topology only.
SERVER_PROFILES = {
    "TG_HOST": "http://default.tg",
    "TG_USERNAME": "defaultuser",
    "TG_PASSWORD": "defaultpass",
    "DEMO_TG_HOST": "http://demo.tg",
    "DEMO_TG_USERNAME": "demouser",
    "DEMO_TG_PASSWORD": "demopass",
    "BYOC_TG_HOST": "http://byoc.tg",
    "TG_HTTP_ALLOWED_PROFILES": "",
}


class TestProfileResolution(unittest.TestCase):
    """The four ways a client may present itself.

    ==========================  =============================================
    Headers                     Result
    ==========================  =============================================
    X-TG-Profile only           that profile's topology + its credentials
    X-TG-Profile + credentials  that profile's topology, caller's identity
    credentials only            default topology, caller's identity
    none                        the default profile as configured
    ==========================  =============================================
    """

    def setUp(self):
        patcher = mock.patch.dict(os.environ, SERVER_PROFILES, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def resolve(self, headers):
        return http_middleware._parse_credentials(headers)

    def test_profile_selector_alone_uses_profile_credentials(self):
        creds = self.resolve({"x-tg-profile": "demo"})
        self.assertEqual(creds["profile"], "demo")
        self.assertEqual(creds["host"], "http://demo.tg")
        self.assertEqual(creds["username"], "demouser")

    def test_profile_plus_credentials_keeps_profile_topology(self):
        creds = self.resolve({
            "x-tg-profile": "demo",
            "x-tg-username": "alice", "x-tg-password": "s3cr3t",
        })
        self.assertEqual(creds["host"], "http://demo.tg")
        self.assertEqual(creds["username"], "alice")

    def test_credentials_alone_use_default_topology(self):
        creds = self.resolve({"x-tg-username": "alice", "x-tg-password": "s3cr3t"})
        self.assertEqual(creds["profile"], "default")
        self.assertEqual(creds["host"], "http://default.tg")
        self.assertEqual(creds["username"], "alice")

    def test_no_headers_uses_the_default_profile(self):
        creds = self.resolve({})
        self.assertEqual(creds["profile"], "default")
        self.assertEqual(creds["host"], "http://default.tg")
        self.assertEqual(creds["username"], "defaultuser")

    def test_host_header_overrides_profile_topology(self):
        creds = self.resolve({"x-tg-profile": "demo", "x-tg-host": "http://other.tg"})
        self.assertEqual(creds["host"], "http://other.tg")

    def test_topology_only_profile_inherits_the_default_credentials(self):
        # A named profile uses its own credentials where it has them, and the
        # unprefixed ones where it does not -- the same rule as stdio.
        creds = self.resolve({"x-tg-profile": "byoc"})
        self.assertEqual(creds["host"], "http://byoc.tg")
        self.assertEqual(creds["username"], "defaultuser")

    def test_topology_only_profile_accepts_client_identity(self):
        creds = self.resolve({
            "x-tg-profile": "byoc",
            "x-tg-api-token": "tok",
        })
        self.assertEqual(creds["host"], "http://byoc.tg")
        self.assertEqual(creds["api_token"], "tok")

    def test_profile_credentials_prefer_the_profile_own_values(self):
        self.assertEqual(http_middleware.profile_credentials("demo")["username"],
                         "demouser")

    def test_profile_credentials_fall_back_to_the_unprefixed_values(self):
        self.assertEqual(http_middleware.profile_credentials("byoc")["username"],
                         "defaultuser")

    def test_unknown_profile_is_refused(self):
        self.assertIsNone(self.resolve({"x-tg-profile": "nosuchprofile"}))

    def test_allow_list_restricts_selectable_profiles(self):
        with mock.patch.dict(os.environ, {"TG_HTTP_ALLOWED_PROFILES": "demo"}):
            self.assertIsNotNone(self.resolve({"x-tg-profile": "demo"}))
            self.assertIsNone(self.resolve({"x-tg-profile": "byoc",
                                            "x-tg-api-token": "tok"}))

    def test_overrides_do_not_mutate_the_server_profile(self):
        # An override applies to the requesting session only; the next caller
        # of the same profile must see the configured value again.
        overridden = self.resolve({"x-tg-profile": "demo", "x-tg-host": "http://mine.tg"})
        plain = self.resolve({"x-tg-profile": "demo"})
        self.assertEqual(overridden["host"], "http://mine.tg")
        self.assertEqual(plain["host"], "http://demo.tg")

    def test_each_resolution_is_independent(self):
        a = self.resolve({"x-tg-profile": "demo", "x-tg-graphname": "GraphA"})
        b = self.resolve({"x-tg-profile": "demo", "x-tg-graphname": "GraphB"})
        self.assertEqual(a["graphname"], "GraphA")
        self.assertEqual(b["graphname"], "GraphB")

    def test_tg_profile_names_the_default_profile(self):
        # TG_PROFILE selects which profile acts as the default for requests
        # that do not name one.
        with mock.patch.dict(os.environ, {"TG_PROFILE": "demo"}):
            creds, _, _ = http_middleware._resolve({})
            self.assertEqual(creds["profile"], "demo")
            self.assertEqual(creds["host"], "http://demo.tg")

    def test_unset_tg_profile_uses_the_unprefixed_vars(self):
        with mock.patch.dict(os.environ, {"TG_PROFILE": ""}):
            creds, _, _ = http_middleware._resolve({})
            self.assertEqual(creds["profile"], "default")
            self.assertEqual(creds["host"], "http://default.tg")

    def test_header_profile_beats_tg_profile(self):
        with mock.patch.dict(os.environ, {"TG_PROFILE": "demo"}):
            creds, _, _ = http_middleware._resolve({"x-tg-profile": "byoc",
                                                    "x-tg-api-token": "tok"})
            self.assertEqual(creds["profile"], "byoc")

    def test_client_credentials_beat_the_default_profile(self):
        # The operator's default profile supplies topology; the caller's
        # identity still wins.
        with mock.patch.dict(os.environ, {"TG_PROFILE": "demo"}):
            creds, _, _ = http_middleware._resolve({"x-tg-username": "alice",
                                                    "x-tg-password": "pw"})
            self.assertEqual(creds["host"], "http://demo.tg")
            self.assertEqual(creds["username"], "alice")

    def test_topology_failures_are_400(self):
        # Addressing the wrong server is a different problem from bad
        # credentials, and the status code should say so.
        _, status, _ = http_middleware._resolve({"x-tg-profile": "nope"})
        self.assertEqual(status, 400)

    def test_missing_host_is_a_topology_failure(self):
        with mock.patch.dict(os.environ, {"TG_HOST": ""}):
            _, status, reason = http_middleware._resolve({})
            self.assertEqual(status, 400)
            self.assertIn("No TigerGraph host", reason)

    def test_missing_credentials_is_401(self):
        # With nothing configured anywhere, the caller must identify itself.
        with mock.patch.dict(os.environ, {"TG_USERNAME": "", "TG_PASSWORD": ""}):
            _, status, reason = http_middleware._resolve({"x-tg-profile": "byoc"})
        self.assertEqual(status, 401)
        self.assertIn("No credentials", reason)

    def test_allow_list_rejection_is_400(self):
        with mock.patch.dict(os.environ, {"TG_HTTP_ALLOWED_PROFILES": "demo"}):
            _, status, _ = http_middleware._resolve({"x-tg-profile": "byoc",
                                                     "x-tg-api-token": "t"})
            self.assertEqual(status, 400)

    def test_success_carries_no_error(self):
        creds, status, reason = http_middleware._resolve({"x-tg-profile": "demo"})
        self.assertIsNotNone(creds)
        self.assertEqual((status, reason), (0, ""))

    def test_empty_header_does_not_override_the_profile(self):
        creds, _, _ = http_middleware._resolve({"x-tg-profile": "demo", "x-tg-host": ""})
        self.assertEqual(creds["host"], "http://demo.tg")

    def test_profile_name_is_case_insensitive(self):
        self.assertEqual(self.resolve({"x-tg-profile": "DEMO"})["profile"], "demo")


if __name__ == "__main__":
    unittest.main()
