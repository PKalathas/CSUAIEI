"""Instructor-facing API routes.

Two URL shapes coexist (same back-compat dance as student routes):

* ``/api/v1/courses/{course_id}/instructor/upload`` and ``/indexer/status``
  — multi-tenant; each call uses the per-course harness's config (which
  carries the course-specific blob container + indexer name).
* ``/api/v1/instructor/upload`` and ``/instructor/indexer/status`` —
  legacy, resolves to the default course.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from agentic_system import LabHarness, SystemConfig
from server.auth import AuthedUser, require_course_instructor, require_instructor
from server.indexing import get_indexer_status, run_indexer, upload_blob
from server.migration import get_default_course
from server.schemas import FileResult, IndexerStatusResponse, UploadResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["instructor"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".html", ".md", ".txt", ".py", ".ipynb"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.get("/instructor/health")
async def health():
    return {"status": "ok"}


# =========================================================== course-scoped
@router.post(
    "/courses/{course_id}/instructor/upload",
    response_model=UploadResponse,
)
async def upload_files_for_course(
    course_id: str,
    request: Request,
    files: list[UploadFile],
    pair: tuple = Depends(require_course_instructor),
):
    _, course = pair
    harness = request.app.state.harnesses.get_or_create(course_id, course)
    return await _upload_files(files, harness.config)


@router.get(
    "/courses/{course_id}/instructor/indexer/status",
    response_model=IndexerStatusResponse,
)
async def indexer_status_for_course(
    course_id: str,
    request: Request,
    pair: tuple = Depends(require_course_instructor),
):
    _, course = pair
    harness = request.app.state.harnesses.get_or_create(course_id, course)
    return await _indexer_status(harness.config)


# =========================================================== legacy
@router.post("/instructor/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    files: list[UploadFile],
    user: AuthedUser = Depends(require_instructor),
):
    harness = _default_harness(request)
    return await _upload_files(files, harness.config)


@router.get("/instructor/indexer/status", response_model=IndexerStatusResponse)
async def indexer_status(
    request: Request,
    user: AuthedUser = Depends(require_instructor),
):
    harness = _default_harness(request)
    return await _indexer_status(harness.config)


# =========================================================== internals
async def _upload_files(
    files: list[UploadFile], config: SystemConfig
) -> UploadResponse:
    if not config.indexing_enabled:
        raise HTTPException(status_code=503, detail="Indexing is not configured")

    results: list[FileResult] = []
    for f in files:
        ext = PurePosixPath(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            results.append(
                FileResult(
                    filename=f.filename or "",
                    blob_url="",
                    error=f"Unsupported file type: {ext}",
                )
            )
            continue

        data = await f.read()
        if len(data) > MAX_FILE_SIZE:
            results.append(
                FileResult(
                    filename=f.filename or "",
                    blob_url="",
                    error="File exceeds 10 MB limit",
                )
            )
            continue

        try:
            blob_url = await asyncio.to_thread(upload_blob, config, f.filename, data)
            results.append(FileResult(filename=f.filename or "", blob_url=blob_url))
        except Exception:
            logger.exception("Blob upload failed for %s", f.filename)
            results.append(
                FileResult(filename=f.filename or "", blob_url="", error="Upload failed")
            )

    successful = [r for r in results if r.error is None]
    indexer_triggered = False
    if successful:
        try:
            await asyncio.to_thread(run_indexer, config)
            indexer_triggered = True
        except Exception:
            logger.exception("Indexer trigger failed")

    return UploadResponse(
        files=results,
        indexer_triggered=indexer_triggered,
        message=f"{len(successful)}/{len(results)} files uploaded"
        + (", indexer triggered" if indexer_triggered else ""),
    )


async def _indexer_status(config: SystemConfig) -> IndexerStatusResponse:
    if not config.indexing_enabled:
        raise HTTPException(status_code=503, detail="Indexing is not configured")
    try:
        status = await asyncio.to_thread(get_indexer_status, config)
    except Exception:
        logger.exception("Failed to fetch indexer status")
        raise HTTPException(status_code=502, detail="Failed to fetch indexer status")
    return IndexerStatusResponse(
        status=status.get("status", "unknown"),
        last_result=status.get("lastResult"),
    )


def _default_harness(request: Request) -> LabHarness:
    course = get_default_course(request.app.state.system_store)
    if course is None:
        raise HTTPException(
            status_code=503,
            detail="Default course is not configured; use the /courses/{id}/ routes",
        )
    return request.app.state.harnesses.get_or_create(course["id"], course)
