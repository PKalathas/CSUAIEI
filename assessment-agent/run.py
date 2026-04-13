"""
Standalone server entry point for the Assessment Agent.

Usage:
    python run.py
    # or
    uvicorn run:app --host 0.0.0.0 --port 8000 --reload
"""
import uvicorn
from assessment_agent.main import create_assessment_app

app = create_assessment_app()

if __name__ == "__main__":
    uvicorn.run("run:app", host="0.0.0.0", port=8000, reload=True)
