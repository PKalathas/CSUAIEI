"""Student-facing API routes.

Two URL shapes coexist:

* ``/api/v1/courses/{course_id}/sessions[...]`` — the multi-tenant shape.
  Every call resolves the right per-course ``LabHarness`` via
  ``app.state.harnesses`` and enforces enrollment via
  ``require_course_member``.

* ``/api/v1/sessions[...]`` — the legacy single-course shape. Preserved so
  the existing Chainlit client keeps working; resolves to the "default
  course" created at first boot by ``server/migration.py``.

Each session carries ``state.student_id`` (the authed user id), and the
turn / delete handlers check that the caller matches.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from agentic_system import LabHarness
from server.auth import AuthedUser, require_course_member, require_user
from server.migration import get_default_course
from server.schemas import CreateSessionResponse, TurnRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["student"])


# =========================================================== course-scoped
@router.post("/courses/{course_id}/sessions", response_model=CreateSessionResponse)
async def create_session_for_course(
    course_id: str,
    request: Request,
    pair: tuple = Depends(require_course_member),
):
    user, course = pair
    harness = _harness_for_course(request, course)
    return await _create_session(request, harness, user)


@router.post("/courses/{course_id}/sessions/{session_id}/turn")
async def handle_turn_for_course(
    course_id: str,
    session_id: str,
    body: TurnRequest,
    request: Request,
    pair: tuple = Depends(require_course_member),
):
    user, course = pair
    harness = _harness_for_course(request, course)
    return await _handle_turn(request, harness, session_id, body, user)


@router.delete("/courses/{course_id}/sessions/{session_id}", status_code=204)
async def delete_session_for_course(
    course_id: str,
    session_id: str,
    request: Request,
    pair: tuple = Depends(require_course_member),
):
    user, course = pair
    harness = _harness_for_course(request, course)
    await _delete_session(request, harness, session_id, user)


# =========================================================== legacy
@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    request: Request,
    user: AuthedUser = Depends(require_user),
):
    harness = _default_harness(request)
    return await _create_session(request, harness, user)


@router.post("/sessions/{session_id}/turn")
async def handle_turn(
    session_id: str,
    body: TurnRequest,
    request: Request,
    user: AuthedUser = Depends(require_user),
):
    harness = _default_harness(request)
    return await _handle_turn(request, harness, session_id, body, user)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    request: Request,
    user: AuthedUser = Depends(require_user),
):
    harness = _default_harness(request)
    await _delete_session(request, harness, session_id, user)


# =========================================================== internals
async def _create_session(
    request: Request, harness: LabHarness, user: AuthedUser
) -> CreateSessionResponse:
    registry = request.app.state.sessions
    state = await asyncio.to_thread(harness.start_session, student_id=user.id)
    registry.put(state)
    return CreateSessionResponse(
        session_id=state.session_id,
        total_questions=state.student_context.total_questions,
        resuming=state.student_context.total_questions > 0,
    )


async def _handle_turn(
    request: Request,
    harness: LabHarness,
    session_id: str,
    body: TurnRequest,
    user: AuthedUser,
):
    registry = request.app.state.sessions
    state = registry.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.student_id and state.student_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Session belongs to another user")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_step(name: str, step_type: str, output: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            ("step", {"name": name, "type": step_type, "output": output}),
        )

    async def event_generator():
        task = asyncio.get_running_loop().run_in_executor(
            None,
            lambda: harness.handle_turn(state, body.message, on_step=on_step),
        )

        done = False
        while not done:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.1)
                event_type, data = item
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
            except asyncio.TimeoutError:
                if task.done():
                    while not queue.empty():
                        item = queue.get_nowait()
                        event_type, data = item
                        yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                    done = True

        try:
            result = task.result()
            yield f"event: result\ndata: {json.dumps(asdict(result))}\n\n"
        except Exception:
            logger.exception("handle_turn failed for session %s", session_id)
            yield f"event: error\ndata: {json.dumps({'detail': 'Internal processing error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _delete_session(
    request: Request, harness: LabHarness, session_id: str, user: AuthedUser
) -> None:
    registry = request.app.state.sessions
    state = registry.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.student_id and state.student_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Session belongs to another user")
    registry.remove(session_id)
    try:
        await asyncio.to_thread(harness.end_session, state)
    except Exception:
        logger.exception("end_session failed for %s", session_id)


def _harness_for_course(request: Request, course: dict) -> LabHarness:
    return request.app.state.harnesses.get_or_create(course["id"], course)


def _default_harness(request: Request) -> LabHarness:
    course = get_default_course(request.app.state.system_store)
    if course is None:
        raise HTTPException(
            status_code=503,
            detail="Default course is not configured; use the /courses/{id}/ routes",
        )
    return request.app.state.harnesses.get_or_create(course["id"], course)
