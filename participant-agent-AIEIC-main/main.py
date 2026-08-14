"""
Participant Agent for AIEIC Lab
Tracks student interactions and provides context for Lab Companion

Author: Yayun
"""

from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Optional
import os
import logging
from dotenv import load_dotenv

from src.participant_agent import ParticipantAgent

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup"""
    logger.info("Participant Agent starting...")
    yield
    logger.info("Participant Agent shutting down...")


app = FastAPI(
    title="AIEIC Participant Agent",
    description="Tracks student interactions for personalized tutoring",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agent
agent = ParticipantAgent()


# ============ Request/Response Models ============

class LogInteractionRequest(BaseModel):
    student_id: str
    session_id: str
    message: str
    response_time_ms: Optional[int] = None
    feedback_score: Optional[Literal["up","down"]] = None  # "up", "down"


class LogInteractionResponse(BaseModel):
    status: str
    interaction_id: str


class StudentContextResponse(BaseModel):
    total_questions: int
    question_type_distribution: dict
    avg_hint_level: float
    sessions_count: int
    avg_questions_per_session: float
    session_help_frequency: dict
    summary: str


# ============ Endpoints ============

@app.get("/")
async def root():
    """Root endpoint"""
    return {"status": "ok", "agent": "participant"}


@app.get("/health")
async def health_check():
    """Health check endpoint for Azure Container Apps"""
    return {"status": "healthy"}


@app.post("/participant/log", response_model=LogInteractionResponse)
async def log_interaction(request: LogInteractionRequest, background_tasks: BackgroundTasks):
    """Classify + build the doc, then kick the Cosmos write to a background task."""
    try:
        logger.info(f"Logging interaction for student: {request.student_id}")
        item = await agent.build_interaction_record(
            student_id=request.student_id,
            session_id=request.session_id,
            message=request.message,
            response_time_ms=request.response_time_ms,
            feedback_score=request.feedback_score,
        )

        # write happens after we respond - don't need to wait on cosmos here
        background_tasks.add_task(agent.save_interaction, item)

        logger.info(f"Interaction queued for write: {item['id']}")
        return LogInteractionResponse(status="ok", interaction_id=item["id"])
    except Exception as e:
        logger.error(f"Error logging interaction for {request.student_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/participant/context/{student_id}", response_model=StudentContextResponse)
async def get_student_context(student_id: str):
    """
    Get student context for personalization
    Called by Lab Companion at session start
    """
    try:
        context = await agent.get_student_context(student_id)
        return StudentContextResponse(**context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ Run Server ============

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
