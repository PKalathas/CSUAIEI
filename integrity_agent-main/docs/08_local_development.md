# Local Development

---

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set required env vars (minimum for local dev)
# Edit .env — at minimum you need Azure OpenAI credentials
# Set USE_MEMORY_STORE=true to skip Cosmos DB entirely
```

**Minimum `.env` for local dev (no Cosmos needed):**
```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
USE_MEMORY_STORE=true
```

**Full `.env` for production-like local run:**
```env
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
COSMOS_URL=https://...documents.azure.com:443/
COSMOS_KEY=...
USE_MEMORY_STORE=false
INTERNAL_API_TOKEN=demo-token
LOG_LEVEL=DEBUG
```

Note: `COSMOS_ENDPOINT` is not a valid variable name — the Settings class expects `COSMOS_URL`.

---

## Running the Server

```bash
USE_MEMORY_STORE=true uvicorn app:app --reload
```

Server starts on `http://localhost:8000`. You should see:
```
INFO  Integrity Guardian started.
```

If port 8000 is already in use:
```bash
# Kill the existing process
lsof -ti:8000 | xargs kill -9

# Or use a different port
USE_MEMORY_STORE=true uvicorn app:app --reload --port 8001
```

Interactive API docs: `http://localhost:8000/docs`

---

## Running the Demo

The demo script simulates a complete session: two legitimate questions, then three direct-solution requests that trigger escalation.

Requires the server to be running in a separate terminal first.

```bash
# Terminal 1 — keep running
USE_MEMORY_STORE=true uvicorn app:app --reload

# Terminal 2
python demo.py
```

Expected output: health check → session start → 5 questions with classifications and violation signals → session end with `final_status: ESCALATED` report.

---

## Running Tests

```bash
# All tests
pytest -v

# With coverage report
pytest -v --cov=. --cov-report=term-missing

# Single file
pytest tests/test_policy_engine.py -v
pytest tests/test_integration.py -v
pytest tests/test_classifier.py -v
pytest tests/test_endpoints.py -v
pytest tests/test_patch_report.py -v
pytest tests/test_post_lab_report.py -v
pytest tests/test_cosmos_contract.py -v
```

Tests require no Azure credentials — they use `USE_MEMORY_STORE=true` and mock the OpenAI client.

---

## Test File Guide

| File | What it covers |
|------|---------------|
| `test_policy_engine.py` | `classify_question()` shape, `concept_tags` extraction, all 5 classifications |
| `test_classifier.py` | LLM classifier with mocked OpenAI; malformed JSON; rate limit propagation |
| `test_integration.py` | Full end-to-end flow: start session → validate questions → escalation → end session → report |
| `test_endpoints.py` | HTTP status codes, auth rejection (403), session lifecycle, post-lab report endpoint |
| `test_patch_report.py` | `PATCH /report/{id}` — instructor notes saved and retrievable |
| `test_post_lab_report.py` | All 5 over-reliance indicators; boundary conditions; multi-session aggregation |
| `test_cosmos_contract.py` | Verifies `MemoryIntegrityClient` and `CosmosIntegrityClient` expose identical public methods |
| `test_guardian_client.py` | Tests for the Lab Companion–side HTTP client (Track A deliverable — not yet built; excluded from collection) |

---

## In-Memory Mode vs Cosmos Mode

| | `USE_MEMORY_STORE=true` | `USE_MEMORY_STORE=false` |
|---|---|---|
| Storage backend | Plain Python dicts in `MemoryIntegrityClient` | Azure Cosmos DB via `CosmosIntegrityClient` |
| Data persistence | Lost on server restart | Persisted to Azure |
| Azure credentials needed | No | Yes (`COSMOS_URL`, `COSMOS_KEY`) |
| Use case | Local dev, demos, all automated tests | Staging and production |

The two clients expose **identical public interfaces**. `test_cosmos_contract.py` enforces this: if a method is added to one client but not the other, the test fails.

---

## Calling the API Manually

```bash
# Health check
curl http://localhost:8000/health

# Start a session
curl -X POST http://localhost:8000/session/start \
  -H "X-Internal-Token: demo-token" \
  -H "Content-Type: application/json" \
  -d '{"student_id": "alice123", "session_id": "test-session-1", "lab_id": "lab03"}'

# Validate a question
curl -X POST http://localhost:8000/validate \
  -H "X-Internal-Token: demo-token" \
  -H "Content-Type: application/json" \
  -d '{
    "student_id": "alice123",
    "session_id": "test-session-1",
    "lab_id": "lab03",
    "question_text": "What is the DC bias voltage given R1=10k, R2=22k, VDD=5V?",
    "conversation_history": []
  }'

# End session
curl -X POST http://localhost:8000/session/end \
  -H "X-Internal-Token: demo-token" \
  -H "Content-Type: application/json" \
  -d '{"student_id": "alice123", "session_id": "test-session-1"}'

# Lab analytics (no sessions exist yet in memory mode, returns zeros)
curl "http://localhost:8000/analytics/lab/lab03?course_id=CSC580" \
  -H "X-Internal-Token: demo-token"
```

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `ValidationError: cosmos_endpoint Extra inputs not permitted` | `.env` has `COSMOS_ENDPOINT` instead of `COSMOS_URL` | Rename the variable in `.env` |
| `Address already in use` | Port 8000 taken by a previous server instance | Run `lsof -ti:8000 \| xargs kill -9` |
| `httpx.ConnectError` in demo.py | Server not running | Start the server in Terminal 1 first |
| `ModuleNotFoundError: guardian_client` | `test_guardian_client.py` requires a module not yet built | Expected — it's excluded in `pytest.ini` via `collect_ignore` |
| `429` from `/validate` | Rate limit hit (60/min per student_id) | Normal in load tests; reduce request rate |
