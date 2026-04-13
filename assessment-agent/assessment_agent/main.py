from fastapi import FastAPI
from assessment_agent.api.routes import router


def create_assessment_app() -> FastAPI:
    """Create the Assessment Agent FastAPI application."""
    app = FastAPI(
        title="AIEIC Assessment Agent",
        description=(
            "Automated assessment agent for CSC 580 lab submissions. "
            "Part of the AIEIC Lab Agentic Design Framework. "
            "Handles code grading, report evaluation, anomaly detection, "
            "and personalized feedback generation."
        ),
        version="0.1.0",
    )
    app.include_router(router)

    @app.get("/health")
    async def health():
        return {"status": "healthy", "agent": "assessment"}

    return app
