"""FastAPI server hosting the multi-tenant ADFEL backend.

Lifespan responsibilities:

1. Load env-driven ``SystemConfig`` (the *base* config — per-course copies
   are derived inside ``HarnessRegistry`` via ``dataclasses.replace``).
2. Open the system DB and run the bootstrap migration (admin + default
   course if empty).
3. Build the lazy ``HarnessRegistry``.
4. Attach everything to ``app.state``.

The single global ``LabHarness`` that the old code attached to
``app.state.harness`` is gone; routes that need a harness ask the
registry for one keyed by ``course_id``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from agentic_system import SystemConfig
from agentic_system.store import SqliteSystemStore
from server import migration
from server.harness_registry import HarnessRegistry
from server.routes.admin import router as admin_router
from server.routes.auth import router as auth_router
from server.routes.instructor import router as instructor_router
from server.routes.student import router as student_router
from server.session_store import SessionRegistry, run_ttl_sweep

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = SystemConfig.from_env()

    system_store = SqliteSystemStore(cfg.system_db_path)
    system_store.init()
    migration.bootstrap(system_store, cfg)

    harnesses = HarnessRegistry(base_config=cfg, data_root=cfg.data_root)
    sessions = SessionRegistry()

    app.state.config = cfg
    app.state.system_store = system_store
    app.state.harnesses = harnesses
    app.state.sessions = sessions

    sweep_task = asyncio.create_task(run_ttl_sweep(sessions))
    if cfg.dev_auth_bypass:
        logger.warning(
            "ADFEL_DEV_AUTH_BYPASS is active — every request will be "
            "authenticated as %s",
            cfg.dev_user_id or cfg.admin_email or "<ephemeral admin>",
        )
    elif cfg.cas_mock:
        logger.warning(
            "CAS_MOCK is active — /auth/cas/validate authenticates a mock "
            "netid without contacting Cal Poly CAS",
        )
    elif cfg.cas_enabled:
        logger.info("CAS SSO enabled (base=%s)", cfg.cas_base_url)
    else:
        logger.warning(
            "No auth configured — set CAS_* (+ SESSION_JWT_SECRET) or a dev "
            "switch; protected routes will 401/500",
        )
    logger.info("ADFEL server ready")
    try:
        yield
    finally:
        sweep_task.cancel()
        try:
            await sweep_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="ADFEL Server", lifespan=lifespan)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(student_router, prefix="/api/v1")
app.include_router(instructor_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
