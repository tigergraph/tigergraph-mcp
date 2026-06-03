"""Tests for the X-TG-* credential ASGI middleware.

The middleware is exercised at the ASGI scope/receive/send level so we
can verify the contract end-to-end without spinning up a real HTTP server.
"""

import asyncio
import json
import unittest
from typing import Any, Dict, List, Tuple
from unittest import mock

from tigergraph_mcp import http_middleware
from tigergraph_mcp.connection_manager import (
    get_pending_credentials,
)
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


class TestCredentialHeadersMiddleware(unittest.TestCase):
    def setUp(self):
        # Bypass live validation in unit tests.
        self.middleware_kwargs = {"validate": False}

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
        # Response should be a 401 with a JSON body.
        starts = [e for e in inbox.events if e["type"] == "http.response.start"]
        bodies = [e for e in inbox.events if e["type"] == "http.response.body"]
        self.assertEqual(starts[0]["status"], 401)
        body = json.loads(bodies[0]["body"])
        self.assertIn("Missing TigerGraph credentials", body["error"])

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
        fake_conn.getToken = mock.AsyncMock(return_value="minted-token")
        fake_conn.aclose = mock.AsyncMock()
        # After getToken, conn.apiToken is set on the real connection. Mock it.
        fake_conn.apiToken = "minted-token"

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


if __name__ == "__main__":
    unittest.main()
