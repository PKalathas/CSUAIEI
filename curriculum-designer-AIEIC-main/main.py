"""
AIEIC Curriculum Designer — FastAPI entry point.

Port: 8003
Generates lab materials (spec, quiz, rubric) from learning objectives, and
supports the instructor approval workflow.

Per INTERFACE_CONTRACT.md §458–554.

Quick start:
    pip install -r requirements.txt
    cp .env.example .env
    uvicorn main:app --host 0.0.0.0 --port 8003 --reload

Stages:
  A. Skeleton — endpoints return hardcoded drafts (current)
  B. LangGraph + Azure OpenAI generation
  C. Approval iteration + check-typos (LLM)
  D. Tests + Orchestrator integration
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from graphs.generation import build_generation_graph
from routers.curriculum import router as curriculum_router
from services.llm import build_llm_client
from services.storage import build_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-30s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("─" * 60)
    logger.info(f"AIEIC Curriculum Designer starting up — v{settings.version}")
    logger.info("─" * 60)

    # ── Storage backend ───────────────────────────────────────────────────────
    app.state.store = build_store(settings.storage_backend)
    logger.info(f"  ✓  storage: {settings.storage_backend}")

    # ── LLM client ────────────────────────────────────────────────────────────
    app.state.llm_client = build_llm_client(settings)
    logger.info(f"  ✓  llm backend: {settings.llm_backend}")

    # ── Generation graph ──────────────────────────────────────────────────────
    app.state.generation_graph = build_generation_graph()
    logger.info("  ✓  generation graph compiled")

    logger.info(f"  ✓  ready on port {settings.service_port}")
    logger.info("─" * 60)

    yield  # ── app is running ────────────────────────────────────────────────

    logger.info("Curriculum Designer shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AIEIC Curriculum Designer",
    description=(
        "Generates lab materials (spec, quiz, rubric) from learning objectives. "
        "See INTERFACE_CONTRACT.md §458–554 for the full API contract."
    ),
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # TODO production: restrict to Orchestrator origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(curriculum_router)


# ── Error envelope (contract §97–107) ─────────────────────────────────────────
# Contract requires non-2xx responses look like:
#   { "error": { "code": ..., "message": ..., "agent": ..., "request_id": ... } }
# FastAPI's default HTTPException nests payloads under "detail", so we
# re-shape it here. Routers raise HTTPException(detail={"error": {...}}) and
# this handler strips the "detail" wrapper.

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        body = exc.detail
    else:
        body = {
            "error": {
                "code": "HTTP_" + str(exc.status_code),
                "message": str(exc.detail),
                "agent": settings.service_name,
            }
        }
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request body failed schema validation.",
                "agent": settings.service_name,
                "details": exc.errors(),
            }
        },
    )


# ── Root / health ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "agent": settings.service_name, "version": settings.version}


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": settings.service_name, "version": settings.version}


# ── Dev entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.service_port, reload=False)
