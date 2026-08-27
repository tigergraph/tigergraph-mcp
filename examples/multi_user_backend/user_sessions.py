# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Per-user MCP session manager.

Owns one tigergraph-mcp stdio subprocess + one agent runtime per
logged-in user, keyed by user_id. Subprocess lifetime tracks the
login session: spawned on `login`, torn down on `logout` or after
an idle timeout.

Pattern A from the multi-user deployment guide. The MCP server itself
is unmodified — each subprocess sees a single static profile populated
from env vars at spawn time.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)


@dataclass
class UserSession:
    """Lifetime bundle owned by UserSessionManager for one logged-in user."""

    user_id: str
    tg_host: str
    exit_stack: AsyncExitStack
    mcp_client: MultiServerMCPClient
    agent: Any
    request_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_activity_at: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_activity_at = time.monotonic()


class UserSessionManager:
    """Owns one tigergraph-mcp subprocess + agent per logged-in user.

    Public lifecycle:

      await mgr.start()                 # start the idle sweeper (optional)
      await mgr.login(user_id, ...)     # spawn subprocess, build agent
      session = mgr.get(user_id)        # look up; None if logged out
      await mgr.chat(user_id, message)  # route into the user's agent
      await mgr.logout(user_id)         # tear down subprocess + agent
      await mgr.shutdown()              # tear down everything

    Concurrency: each user has a per-session asyncio.Lock around `chat()`
    so two parallel requests for the same user run serially. Different
    users run concurrently.
    """

    def __init__(
        self,
        model: str = "openai:gpt-4.1-mini-2025-04-14",
        temperature: float = 0.1,
        max_sessions: int = 100,
        idle_timeout_seconds: int = 1800,
        idle_sweep_interval_seconds: int = 60,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_sessions = max_sessions
        self._idle_timeout = idle_timeout_seconds
        self._sweep_interval = idle_sweep_interval_seconds

        self._sessions: Dict[str, UserSession] = {}
        self._login_lock = asyncio.Lock()
        self._llm = init_chat_model(model=model, temperature=temperature)
        self._sweeper_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Begin the idle-session sweeper. Idempotent."""
        if self._sweeper_task is None or self._sweeper_task.done():
            self._sweeper_task = asyncio.create_task(self._sweep_idle_sessions())

    async def login(
        self,
        user_id: str,
        tg_host: str,
        tg_token: Optional[str] = None,
        tg_username: Optional[str] = None,
        tg_password: Optional[str] = None,
        graphname: Optional[str] = None,
    ) -> UserSession:
        """Spawn a tigergraph-mcp subprocess for this user and build their agent.

        Either ``tg_token`` (API token / JWT) or ``tg_username`` + ``tg_password``
        must be supplied. Token-based auth is preferred — the caller should
        validate the password against TigerGraph upfront (e.g. via
        ``AsyncTigerGraphConnection.getToken()``) and pass the minted token here.
        """
        if not tg_token and not (tg_username and tg_password):
            raise ValueError(
                "login requires tg_token or (tg_username + tg_password)"
            )

        async with self._login_lock:
            if user_id in self._sessions:
                self._sessions[user_id].touch()
                return self._sessions[user_id]

            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError(
                    f"max_sessions ({self._max_sessions}) reached; refusing login"
                )

            env: Dict[str, str] = {
                "TG_HOST": tg_host,
                # PATH/HOME so the subprocess can resolve its own deps.
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
            }
            if graphname:
                env["TG_GRAPHNAME"] = graphname
            if tg_token:
                env["TG_API_TOKEN"] = tg_token
            else:
                env["TG_USERNAME"] = tg_username or ""
                env["TG_PASSWORD"] = tg_password or ""

            stack = AsyncExitStack()
            try:
                mcp_client = MultiServerMCPClient(
                    {
                        "tigergraph": {
                            "transport": "stdio",
                            "command": "tigergraph-mcp",
                            "args": [],
                            "env": env,
                        }
                    }
                )
                tools = await mcp_client.get_tools()
                agent = create_react_agent(model=self._llm, tools=tools)

                session = UserSession(
                    user_id=user_id,
                    tg_host=tg_host,
                    exit_stack=stack,
                    mcp_client=mcp_client,
                    agent=agent,
                )
                self._sessions[user_id] = session
                logger.info("login user=%s host=%s", user_id, tg_host)
                return session
            except Exception:
                await stack.aclose()
                raise

    def get(self, user_id: str) -> Optional[UserSession]:
        """Return the session for ``user_id`` if logged in, else ``None``."""
        return self._sessions.get(user_id)

    async def chat(self, user_id: str, message: str) -> str:
        """Route ``message`` through the user's agent and return the reply text."""
        session = self.get(user_id)
        if session is None:
            raise LookupError(f"user '{user_id}' is not logged in")

        async with session.request_lock:
            session.touch()
            response = await session.agent.ainvoke(
                {"messages": [HumanMessage(content=message)]}
            )

        messages = response.get("messages") if isinstance(response, dict) else None
        if messages:
            return str(messages[-1].content)
        return ""

    async def logout(self, user_id: str) -> bool:
        """Tear down a user's session. Returns True if a session was removed."""
        async with self._login_lock:
            session = self._sessions.pop(user_id, None)
        if session is None:
            return False
        await self._teardown(session)
        logger.info("logout user=%s", user_id)
        return True

    async def shutdown(self) -> None:
        """Tear down all sessions and stop the sweeper."""
        if self._sweeper_task and not self._sweeper_task.done():
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sweeper_task = None

        async with self._login_lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            await self._teardown(session)

    async def _teardown(self, session: UserSession) -> None:
        try:
            await session.exit_stack.aclose()
        except Exception as e:
            logger.warning("exit_stack.aclose failed for user=%s: %s", session.user_id, e)
        close = getattr(session.mcp_client, "aclose", None)
        if close is not None:
            try:
                await close()
            except Exception as e:
                logger.warning("mcp_client.aclose failed for user=%s: %s", session.user_id, e)

    async def _sweep_idle_sessions(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._sweep_interval)
                cutoff = time.monotonic() - self._idle_timeout
                stale = [
                    uid
                    for uid, s in list(self._sessions.items())
                    if s.last_activity_at < cutoff
                ]
                for uid in stale:
                    logger.info("idle logout user=%s", uid)
                    await self.logout(uid)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("idle sweeper iteration failed")
