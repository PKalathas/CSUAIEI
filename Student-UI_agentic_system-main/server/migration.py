"""Idempotent startup migration for the multi-tenant system DB.

Two pieces:

1. Seed an admin user. Source of truth is ``SystemConfig.admin_email``. If
   that's not set, we drop a "legacy" admin so the default course still
   has an owner (production deployments should set the env var).
2. Seed a "default" course pointed at the legacy SQLite paths and the
   legacy ``AZURE_*`` env vars. This keeps the existing un-prefixed routes
   (``POST /api/v1/sessions`` etc.) working while the new multi-course
   routes come online.

Both steps run only when their target tables are empty — re-running the
server is safe.
"""

from __future__ import annotations

import datetime as _dt
import logging
import uuid
from typing import Optional

from agentic_system import SystemConfig
from agentic_system.store import SystemStore

logger = logging.getLogger(__name__)

DEFAULT_COURSE_NAME = "Default Course"
LEGACY_ADMIN_EMAIL = "legacy-admin@adfel.local"


def bootstrap(store: SystemStore, config: SystemConfig) -> dict:
    """Run idempotent bootstrap.

    Returns a small dict describing what was created (useful for logs /
    tests). Safe to call on every boot.
    """
    created = {"admin": None, "default_course": None}

    admin = _ensure_admin(store, config)
    if admin and admin.get("_newly_created"):
        created["admin"] = admin["id"]

    default_course = _ensure_default_course(store, config, admin)
    if default_course and default_course.get("_newly_created"):
        created["default_course"] = default_course["id"]

    return created


def get_default_course(store: SystemStore) -> Optional[dict]:
    """Return the legacy default course row, or None if no courses exist."""
    courses = store.list_courses()
    return courses[0] if courses else None


# --------------------------------------------------------------- helpers
def _ensure_admin(store: SystemStore, config: SystemConfig) -> Optional[dict]:
    existing = store.list_users()
    if existing:
        return next((u for u in existing if u["role"] == "admin"), existing[0])

    email = config.admin_email or LEGACY_ADMIN_EMAIL
    new = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": "ADFEL Admin",
        "sso_subject": None,
        "role": "admin",
        "created_at": _now_iso(),
    }
    store.insert_user(new)
    if config.admin_email:
        logger.info(
            "Bootstrapped admin user %s (sso_subject will bind on first SSO login)",
            email,
        )
    else:
        logger.warning(
            "ADFEL_ADMIN_EMAIL not set; created placeholder admin %s. "
            "Set ADFEL_ADMIN_EMAIL before production deployment.",
            email,
        )
    new["_newly_created"] = True
    return new


def _ensure_default_course(
    store: SystemStore, config: SystemConfig, admin: Optional[dict]
) -> Optional[dict]:
    if store.list_courses():
        return None

    if admin is None:
        logger.warning("Cannot bootstrap default course — no admin user")
        return None

    course_id = str(uuid.uuid4())
    short = course_id.split("-")[0]

    # Point Azure resource names at whatever the legacy env-driven config
    # was using. If those vars are empty, the per-course harness's KB will
    # collapse to NullKB and indexing routes will refuse with 503 — same as
    # the pre-multi-tenant behavior.
    # Carry the legacy SQLite paths on the row so the registry's
    # course-dir convention doesn't strand legacy data. Persisting them
    # on the course row means later boots also keep reading the legacy
    # files instead of materializing empty ones under data/courses/{id}/.
    course = {
        "id": course_id,
        "name": DEFAULT_COURSE_NAME,
        "instructor_id": admin["id"],
        "blob_container_name": config.azure_blob_container or f"course-{short}",
        "search_index_name": config.azure_search_index or f"course-{short}-idx",
        "search_indexer_name": config.azure_search_indexer_name
            or f"course-{short}-indexer",
        "search_datasource_name": f"course-{short}-ds",
        "participant_db_path": str(config.participant_db_path),
        "guardian_db_path": str(config.guardian_db_path),
        "created_at": _now_iso(),
    }
    store.insert_course(course)
    logger.info(
        "Bootstrapped default course %s (id=%s, container=%s, index=%s, "
        "participant_db=%s, guardian_db=%s)",
        DEFAULT_COURSE_NAME, course_id,
        course["blob_container_name"], course["search_index_name"],
        course["participant_db_path"], course["guardian_db_path"],
    )
    course["_newly_created"] = True
    return course


def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat() + "Z"
