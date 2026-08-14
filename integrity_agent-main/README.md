# Integrity Guardian

**AIEIC Agentic Design Framework — Policy & Integrity Agent**

The Integrity Guardian is a standalone FastAPI service that enforces Cal Poly's academic integrity policy inside AI-assisted STEM lab sessions. It sits between the Lab Companion (tutoring agent) and students — every question a student asks is validated here before the tutoring agent is allowed to respond.

It classifies questions using Azure OpenAI, tracks violations per session, escalates repeated offenders to the Instructor Co-pilot, and generates integrity reports at the end of each lab session.

---

## How It Fits Into the System

```
Student
  │  asks question
  ▼
Lab Companion  ──── POST /validate ────▶  Integrity Guardian
                                                │
                                    ┌───────────▼───────────┐
                                    │  Azure OpenAI         │
                                    │  (classifies question)│
                                    └───────────┬───────────┘
                                                │
                                    ┌───────────▼───────────┐
                                    │  Guidance Matrix      │
                                    │  (applies rules)      │
                                    └───────────┬───────────┘
                                                │
                         ◀── FULL / MODERATE / MINIMAL / REJECTED ──
  │
  ▼
Lab Companion answers (or blocks) accordingly
```

The student never interacts with this service directly.

---

## Quick Start (Demo Mode)

No Azure Cosmos DB required — sessions are stored in memory.

**1. Clone and enter the project**
```bash
cd integrity_agent
```

**2. Create and activate a virtual environment**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure `.env`**

Fill in the three required values — copy them from your Azure OpenAI resource:
```
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT_NAME=<your-deployment-name>
```
Everything else is pre-set for demo mode (`USE_MEMORY_STORE=true`, `INTERNAL_API_TOKEN=demo-token`).

**5. Start the server** (Terminal 1)
```bash
uvicorn app:app --reload
```

**6. Run the demo script** (Terminal 2)
```bash
python demo.py
```

The demo sends 5 pre-scripted questions — two appropriate, three policy violations — and prints the live classification results and final integrity report.

---

## Project Structure

```
integrity_agent/
├── app.py                   # FastAPI service — all routes, settings, lifespan
├── models.py                # Pydantic models: enums, API shapes, DB documents
├── policy_engine.py         # LLM classifier + rule-based guidance matrix
├── cosmos_client.py         # Azure Cosmos DB async client (production)
├── cosmos_client_memory.py  # In-memory drop-in replacement (demo / dev)
├── report_generator.py      # Session and post-lab integrity report generation
├── demo.py                  # Scripted end-to-end demo walkthrough
├── requirements.txt
├── Dockerfile
├── config.yaml              # Azure Container App deployment config
└── .env                     # Local secrets — never commit this
```

---

## Classification System

Every question is classified by the LLM into one of five categories:

| Classification | Meaning | Guidance |
|---|---|---|
| `CONCEPTUAL` | Student wants to understand a concept or principle | **FULL** — answer completely |
| `CLARIFICATION` | Student asks about lab instructions or wording | **FULL** — clarify directly |
| `PROCEDURAL` | Student asks how to approach a problem type in general | **MODERATE** — explain method, not their specific answer |
| `ANSWER_FARMING` | Incremental questions that together extract a full solution | **MINIMAL** — only confirm if their stated approach is correct |
| `DIRECT_SOLUTION` | Student asks for the specific answer, code, or derivation | **REJECTED** — blocked entirely |

### Thresholds

| Event | Trigger | Action |
|---|---|---|
| Frequency warning | Question 13/15 | Guidance capped at MODERATE, student warned |
| Frequency hard block | Question 16+ | REJECTED, student directed to office hours |
| Escalation | 3rd violation | Session flagged, `CRITICAL` log emitted, all further questions blocked |

---

## API Reference

All endpoints except `/health` require the header:
```
X-Internal-Token: <INTERNAL_API_TOKEN>
```

### `GET /health`
Liveness probe. No auth required.

**Response**
```json
{ "status": "ok", "timestamp": "2026-04-13T10:00:00Z" }
```

---

### `POST /session/start`
Initialize a session when a student opens the Lab Companion.

**Request**
```json
{
  "student_id": "jsmith",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "lab_id": "lab3",
  "course_id": "CSC580"
}
```

**Response**
```json
{
  "session_id": "550e8400-...",
  "started_at": "2026-04-13T10:00:00Z",
  "message": "Session initialized."
}
```

---

### `POST /validate` ★ Primary endpoint
Validate a student question before the Lab Companion responds. Called on every message.

**Request**
```json
{
  "student_id": "jsmith",
  "session_id": "550e8400-...",
  "lab_id": "lab3",
  "course_id": "CSC580",
  "question_text": "Can you write the complete transfer function for my circuit?",
  "conversation_history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

**Response**
```json
{
  "approved": false,
  "guidance_level": "REJECTED",
  "student_message": "I'm not able to provide direct solutions to lab problems...",
  "violation_detected": true,
  "violation_type": "DIRECT_SOLUTION_REQUEST",
  "violation_count": 1,
  "question_count": 4,
  "session_escalated": false,
  "classification": "DIRECT_SOLUTION"
}
```

The Lab Companion should:
- If `approved == false` → show `student_message` to the student, do not call OpenAI
- If `guidance_level == MODERATE` or `MINIMAL` → inject `student_message` as a constraint into its system prompt before responding
- If `guidance_level == FULL` → proceed normally

---

### `POST /session/end`
Close a session and generate the integrity report.

**Request**
```json
{ "student_id": "jsmith", "session_id": "550e8400-..." }
```

**Response**
```json
{
  "session_id": "550e8400-...",
  "report_id": "a1b2c3d4-...",
  "ended_at": "2026-04-13T11:00:00Z",
  "summary": {
    "total_questions": 14,
    "violation_count": 2,
    "escalated": false,
    "final_status": "WARNING"
  }
}
```

---

### `GET /session/{session_id}?student_id=jsmith`
Retrieve the full session state including all question and violation records.

---

### `POST /report/generate`
Re-generate a report for an existing session (e.g. after a session ends without a clean close).

**Request**
```json
{ "student_id": "jsmith", "session_id": "550e8400-...", "report_type": "SESSION" }
```

---

### `POST /report/post-lab`
Cross-session over-reliance analysis. Called by the Assessment Agent after final submission.

**Request**
```json
{
  "student_id": "jsmith",
  "session_ids": ["550e8400-...", "660e9500-..."],
  "lab_id": "lab3",
  "course_id": "CSC580"
}
```

**Response**
```json
{
  "report_id": "x9y8z7w6-...",
  "over_reliance_indicators": {
    "high_rejection_ratio": false,
    "rapid_successive_questions": true,
    "escalated_any_session": false,
    "repeated_violation_types": {},
    "low_full_guidance_ratio": false
  },
  "summary": "1 over-reliance indicator detected. Recommend instructor review."
}
```

---

### `GET /report/{report_id}?student_id=jsmith`
Retrieve a full report document for the Instructor Co-pilot.

---

## Configuration

### `.env` reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | ✅ | — | Your Azure OpenAI resource URL |
| `AZURE_OPENAI_API_KEY` | ✅ | — | API key |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | ✅ | — | Model deployment name (e.g. `gpt-4o-mini`) |
| `AZURE_OPENAI_API_VERSION` | | `2024-12-01-preview` | API version |
| `USE_MEMORY_STORE` | | `false` | Set `true` for demo/dev — skips Cosmos DB |
| `INTERNAL_API_TOKEN` | ✅ prod | `demo-token` | Shared secret with Lab Companion |
| `COSMOS_URL` | ✅ prod | — | Cosmos DB account URL |
| `COSMOS_KEY` | ✅ prod | — | Cosmos DB primary key |
| `COSMOS_DATABASE` | | `integrity_guardian` | Database name |
| `LOG_LEVEL` | | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Deploying to Azure

**1. Build and push the Docker image**
```bash
docker build -t x80registry.azurecr.io/integrity-guardian:v1 .
az acr login --name x80registry
docker push x80registry.azurecr.io/integrity-guardian:v1
```

**2. Fill in `config.yaml`**

Replace all `<placeholder>` values with real credentials. Key settings already configured:
- `external: false` — internal only, never publicly exposed
- `minReplicas: 1` — stays warm (Lab Companion calls it synchronously on every message)
- Same `x80-environment` as the Lab Companion

**3. Deploy**
```bash
az containerapp create \
  --yaml config.yaml \
  --resource-group x80_assistant_group
```

The service will be reachable internally at `http://integrity-guardian-app` within the Container Apps environment.

---

## Wiring to the Lab Companion (x80_helper)

Three changes are needed in `x80_helper/app.py`. Add `httpx` to x80_helper's `requirements.txt` first.

**On chat start** — create a session:
```python
import httpx, uuid

session_id = str(uuid.uuid4())
async with httpx.AsyncClient() as http:
    await http.post(
        "http://integrity-guardian-app/session/start",
        json={"student_id": user.identifier, "session_id": session_id,
              "lab_id": "lab3", "course_id": "CSC580"},
        headers={"X-Internal-Token": os.getenv("INTERNAL_API_TOKEN")}
    )
cl.user_session.set("session_id", session_id)
```

**On each message** — validate before calling OpenAI:
```python
session_id = cl.user_session.get("session_id")
async with httpx.AsyncClient() as http:
    resp = await http.post(
        "http://integrity-guardian-app/validate",
        json={"student_id": user.identifier, "session_id": session_id,
              "lab_id": "lab3", "course_id": "CSC580",
              "question_text": message.content,
              "conversation_history": conversation_history},
        headers={"X-Internal-Token": os.getenv("INTERNAL_API_TOKEN")}
    )
result = resp.json()

if not result["approved"]:
    await cl.Message(content=result["student_message"]).send()
    return  # do not call OpenAI

# If MODERATE or MINIMAL, prepend constraint into the system prompt
if result["guidance_level"] in ("MODERATE", "MINIMAL"):
    system_prompt = result["student_message"] + "\n\n" + system_prompt
```

**On session end** — close and generate report:
```python
async with httpx.AsyncClient() as http:
    await http.post(
        "http://integrity-guardian-app/session/end",
        json={"student_id": user.identifier,
              "session_id": cl.user_session.get("session_id")},
        headers={"X-Internal-Token": os.getenv("INTERNAL_API_TOKEN")}
    )
```

---

## Remaining Work

### 🔴 Required before production

| Task | Notes |
|---|---|
| Provision Azure Cosmos DB | Create account → `integrity_guardian` DB is auto-created on first run. Set `USE_MEMORY_STORE=false` and fill `COSMOS_URL` / `COSMOS_KEY` in `.env` |
| Provision dedicated Azure OpenAI deployment | Separate from Lab Companion's deployment. Update `AZURE_OPENAI_DEPLOYMENT_NAME` |
| Build and deploy Docker image to Azure Container Registry | See deploy steps above |
| Wire Lab Companion to call the Guardian | See integration section above. Needs `httpx` added to x80_helper's `requirements.txt` |
| Rotate `INTERNAL_API_TOKEN` from `demo-token` to a real secret | Set the matching value in both services |
| Azure Monitor alert on `CRITICAL` log lines | Escalation events must reach the instructor in real time — set up a log alert rule on the Container App |

### 🟡 Core feature completion

| Task | Notes |
|---|---|
| Instructor Co-pilot: consume session reports | Read `GET /report/{id}` — the full report JSON schema is already defined |
| Instructor Co-pilot: consume post-lab reports | Call `POST /report/post-lab` and display over-reliance indicators |
| Add `PATCH /report/{id}` endpoint for instructor notes | `instructor_notes` field is already in the report schema, just needs a write route added to `app.py` |
| Pass real conversation history from Lab Companion into `/validate` | Currently sent as an empty list — ANSWER_FARMING detection depends on this context |
| Assessment Agent: call `POST /report/post-lab` after final submission | Connects to the post-lab pipeline in the activity diagram |

### 🟢 Hardening and ops

| Task | Notes |
|---|---|
| Unit tests for `policy_engine.py` | Cover guidance matrix edge cases: exactly question 13, exactly violation 3, LLM JSON parse failure triggering the fail-safe |
| Integration test: x80_helper → Guardian full flow | Both services running locally; a DIRECT_SOLUTION question in the Chainlit UI should be blocked without ever reaching OpenAI |
| Rate limiting on `/validate` | This is on the hot path for every student question — add `slowapi` or put Azure APIM in front |
| Per-lab configurable thresholds | 15 questions / 3 violations are global constants in `policy_engine.py` — make them configurable per `lab_id` |
| CI/CD pipeline | Build + push Docker image on merge to main |
| Cross-session ANSWER_FARMING detection | Currently only detects patterns within one session; the post-lab report could flag it across multiple sessions |

---

## Architecture Notes

- **Why in-memory for the demo:** Cosmos DB requires a provisioned Azure resource. `cosmos_client_memory.py` implements the exact same interface, so switching to production is a single `.env` change.
- **Why `temperature=0` on the classifier:** Classification must be deterministic — the same question must always produce the same result to maintain auditability.
- **Why `minReplicas: 1`:** The Lab Companion calls `/validate` synchronously on every message. A cold start (10–30 s) would block every first question of every session.
- **Why `external: false`:** The service must never be reachable by students directly — only by internal agents on the same Container Apps environment.
- **Fail-safe on classifier errors:** If Azure OpenAI is unavailable, `/validate` defaults to MODERATE guidance rather than blocking students entirely. This is intentional.

---

## Contributing

This repo is part of the AIEIC Agentic Design Framework for Engineering Lab Education.
Cal Poly — CSU Engineering Lab Agents — Parastou Fard.
