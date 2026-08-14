"""Admin / multi-tenant CRUD routes.

* ``/admin/users``  — admin-only user lifecycle.
* ``/admin/courses`` — instructor-owned course lifecycle. Course creation
  side-effects provision per-course resources (blob container; SQLite dir
  materializes lazily on first session). Course deletion tears them down.
* ``/admin/courses/{cid}/enroll`` — instructor adds a student by email.
  If the email isn't on the system yet, a placeholder ``student`` row is
  created with ``sso_subject=NULL`` — it binds on first SSO login.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from agentic_system.store import SystemStore
from server.auth import (
    AuthedUser,
    require_admin,
    require_course_instructor,
    require_instructor,
)
from server.provisioning import (
    create_course_resources,
    delete_course_resources,
    derive_resource_names,
)
from server.schemas import (
    CourseCreate,
    CourseDeleteResponse,
    CourseOut,
    CoursePatch,
    EnrollRequest,
    EnrollmentOut,
    UserCreate,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================ users
@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    request: Request,
    _: AuthedUser = Depends(require_admin),
):
    store: SystemStore = request.app.state.system_store
    if store.get_user_by_email(body.email) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    row = {
        "id": str(uuid.uuid4()),
        "email": body.email,
        "name": body.name,
        "sso_subject": None,
        "role": body.role,
        "created_at": _now_iso(),
    }
    store.insert_user(row)
    return _user_out(row)


@router.get("/users", response_model=list[UserOut])
async def list_users(
    request: Request,
    _: AuthedUser = Depends(require_admin),
):
    store: SystemStore = request.app.state.system_store
    return [_user_out(u) for u in store.list_users()]


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    request: Request,
    _: AuthedUser = Depends(require_admin),
):
    store: SystemStore = request.app.state.system_store
    row = store.get_user(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_out(row)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    request: Request,
    _: AuthedUser = Depends(require_admin),
):
    store: SystemStore = request.app.state.system_store
    if store.get_user(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    store.delete_user(user_id)


# ============================================================ courses
@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(
    body: CourseCreate,
    request: Request,
    user: AuthedUser = Depends(require_instructor),
):
    store: SystemStore = request.app.state.system_store

    course_id = str(uuid.uuid4())
    names = derive_resource_names(
        course_id,
        overrides={
            "blob_container_name": body.blob_container_name,
            "search_index_name": body.search_index_name,
            "search_indexer_name": body.search_indexer_name,
            "search_datasource_name": body.search_datasource_name,
        },
    )

    row = {
        "id": course_id,
        "name": body.name,
        "instructor_id": user.id,
        "blob_container_name": names["blob_container_name"],
        "search_index_name": names["search_index_name"],
        "search_indexer_name": names["search_indexer_name"],
        "search_datasource_name": names["search_datasource_name"],
        "participant_db_path": None,
        "guardian_db_path": None,
        "created_at": _now_iso(),
    }

    cfg = request.app.state.config
    try:
        await asyncio.to_thread(create_course_resources, cfg, row)
    except Exception as e:
        logger.exception("Course resource provisioning failed for %s", course_id)
        raise HTTPException(status_code=502, detail=f"Resource provisioning failed: {e}")

    try:
        store.insert_course(row)
    except Exception:
        logger.exception("Insert course row failed for %s; rolling back blob container", course_id)
        try:
            await asyncio.to_thread(delete_course_resources, cfg, row, cfg.data_root)
        except Exception:  # pragma: no cover
            logger.exception("Rollback of blob container failed for %s", course_id)
        raise

    # Eagerly build the harness so SQLite files materialize and any
    # configuration error surfaces here instead of on the first student turn.
    request.app.state.harnesses.get_or_create(course_id, row)

    return _course_out(row)


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(
    request: Request,
    user: AuthedUser = Depends(require_instructor),
):
    store: SystemStore = request.app.state.system_store
    if user.role == "admin":
        rows = store.list_courses()
    else:
        rows = store.list_courses(instructor_id=user.id)
    return [_course_out(r) for r in rows]


@router.get("/courses/{course_id}", response_model=CourseOut)
async def get_course(
    course_id: str,
    request: Request,
    pair: tuple = Depends(require_course_instructor),
):
    _, course = pair
    return _course_out(course)


@router.patch("/courses/{course_id}", response_model=CourseOut)
async def patch_course(
    course_id: str,
    body: CoursePatch,
    request: Request,
    pair: tuple = Depends(require_course_instructor),
):
    store: SystemStore = request.app.state.system_store
    _, course = pair
    patch: dict = {}
    if body.name is not None:
        patch["name"] = body.name
    if patch:
        store.update_course(course_id, patch)
        course = store.get_course(course_id) or course
    return _course_out(course)


@router.delete("/courses/{course_id}", response_model=CourseDeleteResponse)
async def delete_course(
    course_id: str,
    request: Request,
    pair: tuple = Depends(require_course_instructor),
):
    store: SystemStore = request.app.state.system_store
    _, course = pair

    request.app.state.harnesses.evict(course_id)

    cfg = request.app.state.config
    leftover = await asyncio.to_thread(delete_course_resources, cfg, course, cfg.data_root)
    store.delete_course(course_id)

    return CourseDeleteResponse(id=course_id, leftover_resources=leftover)


# ============================================================ enrollments
@router.post(
    "/courses/{course_id}/enroll",
    response_model=EnrollmentOut,
    status_code=201,
)
async def enroll_student(
    course_id: str,
    body: EnrollRequest,
    request: Request,
    pair: tuple = Depends(require_course_instructor),
):
    store: SystemStore = request.app.state.system_store
    _, _course = pair

    user = store.get_user_by_email(body.email)
    if user is None:
        user = {
            "id": str(uuid.uuid4()),
            "email": body.email,
            "name": body.name,
            "sso_subject": None,
            "role": "student",
            "created_at": _now_iso(),
        }
        store.insert_user(user)
        logger.info("Created placeholder student %s on enrollment", body.email)

    enrolled_at = _now_iso()
    store.insert_enrollment(course_id, user["id"], enrolled_at)
    return EnrollmentOut(
        course_id=course_id,
        user=_user_out(user),
        enrolled_at=enrolled_at,
    )


@router.get(
    "/courses/{course_id}/enrollments",
    response_model=list[UserOut],
)
async def list_enrollments(
    course_id: str,
    request: Request,
    pair: tuple = Depends(require_course_instructor),
):
    store: SystemStore = request.app.state.system_store
    return [_user_out(u) for u in store.list_enrolled_users(course_id)]


@router.delete(
    "/courses/{course_id}/enrollments/{user_id}",
    status_code=204,
)
async def unenroll_student(
    course_id: str,
    user_id: str,
    request: Request,
    pair: tuple = Depends(require_course_instructor),
):
    store: SystemStore = request.app.state.system_store
    if not store.is_enrolled(course_id, user_id):
        raise HTTPException(status_code=404, detail="Enrollment not found")
    store.delete_enrollment(course_id, user_id)


# ----------------------------------------------------------- helpers
def _user_out(row: dict) -> UserOut:
    return UserOut(
        id=row["id"],
        email=row["email"],
        name=row.get("name", ""),
        role=row["role"],
        sso_subject=row.get("sso_subject"),
        created_at=row["created_at"],
    )


def _course_out(row: dict) -> CourseOut:
    return CourseOut(
        id=row["id"],
        name=row["name"],
        instructor_id=row["instructor_id"],
        blob_container_name=row["blob_container_name"],
        search_index_name=row["search_index_name"],
        search_indexer_name=row["search_indexer_name"],
        search_datasource_name=row["search_datasource_name"],
        created_at=row["created_at"],
    )


def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat() + "Z"
