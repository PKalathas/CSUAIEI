"""Authentication and authorization for the multi-tenant ADFEL server.

Two halves:

* **Auth (`require_user`)** verifies the server-minted **session JWT** carried
  as ``Authorization: Bearer ...`` and builds an ``AuthedUser`` straight from
  its claims (no per-request DB lookup). The JWT is issued once, by the CAS
  validate endpoint (`server/routes/auth.py`), after a Cal Poly **CAS** ticket
  is validated back-channel here in `validate_cas_ticket`.
* **AuthZ (`require_admin`, `require_instructor`, `require_course_member`,
  `require_course_instructor`)** layer role / enrollment checks on top.

A dev bypass (`SystemConfig.dev_auth_bypass`) skips all of this and impersonates
either ``SystemConfig.dev_user_id`` or the admin row. Precedence in
``require_user``: ``dev_auth_bypass`` > session-JWT verification. The CAS layer
itself has a separate ``cas_mock`` switch (handled in `validate_cas_ticket`) so
the whole login flow is testable without a live Cal Poly IdP.

Heavy deps are lazy-imported per the repo convention: ``jwt`` (PyJWT) and
``httpx`` only load inside the helpers that use them.
"""

from __future__ import annotations

import datetime as _dt
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from agentic_system import SystemConfig
from agentic_system.store import SystemStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthedUser:
    id: str
    email: str
    name: str
    role: str  # 'admin' | 'instructor' | 'student'


# --------------------------------------------------------------- core deps
def require_user(request: Request) -> AuthedUser:
    """Resolve the request to an authenticated user.

    Verifies the session JWT and builds the user from its claims. Raises 401
    if the token is missing, invalid, or expired.
    """
    cfg: SystemConfig = request.app.state.config
    store: SystemStore = request.app.state.system_store

    if cfg.dev_auth_bypass:
        return _dev_bypass_user(store, cfg)

    token = _extract_bearer(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    claims = verify_session_jwt(token, cfg)
    return AuthedUser(
        id=claims["sub"],
        email=claims.get("email", ""),
        name=claims.get("name", ""),
        role=claims.get("role", "student"),
    )


def require_admin(user: AuthedUser = Depends(require_user)) -> AuthedUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def require_instructor(user: AuthedUser = Depends(require_user)) -> AuthedUser:
    if user.role not in ("admin", "instructor"):
        raise HTTPException(status_code=403, detail="Instructor role required")
    return user


def require_course_member(
    course_id: str,
    request: Request,
    user: AuthedUser = Depends(require_user),
) -> tuple[AuthedUser, dict]:
    """Resolve a course and assert the user can access it.

    Admin sees everything; the course instructor always sees their own;
    students must be enrolled. Returns (user, course_row).
    """
    store: SystemStore = request.app.state.system_store
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if user.role == "admin":
        return user, course
    if course["instructor_id"] == user.id:
        return user, course
    if store.is_enrolled(course_id, user.id):
        return user, course
    raise HTTPException(status_code=403, detail="Not enrolled in this course")


def require_course_instructor(
    course_id: str,
    request: Request,
    user: AuthedUser = Depends(require_user),
) -> tuple[AuthedUser, dict]:
    """Like `require_course_member`, but only admins / the course instructor pass."""
    store: SystemStore = request.app.state.system_store
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if user.role == "admin" or course["instructor_id"] == user.id:
        return user, course
    raise HTTPException(status_code=403, detail="Course instructor or admin required")


# ------------------------------------------------------------- CAS validation
def validate_cas_ticket(ticket: str, cfg: SystemConfig) -> dict:
    """Validate a CAS service ticket and return normalized identity.

    Returns ``{"netid", "email", "name"}``. When ``cfg.cas_mock`` is set, this
    short-circuits to a fixed mock identity with **no** network call — the
    local-dev counterpart of ``dev_auth_bypass`` but exercising the real
    resolve → mint → verify path. Otherwise it back-channels Cal Poly CAS 3.0
    (`/p3/serviceValidate`) so the released attributes (email/displayName) come
    through. ``httpx`` is imported lazily.

    ``service`` is the highest-risk CAS detail: it must be byte-for-byte
    identical to the value sent to ``/login``. We always use the server's own
    ``cfg.cas_service_url`` (never a caller-supplied value) so the two legs
    cannot drift.
    """
    if cfg.cas_mock:
        netid = cfg.dev_user_id or "mockstudent"
        email = cfg.admin_email or f"{netid}@{cfg.cas_email_domain}"
        logger.warning("CAS_MOCK active — authenticating mock netid %s", netid)
        return {"netid": netid, "email": email, "name": "Mock CAS User"}

    if not cfg.cas_enabled:
        raise HTTPException(
            status_code=500,
            detail="CAS is not configured (set CAS_BASE_URL, CAS_SERVICE_URL, "
            "SESSION_JWT_SECRET) and CAS_MOCK is off",
        )

    try:
        import httpx
    except ImportError as e:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail="httpx is not installed on the server"
        ) from e

    url = f"{cfg.cas_base_url.rstrip('/')}/p3/serviceValidate"
    params = {"service": cfg.cas_service_url, "ticket": ticket, "format": "json"}
    try:
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.info("CAS ticket validation request failed: %s", e)
        raise HTTPException(status_code=401, detail="CAS ticket validation failed") from e

    success = (data.get("serviceResponse") or {}).get("authenticationSuccess")
    if not success or not success.get("user"):
        logger.info("CAS rejected ticket: %s", data)
        raise HTTPException(status_code=401, detail="CAS authentication failed")

    netid = success["user"]
    attrs = success.get("attributes") or {}
    email = (
        _first(attrs.get("mail"))
        or _first(attrs.get("email"))
        or f"{netid}@{cfg.cas_email_domain}"
    )
    name = _first(attrs.get("displayName")) or _first(attrs.get("cn")) or netid
    return {"netid": netid, "email": email, "name": name}


def resolve_or_create_user(
    store: SystemStore,
    *,
    sso_subject: str,
    email: str,
    name: str,
    admin_email: str,
) -> AuthedUser:
    """Map a validated SSO identity to a `users` row (provider-neutral).

    Resolution order (preserves instructor pre-enrollment + late-binding):
      1. exact match by ``sso_subject`` (the CAS netid)
      2. pre-seeded row by email → late-bind the subject onto it
      3. bootstrap the admin if email matches ``admin_email``
      4. otherwise 401 — they must be enrolled first
    """
    row = store.get_user_by_sso_subject(sso_subject)
    if row is not None:
        return _to_authed(row)

    row = store.get_user_by_email(email)
    if row is not None:
        if not row.get("sso_subject"):
            store.update_user_sso_subject(row["id"], sso_subject)
        return _to_authed(row)

    if admin_email and email.lower() == admin_email.lower():
        new = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": name,
            "sso_subject": sso_subject,
            "role": "admin",
            "created_at": _now_iso(),
        }
        store.insert_user(new)
        logger.info("Bootstrapped admin user %s via CAS SSO", email)
        return _to_authed(new)

    raise HTTPException(
        status_code=401,
        detail="No account found for this email. Ask your instructor to enroll you.",
    )


# ----------------------------------------------------------- session JWT
def mint_session_jwt(user: AuthedUser, cfg: SystemConfig) -> str:
    """Issue a short-lived HS256 session token for an authenticated user."""
    jwt = _jwt()
    secret = _require_jwt_secret(cfg)
    now = _dt.datetime.now(_dt.timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "iat": now,
        "exp": now + _dt.timedelta(seconds=cfg.session_jwt_ttl),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_session_jwt(token: str, cfg: SystemConfig) -> dict:
    """Verify a session token and return its claims, or raise 401."""
    jwt = _jwt()
    secret = _require_jwt_secret(cfg)
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Session expired") from e
    except jwt.InvalidTokenError as e:
        logger.info("Rejected invalid session token: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token") from e


# --------------------------------------------------------------- helpers
def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _jwt():
    """Lazy-import PyJWT, surfacing a clear 500 if it's missing."""
    try:
        import jwt

        return jwt
    except ImportError as e:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail="PyJWT is not installed on the server"
        ) from e


def _require_jwt_secret(cfg: SystemConfig) -> str:
    if not cfg.session_jwt_secret:
        raise HTTPException(
            status_code=500, detail="SESSION_JWT_SECRET is not configured on the server"
        )
    return cfg.session_jwt_secret


def _first(val):
    """CAS p3/serviceValidate returns each attribute as a list; unwrap it."""
    if isinstance(val, list):
        return val[0] if val else None
    return val


def _dev_bypass_user(store: SystemStore, cfg: SystemConfig) -> AuthedUser:
    """Return a stub authed user without verifying a token.

    Priority: explicit ``cfg.dev_user_id`` → admin row → ephemeral admin
    (not persisted) as a last resort. Logged loudly so it's obvious in CI.
    """
    if cfg.dev_user_id:
        row = store.get_user(cfg.dev_user_id)
        if row is not None:
            return _to_authed(row)
        logger.warning(
            "ADFEL_DEV_USER_ID=%s but no such user; falling back to admin lookup",
            cfg.dev_user_id,
        )

    if cfg.admin_email:
        row = store.get_user_by_email(cfg.admin_email)
        if row is not None:
            return _to_authed(row)

    logger.warning("Dev auth bypass active: returning ephemeral admin user")
    return AuthedUser(
        id="dev-admin",
        email=cfg.admin_email or "dev@local",
        name="Dev Admin",
        role="admin",
    )


def _to_authed(row: dict) -> AuthedUser:
    return AuthedUser(
        id=row["id"],
        email=row["email"],
        name=row.get("name", ""),
        role=row["role"],
    )


def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat() + "Z"
