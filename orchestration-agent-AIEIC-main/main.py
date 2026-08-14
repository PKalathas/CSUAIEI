"""
AIEIC Orchestrator — FastAPI entry point.

Port: 8000
Single entry point for the frontend. Routes all requests to the
appropriate backend agents.

Quick start:
  # Install deps
  pip install -r requirements.txt

  # Run with all agents mocked (port 8001–8004 mocked automatically)
  python -m aieic_shared.mocks.run_all --no-participant  # if real participant is up
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  # Run against real agents (set URLs in .env)
  cp .env.example .env
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Architecture:
  - LangGraph StateGraph for student message flow (sequential, conditional)
  - asyncio.gather for dashboard aggregation (parallel)
  - aieic-shared typed clients for all downstream agent calls
  - In-memory session store for v0.1 (→ Cosmos DB in v0.2)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aieic_shared.clients.assessment import AssessmentClient
from aieic_shared.clients.companion import LabCompanionClient
from aieic_shared.clients.curriculum import CurriculumClient
from aieic_shared.clients.integrity import IntegrityClient
from aieic_shared.clients.participant import ParticipantClient

from config import settings
from graphs.student_message import build_student_message_graph
from routers.instructor import router as instructor_router
from routers.student import router as student_router
from services.dashboard import DashboardService
from services.session import SessionStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-30s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: create one shared httpx client per agent, build the LangGraph,
    attach everything to app.state for use by routers.

    Shutdown: close all httpx clients cleanly.

    Using one shared client per agent means a single connection pool is reused
    across all requests — much more efficient than creating a client per request.
    """
    logger.info("─" * 60)
    logger.info("AIEIC Orchestrator starting up")
    logger.info("─" * 60)

    # ── Create typed HTTP clients ──────────────────────────────────────────
    participant = ParticipantClient(base_url=settings.participant_url)
    companion   = LabCompanionClient(base_url=settings.companion_url)
    curriculum  = CurriculumClient(base_url=settings.curriculum_url)
    assessment  = AssessmentClient(base_url=settings.assessment_url)
    integrity   = IntegrityClient(
        base_url=settings.integrity_url,
        internal_token=settings.integrity_token,
    )

    # ── Health-check all agents at startup (non-fatal) ─────────────────────
    for name, client, url in [
        ("participant",  participant, settings.participant_url),
        ("companion",    companion,   settings.companion_url),
        ("curriculum",   curriculum,  settings.curriculum_url),
        ("assessment",   assessment,  settings.assessment_url),
        ("integrity",    integrity,   settings.integrity_url),
    ]:
        try:
            h = await client.health()
            logger.info(f"  ✓  {name:<14} {url}  [{h.status}]")
        except Exception as exc:
            logger.warning(f"  ✗  {name:<14} {url}  UNAVAILABLE — {exc}")
            logger.warning(f"     Requests to {name} will fail until it comes up.")

    # ── Build LangGraph (student message flow) ─────────────────────────────
    student_message_graph = build_student_message_graph(participant, companion, integrity)
    logger.info("  ✓  LangGraph compiled (student message flow)")

    # ── Build dashboard service ────────────────────────────────────────────
    dashboard_service = DashboardService(participant, assessment, curriculum)

    # ── Session store (in-memory, v0.1) ────────────────────────────────────
    session_store = SessionStore(ttl_seconds=settings.session_ttl_seconds)

    # ── Attach to app.state (shared across all requests) ──────────────────
    app.state.participant           = participant
    app.state.companion             = companion
    app.state.curriculum            = curriculum
    app.state.assessment            = assessment
    app.state.integrity             = integrity
    app.state.student_message_graph = student_message_graph
    app.state.dashboard_service     = dashboard_service
    app.state.session_store         = session_store

    logger.info("─" * 60)
    logger.info("Orchestrator ready on port 8000")
    logger.info("─" * 60)

    yield  # ── app is running ──────────────────────────────────────────────

    logger.info("Orchestrator shutting down — closing agent clients...")
    for client in [participant, companion, curriculum, assessment, integrity]:
        await client.close()
    logger.info("Shutdown complete.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AIEIC Orchestrator",
    description=(
        "Single entry point for the AIEIC Lab Multi-Agent System. "
        "Routes student and instructor requests to the appropriate backend agents. "
        "See INTERFACE_CONTRACT.md for the full API specification."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # TODO production: restrict to frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(student_router)
app.include_router(instructor_router)


# ── Root / health ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "agent": "orchestrator", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "orchestrator", "version": "0.1.0"}


# ── Dev entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
