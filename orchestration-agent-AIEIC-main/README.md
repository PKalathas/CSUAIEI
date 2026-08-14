# AIEIC Orchestrator

Single entry point for the AIEIC Lab Multi-Agent System. Routes all student and instructor requests to the appropriate backend agents.

---

## Architecture

```
Frontend (React / Figma)
        │  HTTPS
        ▼
  ORCHESTRATOR  ← this repo, port 8000
  ┌──────────────────────────────────────────┐
  │  LangGraph (student message flow)        │
  │  asyncio.gather (dashboard aggregation)  │
  │  In-memory session store (v0.1)          │
  └──┬──────┬──────┬──────────────────────┬──┘
     │      │      │                      │
     ▼      ▼      ▼                      ▼
 :8001   :8002  :8003   :8004          :8005
Particip Compan Curricu Assessment   Integrity
  Agent  ion    lum       Agent        Agent
```

The frontend talks **only** to the Orchestrator. Agents do not call each other directly.

The student message flow uses LangGraph because it is sequential with conditional routing:

```
load_context → policy_check → call_companion → log_interaction
```

`policy_check` calls the Integrity Agent (`POST /validate`) on every student message. If `session_escalated=True` (3+ violations), the companion is skipped and a refusal is returned directly. The instructor dashboard uses `asyncio.gather` instead: parallel HTTP calls with no branching.

## Quick Start (all agents mocked)

```bash
# 1. Install
pip install -r requirements.txt

# 2. Start mock agents (ports 8001–8004) and the real Integrity Agent (port 8005)
python -m aieic_shared.mocks.run_all
# In a separate terminal, start the Integrity Agent:
cd ../integrity_agent && uvicorn app:app --port 8005 --reload

# 3. Start orchestrator (in a separate terminal)
cp .env.example .env          # fill in INTEGRITY_TOKEN
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000/docs to explore the API.

## Development with real agents

```bash
# Run mocks only for agents not yet implemented
# e.g. real Participant + real Assessment, mock Companion + mock Curriculum:
python -m aieic_shared.mocks.run_all --no-participant --no-assessment

# Point orchestrator at real agents via .env
PARTICIPANT_URL=http://localhost:8001
ASSESSMENT_URL=http://localhost:8004
```

## Project Structure

```
orchestration-agent-AIEIC/
├── main.py                  # FastAPI app + lifespan (client init, graph build)
├── config.py                # Settings (agent URLs, session TTL)
├── requirements.txt
├── Dockerfile
├── graphs/
│   └── student_message.py   # LangGraph: load_context → policy_check → companion → log
├── routers/
│   ├── student.py           # POST /orchestrator/student/message, /submit
│   └── instructor.py        # GET /orchestrator/instructor/dashboard/{lab_id}, etc.
└── services/
    ├── session.py           # In-memory session store (→ Cosmos DB in v0.2)
    └── dashboard.py         # Parallel agent aggregation for instructor dashboard
```

## API Reference

Full request/response schemas and end-to-end flows: [`INTERFACE_CONTRACT.md`](https://github.com/yuki011121/aieic-shared/blob/main/INTERFACE_CONTRACT.md)

### Student endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/orchestrator/student/message` | Student sends a message → Lab Companion reply |
| POST | `/orchestrator/student/submit` | Student submits final code + report |

### Instructor endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/orchestrator/instructor/dashboard/{lab_id}` | All 4 dashboard tabs |
| POST | `/orchestrator/instructor/material/approve` | Approve AI-generated material |
| POST | `/orchestrator/instructor/material/request-changes` | Request regeneration |
| POST | `/orchestrator/instructor/material/generate-quiz` | Generate quiz |
| POST | `/orchestrator/instructor/material/check-typos` | Check material for errors |
| POST | `/orchestrator/instructor/review/{id}/complete` | Complete manual review |
| GET | `/orchestrator/instructor/grades/csv?lab_id=` | Download grades as CSV |


