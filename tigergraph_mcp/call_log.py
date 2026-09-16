# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Recording which tool was called, and optionally by whom.

Off by default. Nothing here changes what a tool does; it writes one line
per call so an operator can answer "what has been run against this
instance" after the fact.

Two settings, kept separate on purpose:

- whether tool calls are logged at all
- which caller identity, if any, each line carries

The identity is separate because a TigerGraph username generally
identifies a person, and a library should not write personal data into an
operator's logs unasked. ``profile`` names the configured connection a
call used — a property of the server, not of a person — and is the
smaller disclosure; ``username`` names the account. Which one is
appropriate depends on the deployment, so the default is neither.

Credentials never appear in a line: it carries the authentication *mode*,
never the password, secret, or token that proved it. Tool arguments never
appear either — they hold query text and vertex payloads, which is graph
data rather than an audit record.
"""

import logging
import os
from typing import Any, Dict, Optional

# Which caller identity a line carries.
IDENTITY_NONE = "none"
IDENTITY_PROFILE = "profile"
IDENTITY_USERNAME = "username"
IDENTITY_CHOICES = (IDENTITY_NONE, IDENTITY_PROFILE, IDENTITY_USERNAME)

# Stands in for a field the server cannot know, so a line's shape is stable
# whether or not the value was available.
_UNKNOWN = "-"

logger = logging.getLogger(__name__)

_enabled: bool = False
_identity: str = IDENTITY_NONE
# What was asked for, before call logging gated it. Kept only so the entry
# point can say a setting was ignored.
_requested_identity: str = IDENTITY_NONE


def _bool_env(name: str) -> Optional[bool]:
    """Read a boolean-ish environment variable, or None when it is unset."""
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return None
    return raw in ("1", "true", "yes", "on")


def configure(enabled: Optional[bool] = None, identity: Optional[str] = None) -> None:
    """Set the server-wide call-log settings, falling back to the environment.

    Args:
        enabled: Log a line per tool call. Defaults to ``TG_LOG_TOOL_CALLS``,
            else off.
        identity: One of :data:`IDENTITY_CHOICES`. Defaults to
            ``TG_LOG_CALLER_IDENTITY``, else ``"none"``. Requires ``enabled``:
            with call logging off it resolves to ``"none"``.

    Raises:
        ValueError: on an unrecognised identity, so a typo is reported at
            startup rather than quietly logging no identity at all.
    """
    global _enabled, _identity, _requested_identity

    if enabled is None:
        enabled = _bool_env("TG_LOG_TOOL_CALLS")
    _enabled = bool(enabled)

    raw = identity if identity is not None else os.getenv("TG_LOG_CALLER_IDENTITY")
    choice = (raw or IDENTITY_NONE).strip().lower()
    # Validated even when call logging is off, so a typo is still caught at
    # startup rather than surfacing the day someone turns logging on.
    if choice not in IDENTITY_CHOICES:
        raise ValueError(
            f"Unknown caller identity '{choice}'. "
            f"Choose one of: {', '.join(IDENTITY_CHOICES)}."
        )
    _requested_identity = choice
    # An identity only means something attached to a logged call. With call
    # logging off there is no line to attach it to, so the setting is off
    # rather than merely unused -- nothing reports an identity that is not
    # being written, and enabling logging later cannot pick up an account
    # name the operator has since forgotten they asked for.
    _identity = choice if _enabled else IDENTITY_NONE

    # The flag has to be enough on its own: the server's default level is
    # WARNING, so lines emitted at INFO would otherwise go nowhere and the
    # setting would look broken. Raising this logger alone leaves every other
    # logger at whatever -v selected; records reach the root handlers even
    # though the root logger sits at a higher level.
    if _enabled:
        logger.setLevel(logging.INFO)


def configured() -> tuple:
    """The active settings, as ``(enabled, identity)``."""
    return _enabled, _identity


def enabled() -> bool:
    """Whether tool calls are being logged."""
    return _enabled


def identity() -> str:
    """Which caller identity lines carry. ``"none"`` when logging is off."""
    return _identity


def identity_ignored() -> bool:
    """Whether a caller identity was asked for but call logging is off.

    Lets the entry point point out a setting that will do nothing.
    """
    return not _enabled and _requested_identity != IDENTITY_NONE


def logs_personal_data() -> bool:
    """Whether the current settings can write an account name to the log.

    Lets the entry point say so at startup: an operator turning this on is
    taking on the handling of it.
    """
    # configure() already gates the identity on _enabled, so this cannot be
    # true while nothing is being logged.
    return _identity == IDENTITY_USERNAME


def _identity_fields(creds: Optional[Dict[str, Any]]) -> list:
    """The identity part of a line, as ``key=value`` pairs.

    ``creds`` is what the HTTP middleware resolved for this request, or None
    in stdio mode, where there is no per-request identity and the server's
    configured profile is the only one there is.
    """
    if _identity == IDENTITY_NONE:
        return []

    # Imported here: this module is loaded by the entry point before the env
    # file is read, and connection_manager reads the environment on import.
    from .connection_manager import default_profile_name, profile_credentials

    if creds is None:
        profile = default_profile_name()
        fields = [f"profile={profile}"]
        if _identity == IDENTITY_USERNAME:
            username = profile_credentials(profile).get("username") or _UNKNOWN
            fields.append(f"user={username}")
        return fields

    fields = [f"profile={creds.get('profile') or _UNKNOWN}"]
    if _identity == IDENTITY_USERNAME:
        # Token and secret auth do not tell the server which account is
        # behind them, and the credentials carry a placeholder username in
        # that case. Reporting it would put a name in the log that nobody
        # authenticated as, so say the account is unknown instead.
        username = (
            creds.get("username") if creds.get("username_supplied") else None
        )
        fields.append(f"user={username or _UNKNOWN}")
        fields.append(f"auth={creds.get('auth_mode') or _UNKNOWN}")
    return fields


def log_call(
    tool: str,
    creds: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
) -> None:
    """Write one line for a tool call, if call logging is on.

    Args:
        tool: Name of the tool being dispatched.
        creds: Credentials the HTTP middleware resolved for this request, or
            None in stdio mode.
        session_id: The MCP session this call belongs to. Falls back to the
            one recorded on ``creds``.
    """
    if not _enabled:
        return

    fields = [f"tool={tool}"]

    session = session_id or (creds or {}).get("session_id")
    fields.append(f"session={session or _UNKNOWN}")

    if creds is not None and creds.get("host"):
        fields.append(f"host={creds['host']}")

    fields.extend(_identity_fields(creds))
    logger.info("tool call %s", " ".join(fields))
