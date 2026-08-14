"""Auth routes — the CAS login handshake.

``POST /api/v1/auth/cas/validate`` is the **only** auth-free route in the
app (it's the thing that establishes auth). The browser-facing Chainlit
client drives the CAS redirect, receives the service ticket, and hands it
here; the server validates it back-channel, resolves/creates the user, and
returns a short-lived session JWT that the client then carries as
``Authorization: Bearer`` on every subsequent request.

CAS validation + store access are synchronous, so the handler offloads them
to a worker thread (mirrors the ``asyncio.to_thread`` pattern in
``server/routes/student.py``).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request

from agentic_system import SystemConfig
from agentic_system.store import SystemStore
from server.auth import (
    mint_session_jwt,
    resolve_or_create_user,
    validate_cas_ticket,
)
from server.schemas import CasValidateRequest, CasValidateResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/cas/validate", response_model=CasValidateResponse)
async def validate_cas(body: CasValidateRequest, request: Request):
    cfg: SystemConfig = request.app.state.config
    store: SystemStore = request.app.state.system_store

    def _do() -> str:
        identity = validate_cas_ticket(body.ticket, cfg)
        user = resolve_or_create_user(
            store,
            sso_subject=identity["netid"],
            email=identity["email"],
            name=identity["name"],
            admin_email=cfg.admin_email,
        )
        return mint_session_jwt(user, cfg)

    token = await asyncio.to_thread(_do)
    return CasValidateResponse(token=token, expires_in=cfg.session_jwt_ttl)
