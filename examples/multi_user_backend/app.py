# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""FastAPI multi-user backend for tigergraph-mcp.

Demonstrates Pattern A: each logged-in user owns one tigergraph-mcp
subprocess + one agent runtime. The frontend backend authenticates
credentials against TigerGraph upfront via ``pyTigerGraph.getToken()``,
keeps only the resulting token in memory, and tears the session down
on logout or idle timeout.

Run with:

    uvicorn examples.multi_user_backend.app:app --reload
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pyTigerGraph import AsyncTigerGraphConnection
from pyTigerGraph.common.exception import TigerGraphException

from .user_sessions import UserSessionManager

sessions = UserSessionManager(
    model=os.environ.get("LLM_MODEL", "openai:gpt-4.1-mini-2025-04-14"),
    max_sessions=int(os.environ.get("MAX_SESSIONS", "100")),
    idle_timeout_seconds=int(os.environ.get("SESSION_IDLE_TIMEOUT", "1800")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await sessions.start()
    try:
        yield
    finally:
        await sessions.shutdown()


app = FastAPI(title="tigergraph-mcp multi-user backend", lifespan=lifespan)


class LoginRequest(BaseModel):
    user_id: str = Field(..., description="Stable identifier for the logged-in user.")
    tg_host: str = Field(..., description="TigerGraph host URL, e.g. https://acme.tgcloud.io.")
    tg_username: str = Field(..., description="TigerGraph username.")
    tg_password: str = Field(..., description="TigerGraph password.")
    graphname: Optional[str] = Field(None, description="Default graph for this session (optional).")


class ChatRequest(BaseModel):
    user_id: str
    message: str


@app.post("/login")
async def login(req: LoginRequest):
    """Validate creds against TigerGraph, mint a token, build the user's agent."""
    conn = AsyncTigerGraphConnection(
        host=req.tg_host,
        username=req.tg_username,
        password=req.tg_password,
        graphname=req.graphname or "",
    )
    try:
        await conn.getToken()
        token = conn.apiToken
    except TigerGraphException as e:
        raise HTTPException(status_code=401, detail=f"TigerGraph auth failed: {e}")
    finally:
        try:
            await conn.aclose()
        except Exception:
            pass

    if not token:
        raise HTTPException(status_code=401, detail="No token returned from TigerGraph")

    await sessions.login(
        req.user_id,
        tg_host=req.tg_host,
        tg_token=token,
        graphname=req.graphname,
    )
    return {"status": "ok", "user_id": req.user_id}


@app.post("/chat")
async def chat(req: ChatRequest):
    if sessions.get(req.user_id) is None:
        raise HTTPException(status_code=401, detail="not logged in")
    try:
        reply = await sessions.chat(req.user_id, req.message)
    except LookupError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return {"reply": reply}


@app.post("/logout")
async def logout(user_id: str):
    removed = await sessions.logout(user_id)
    return {"status": "ok", "logged_out": removed}


@app.get("/health")
async def health():
    return {"status": "ok", "active_sessions": len(sessions._sessions)}
