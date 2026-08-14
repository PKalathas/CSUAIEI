"""
Chainlit client shell — thin HTTP/SSE proxy to the ADFEL server.

This file is the ONLY place Chainlit is imported. It holds no agent logic:
every turn is forwarded to the remote server via HTTP, and step-progress
events are streamed back via SSE.

Authentication is **Cal Poly CAS**, but the server is authoritative: this
client only drives the browser redirect and carries the resulting token.

    browser → GET /login/cas            → 302 to Cal Poly CAS (or mock)
    CAS     → GET /login/cas/callback?ticket=…
            → POST {ticket} to server /api/v1/auth/cas/validate
            → set HttpOnly session cookie (the server JWT) → 302 /
    header_auth_callback reads the cookie → cl.User(metadata={"token": …})
    every API call attaches Authorization: Bearer <token> from that user

Required env:
    ADFEL_SERVER_URL    Base URL of the FastAPI server (default http://localhost:8080)
    CHAINLIT_AUTH_SECRET  Signs Chainlit's own session (required once auth is on)
    CAS_BASE_URL        Cal Poly CAS base, e.g. https://cas.calpoly.edu/cas
    CAS_SERVICE_URL     This app's approved callback, e.g. https://host/login/cas/callback
    CAS_MOCK            "1" to skip the real redirect (local dev). Recommended dev path.
    ADFEL_COOKIE_SECURE "1" to mark the session cookie Secure (HTTPS only). Leave
                        blank for http://localhost or the browser drops the cookie.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from http.cookies import SimpleCookie
from urllib.parse import quote

import chainlit as cl
import httpx
from chainlit.server import app as cl_app
from dotenv import load_dotenv
from fastapi.responses import HTMLResponse, RedirectResponse

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SERVER_URL = os.getenv("ADFEL_SERVER_URL", "http://localhost:8080")
CAS_BASE_URL = os.getenv("CAS_BASE_URL", "")
CAS_SERVICE_URL = os.getenv("CAS_SERVICE_URL", "")
CAS_MOCK = os.getenv("CAS_MOCK", "").lower() in ("1", "true", "yes")
COOKIE_SECURE = os.getenv("ADFEL_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
SESSION_COOKIE = "adfel_session"

# When neither a real CAS base nor the mock is set, the client assumes the
# server runs in dev bypass and lets users straight in (no redirect, no token).
CAS_CONFIGURED = CAS_MOCK or bool(CAS_BASE_URL)

_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(base_url=SERVER_URL, timeout=httpx.Timeout(300.0))
    return _http


# ------------------------------------------------------- CAS login routes
# Mounted on Chainlit's own FastAPI app so the browser-redirect flow lives
# at the browser-facing tier without a separate proxy.

@cl_app.get("/login/cas")
async def login_cas():
    if CAS_MOCK:
        # Skip the real redirect; the server's mock accepts any ticket.
        return RedirectResponse("/login/cas/callback?ticket=MOCK", status_code=302)
    if not CAS_BASE_URL or not CAS_SERVICE_URL:
        return HTMLResponse(
            "CAS is not configured on the client. Set CAS_BASE_URL and "
            "CAS_SERVICE_URL (or CAS_MOCK=1 for local dev).",
            status_code=500,
        )
    # `service` must match the server's cas_service_url byte-for-byte.
    target = f"{CAS_BASE_URL.rstrip('/')}/login?service={quote(CAS_SERVICE_URL, safe='')}"
    return RedirectResponse(target, status_code=302)


@cl_app.get("/login/cas/callback")
async def login_cas_callback(ticket: str = ""):
    if not ticket:
        return RedirectResponse("/login/cas", status_code=302)
    try:
        resp = await _client().post(
            "/api/v1/auth/cas/validate", json={"ticket": ticket}
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError):
        logger.exception("CAS ticket validation failed")
        return HTMLResponse(
            "Sign-in failed. <a href='/login/cas'>Try again</a>.", status_code=401
        )

    redirect = RedirectResponse("/", status_code=302)
    redirect.set_cookie(
        SESSION_COOKIE,
        data["token"],
        max_age=data.get("expires_in"),
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return redirect


@cl_app.middleware("http")
async def _bounce_unauthenticated_to_cas(request, call_next):
    """Send a fresh browser hitting the app root to CAS before the SPA loads."""
    if (
        CAS_CONFIGURED
        and request.method == "GET"
        and request.url.path == "/"
        and SESSION_COOKIE not in request.cookies
    ):
        return RedirectResponse("/login/cas", status_code=302)
    return await call_next(request)


# ------------------------------------------------------------------ auth

@cl.header_auth_callback
def header_auth_callback(headers: dict) -> cl.User | None:
    if not CAS_CONFIGURED:
        # No CAS configured → assume the server is in dev bypass.
        return cl.User(identifier="dev")

    token = _cookie_value(headers, SESSION_COOKIE)
    if not token:
        return None
    claims = _jwt_claims_unverified(token)  # server already verified the signature
    email = claims.get("email")
    if not email:
        return None
    return cl.User(
        identifier=email,
        metadata={"token": token, "role": claims.get("role", "student")},
    )


def _cookie_value(headers: dict, name: str) -> str | None:
    raw = headers.get("cookie") or headers.get("Cookie")
    if not raw:
        return None
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return None
    morsel = jar.get(name)
    return morsel.value if morsel else None


def _jwt_claims_unverified(token: str) -> dict:
    """Decode the JWT payload for display only (signature NOT verified here —
    the server verifies it on every API call)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # restore base64 padding
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _auth_headers() -> dict:
    """Per-user Bearer header pulled from the authed cl.User (never the
    shared httpx client, which would leak one user's token to all)."""
    user = cl.user_session.get("user")
    meta = getattr(user, "metadata", None) or {}
    token = meta.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


# ------------------------------------------------------------------ callbacks

@cl.on_chat_start
async def on_start() -> None:
    client = _client()
    resp = await client.post("/api/v1/sessions", headers=_auth_headers())
    resp.raise_for_status()
    data = resp.json()

    cl.user_session.set("session_id", data["session_id"])

    intro = (
        "Welcome to the CSC 580 Lab Companion. I'll help you work through "
        "your assignments by giving hints, not answers. Ask me about the "
        "lab manual, concepts you want to understand, or errors you're "
        "running into."
    )
    if data.get("resuming"):
        intro += (
            f"\n\n*(Picking up where we left off — "
            f"{data['total_questions']} prior questions on file.)*"
        )
    await cl.Message(content=intro).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    session_id: str | None = cl.user_session.get("session_id")
    if session_id is None:
        await on_start()
        session_id = cl.user_session.get("session_id")

    client = _client()
    url = f"/api/v1/sessions/{session_id}/turn"
    result_data: dict | None = None

    try:
        async with client.stream(
            "POST", url, json={"message": message.content}, headers=_auth_headers()
        ) as resp:
            resp.raise_for_status()
            event_type: str | None = None

            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: ") and event_type:
                    data = json.loads(line[6:])

                    if event_type == "step":
                        async with cl.Step(name=data["name"], type=data["type"]) as step:
                            step.output = data["output"]
                    elif event_type == "result":
                        result_data = data
                    elif event_type == "error":
                        logger.error("Server error: %s", data.get("detail"))
                        await cl.Message(
                            content="Sorry — something went wrong on my side. Please try again."
                        ).send()
                        return

                    event_type = None

    except (httpx.HTTPStatusError, httpx.RequestError):
        logger.exception("Request to server failed")
        await cl.Message(
            content="Sorry — something went wrong on my side. Please try again."
        ).send()
        return

    if result_data:
        await cl.Message(content=result_data["response"]).send()


@cl.on_chat_end
async def on_end() -> None:
    session_id: str | None = cl.user_session.get("session_id")
    if session_id is None:
        return
    client = _client()
    try:
        await client.delete(
            f"/api/v1/sessions/{session_id}", headers=_auth_headers()
        )
    except Exception:
        logger.exception("end_session failed")
