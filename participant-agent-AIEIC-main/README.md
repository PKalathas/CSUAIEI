# AIEIC Participant Agent

FastAPI service for tracking student interactions in the AIEIC Lab Multi-Agent System.

## Overview

The Participant Agent tracks individual student behavior across sessions and exposes that history so the Lab Companion can personalize its responses.

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your credentials
```

## Run

```bash
# Development
python main.py

# Or with uvicorn
uvicorn main:app --reload --port 8001
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/participant/log` | Log a student interaction |
| GET | `/participant/context/{student_id}` | Get student context |

## Architecture

```
Lab Companion (tutoring agent)
    │
    ├── POST /participant/log (after each message)
    │
    └── GET /participant/context/{student_id} (at session start)
            │
            ▼
    Participant Agent
            │
            └── Azure Table Storage
```

## Azure Resources

- **Resource Group:** `aieic-participant-dev`
- **Storage Account:** For Table Storage
- **Table:** `StudentInteractions`
