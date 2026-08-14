# ADFEL — CSC 580 Lab Companion

A student-facing agentic tutoring system for Cal Poly's CSC 580 lab course. The
assistant helps students work through assignments by giving **hints, not
answers**, while a separate Guardian agent enforces academic integrity by
classifying every question and verifying every draft response before it reaches
the student.

The system runs as two processes:

- **`server/`** — a [FastAPI](https://fastapi.tiangolo.com/) backend that hosts
  the `LabHarness` and all agent logic. Owns session state, LLM clients, and
  SQLite stores. Future instructor-dashboard endpoints also live here.
- **`app.py`** — a thin [Chainlit](https://chainlit.io) client that forwards
  every turn to the server over HTTP and renders streamed step-progress events
  via SSE. It holds only a `session_id` per user and imports nothing from the
  core package.
- **`agentic_system/`** — a UI-agnostic Python package that owns all the agents,
  policy, storage, retrieval, and LLM integration. It exposes a single facade,
  `LabHarness`, and knows nothing about either the web framework or the server.

## How it works

Every student turn runs through this pipeline (`agentic_system/orchestrator.py`):

```
question
    │
    ▼
KnowledgeBase.search ──► RAG context (Azure AI Search; optional)
    │                    runs first so the classifier can see what lab
    │                    material the question semantically targets
    │
    ▼
Guardian.validate ──► classify (CONCEPTUAL / PROCEDURAL / DIRECT_SOLUTION / …)
    │                 derive guidance level (FULL / MODERATE / MINIMAL / REJECTED)
    │                 escalate session after 3 violations
    │
    ▼
LabCompanion.respond ──► draft (constrained by guidance level)
    │
    ▼
Guardian.verify ──► pass / fail with feedback
    │           (on fail: retry up to VERIFIER_MAX_RETRIES; then safe fallback)
    │
    ▼
Participant.log_interaction (best-effort telemetry)
    │
    ▼
response to student
```

### The three agents

| Agent | Role | Backed by |
|---|---|---|
| **Lab Companion** | The only student-facing agent. Generates hint-style responses constrained by the per-turn guidance level. | `LLMClient` |
| **Guardian** | Two gates: input classification (academic-integrity policy, with KB match awareness) and output verification (does the draft give away the answer?). Tracks violations and escalates the session at the 3rd violation. | `LLMClient` + SQLite (`guardian.db`) |
| **Participant** | Learning-context tracker. Classifies each question's type/hint-level/difficulty and builds a narrative summary of the student's history that the Lab Companion uses as context. | `LLMClient` + SQLite (`participant.db`) |

The model is reached only through the `LLMClient` protocol
(`agentic_system/llm/base.py`). Two implementations ship in-package:

- `AzureOpenAILLM` — default; talks to Azure OpenAI via the `openai` SDK.
- `ClaudeLLM` — talks to Anthropic via the `anthropic` SDK
  (`ANTHROPIC_API_KEY` by default; pass `auth_token=` for an OAuth bearer).

Any object exposing a `complete(messages, *, temperature, max_tokens, json_mode)`
method can be injected at build time. Nothing under `agentic_system/` outside
the `llm/` package imports a vendor SDK.

### Public API

The embedder (`app.py` today; anything else tomorrow) only needs the
`LabHarness` facade:

```python
from agentic_system import LabHarness

harness = LabHarness.build()              # env-driven defaults
state   = harness.start_session()
result  = harness.handle_turn(state, "what does KVL mean?")
print(result.response)
harness.end_session(state)
```

`handle_turn` accepts an optional `on_step` callback that receives
`(name, type, output)` triples for each pipeline stage — used by the
Chainlit shell to render live "Steps" in the UI. Embedders that don't
care about progress events can omit it.

To swap backends (custom KB, remote-API store, a different LLM):

```python
from agentic_system import LabHarness, ClaudeLLM, SystemConfig

# Use Claude via the Anthropic SDK (reads ANTHROPIC_API_KEY by default):
harness = LabHarness.build(llm=ClaudeLLM())

# Or compose multiple swaps:
harness = LabHarness.build(
    config=SystemConfig.from_env(),
    participant_store=MyRemoteStore(...),
    guardian_store=MyRemoteStore(...),
    knowledge_base=MyKB(...),
    llm=MyLLMClient(...),
)
```

`ParticipantStore`, `GuardianStore`, `KnowledgeBase`, and `LLMClient` are
all `typing.Protocol`s — implement the methods, pass the instance in. The
LLM protocol is one method:

```python
class MyLLMClient:
    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str: ...
```

## Repository layout

```
adfel_agentic_system/
├── app.py                       Chainlit client (thin HTTP/SSE proxy to server)
├── server/                      FastAPI backend
│   ├── main.py                  App + lifespan (builds LabHarness)
│   ├── schemas.py               Pydantic request/response models
│   ├── session_store.py         In-memory session registry with TTL
│   └── routes/
│       ├── student.py           Session + turn endpoints (SSE streaming)
│       └── instructor.py        Stub for future dashboard routes
├── agentic_system/              UI-agnostic core package
│   ├── __init__.py              Public re-exports
│   ├── api.py                   LabHarness facade — single public entry point
│   ├── config.py                SystemConfig dataclass + from_env()
│   ├── orchestrator.py          Per-turn pipeline (RAG → validate → draft → verify)
│   ├── models.py                Enums, Pydantic records, result dataclasses
│   ├── agents/
│   │   ├── lab_companion.py     Student-facing hint generator
│   │   ├── guardian.py          Integrity gate (validate + verify)
│   │   └── participant.py       Learning-context tracker
│   ├── policy/
│   │   └── engine.py            Pure: classification prompt, verification prompt,
│   │                            and the (classification, counters) → guidance mapping
│   ├── llm/
│   │   ├── base.py              LLMClient Protocol — single chat-completion method
│   │   ├── azure_openai.py      AzureOpenAILLM (the only file that imports `openai`)
│   │   └── claude.py            ClaudeLLM (the only file that imports `anthropic`)
│   ├── kb/
│   │   ├── base.py              KnowledgeBase Protocol + RetrievedDoc + format_context
│   │   ├── azure_search.py      AzureSearchKB (lazy-imports the Azure SDK)
│   │   └── null.py              NullKB — used when search is unconfigured
│   └── store/
│       ├── base.py              ParticipantStore + GuardianStore Protocols
│       └── sqlite.py            Default SQLite implementations of both
├── data/                        SQLite files live here (gitignored, local dev only)
├── public/                      Chainlit static assets (logo, favicon, theme)
├── pixi.toml                    Local dev environment + tasks
├── requirements-server.txt      Server pip dependencies
├── requirements-client.txt      Client pip dependencies
├── Dockerfile                   Client container build
├── Dockerfile.server            Server container build
└── docker-compose.yml           Two-service container run (server + client)
```

## Local development

The project uses [pixi](https://pixi.sh/) for environment management.

```bash
# 1. copy env template and fill in your Azure OpenAI credentials
cp .env.example .env
$EDITOR .env

# 2. install dependencies
pixi install

# 3. run server and client in separate terminals:
pixi run dev-server     # uvicorn server.main:app --reload --port 8080
pixi run dev-client     # chainlit run app.py -w → http://localhost:8000
```

Other tasks:

```bash
pixi run start-server   # production: uvicorn --host 0.0.0.0 --port 8080
pixi run start-client   # production: chainlit run -h --host 0.0.0.0 --port 8000
pixi run reset-db       # nuke local SQLite stores under data/
```

`pixi.toml` sets `PARTICIPANT_DB_PATH` and `GUARDIAN_DB_PATH` to absolute
paths under `data/` automatically when the env activates. ### Running with Docker

```bash
docker compose up --build
```

`docker-compose.yml` runs two services: `server` (port 8080) and `client`
(port 8000). The server mounts `./data` to `/data` for SQLite persistence
in local dev. Set `CAS_MOCK=1` (plus `SESSION_JWT_SECRET` and
`CHAINLIT_AUTH_SECRET`) in `.env` to run the full CAS login flow locally
without a live Cal Poly IdP.

## Environment variables

All env reads happen in `SystemConfig.from_env()` (`agentic_system/config.py`)
or in `app.py`. The agents themselves never touch `os.environ`.

| Variable | Required? | Notes |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | yes¹ | Used by all three agents. |
| `AZURE_OPENAI_API_KEY` | yes¹ | |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | yes¹ | The chat-model deployment (e.g. `gpt-4o`). |
| `AZURE_OPENAI_API_VERSION` | no | Defaults to `2024-12-01-preview`. |
| `AZURE_SEARCH_ENDPOINT` | no | Leave the three `AZURE_SEARCH_*` blank to disable RAG (the harness falls back to `NullKB`). |
| `AZURE_SEARCH_API_KEY` | no | |
| `AZURE_SEARCH_INDEX_NAME` | no | |
| `STUDENT_ID` | no | Single-user prototype identity. Default `default-student`. |
| `LAB_ID` | no | Default `default-lab`. |
| `COURSE_ID` | no | Default `CSC580`. |
| `ADFEL_SERVER_URL` | no² | Client needs this to reach the server. Default `http://localhost:8080`. |
| `CAS_BASE_URL` | no³ | Cal Poly CAS base (from ITS), e.g. `https://cas.calpoly.edu/cas`. |
| `CAS_SERVICE_URL` | no³ | This app's approved callback, e.g. `https://<host>/login/cas/callback`. Must match ITS registration byte-for-byte. |
| `CAS_EMAIL_DOMAIN` | no | Synthesizes `<netid>@domain` when CAS omits email. Default `calpoly.edu`. |
| `CAS_MOCK` | no³ | `1` runs the login flow against a fixed mock netid (local dev). Set on **both** server and client. |
| `SESSION_JWT_SECRET` | no³ | Server-side secret (32+ bytes) signing the API session token. Required for real or mock CAS. |
| `SESSION_JWT_TTL` | no | Session token lifetime in seconds. Default `28800` (8h). |
| `CHAINLIT_AUTH_SECRET` | no³ | Signs Chainlit's own session. Required once any client auth callback is enabled. |
| `ADFEL_COOKIE_SECURE` | no | `1` marks the client session cookie `Secure` (HTTPS). Leave blank for `http://localhost`. |
| `ADFEL_ADMIN_EMAIL` | no | Bootstrapped as the admin user; binds to a netid on first CAS login. |
| `ADFEL_DEV_AUTH_BYPASS` | no | `1` skips auth entirely (server impersonates the admin). Coarser than `CAS_MOCK`. |
| `PARTICIPANT_DB_PATH` | no | Default `data/participant.db`. |
| `GUARDIAN_DB_PATH` | no | Default `data/guardian.db`. |
| `RAG_TOP_N` | no | How many docs to retrieve. Default `3`. |
| `RAG_MAX_CONTENT_LENGTH` | no | Per-doc truncation in the prompt. Default `1000`. |
| `HISTORY_KEEP_TURNS` | no | Conversation history window passed to the Lab Companion. Default `6`. |
| `VERIFIER_MAX_RETRIES` | no | Retries when Guardian rejects a draft. Default `2`. |
| `LOG_LEVEL` | no | `INFO` by default. Set `DEBUG` to see classifications/retries inline. |

¹ Only required if you don't inject your own `LLMClient` into
`LabHarness.build(llm=...)`. Using `ClaudeLLM` instead requires
`ANTHROPIC_API_KEY` (or an explicit `api_key=` / `auth_token=`).

² Required by the Chainlit client. Set in `docker-compose.yml` automatically
(`http://server:8080`).

³ Auth wiring. Students sign in with Cal Poly CAS: the client redirects the
browser to CAS, the server validates the ticket and mints a session JWT, and
the client carries it as a Bearer token. `CAS_BASE_URL` / `CAS_SERVICE_URL`
live on both processes; `SESSION_JWT_SECRET` is server-side; `CHAINLIT_AUTH_SECRET`
is client-side. For local dev set `CAS_MOCK=1` on both (no live IdP needed).
Real endpoints come from a Cal Poly ITS project request — see the deployment
section.

## Policy at a glance

`agentic_system/policy/engine.py` is intentionally a pure module so the
behavior is auditable in one place.

**Question classifications** (input gate):
- `CONCEPTUAL`, `PROCEDURAL`, `CLARIFICATION` — allowed.
- `DIRECT_SOLUTION` — hard rejection.
- `ANSWER_FARMING` — incremental extraction across turns; allowed but throttled.

The classifier sees the retrieved KB chunks alongside the question, so a
question that semantically targets a specific lab task surfaced by the
KB is classified as `DIRECT_SOLUTION` even when phrased as "how do
I…" or "walk me through…".

**Guidance levels** (what shape the Lab Companion's response takes):
- `FULL` — normal hint-style tutoring.
- `MODERATE` — nudge harder toward independence; shorter answers.
- `MINIMAL` — at most one hint, no elaboration, no code.
- `REJECTED` — politely decline.

**Throttling rules** (`derive_guidance_level`):
- 3 violations in a session → escalate; all subsequent turns rejected.
- Q12+ (or any prior violation) → at least `MODERATE`. Q14+ → `MINIMAL`.
  Q16+ → `REJECTED`.
- Any `DIRECT_SOLUTION` classification → `REJECTED` for that turn.
- Any `ANSWER_FARMING` classification → `MINIMAL` for that turn.

**Failure modes** are all fail-safe: a classifier error defaults to
`PROCEDURAL` / `MODERATE`; a verifier error passes the draft through; a
KB error proceeds with empty context; a companion error returns a polite
"please rephrase" message.

## Azure deployment

The system deploys as two Azure Container Apps in a shared Container Apps
Environment:

| Container | Image | Ingress | Port | Purpose |
|---|---|---|---|---|
| `adfel-server` | `adfel-server:v1` | **Internal** | 8080 | FastAPI backend — agent logic, SQLite stores, LLM clients |
| `adfel-client` | `adfel-client:v1` | **External** | 8000 | Chainlit UI — Cal Poly CAS SSO, proxies to server |

The server is only reachable from within the Container Apps Environment
(internal ingress). The client is the public-facing entry point; students
authenticate with Cal Poly CAS. The client's public URL (its
`/login/cas/callback`) is the `CAS_SERVICE_URL` that must be registered with
Cal Poly ITS via an [ITS project request](https://tech.calpoly.edu/its-project-request-form);
those endpoints don't exist until ITS provisions the integration. Until then,
run with `CAS_MOCK=1`.

### Infrastructure

- **Container Registry** (`x80registry.azurecr.io`) — hosts the two images.
- **Container Apps Environment** (`x80-environment`) — shared networking
  for both apps; the client reaches the server at its internal FQDN.
- **Azure AI Foundry** — hosts the chat-model deployment, and (if RAG is
  on) the embedding-model deployment used to build the Search index.
- **Azure AI Search** — hosts the RAG index. Index field names expected by
  `AzureSearchKB`: `parent_id`, `chunk_id`, `chunk`, `title`.
- **Azure Storage** — Blob storage for documents that feed AI Search.

### SQLite persistence

SQLite databases live on the server container's **ephemeral storage**
(not Azure Files). SQLite's file locking is incompatible with Azure Files
SMB, so databases use a local EmptyDir volume instead. Data persists as
long as the single server replica is alive (`minReplicas: 1`,
`maxReplicas: 1`). A container restart resets both databases — acceptable
for the prototype since session data is transient and the system is
designed to rebuild context from scratch.

For durable persistence in a future production deployment, replace the
SQLite stores with a `ParticipantStore` / `GuardianStore` implementation
backed by Azure PostgreSQL Flexible Server or Cosmos DB.

### Deploying

```bash
# Build and push images (requires az login + az acr login):
az acr build -r x80registry -t adfel-server:v1 -f Dockerfile.server .
az acr build -r x80registry -t adfel-client:v1 -f Dockerfile .

# After updating images, force a new revision on each app:
az containerapp update -n adfel-server -g x80_assistant_group --revision-suffix <tag>
az containerapp update -n adfel-client -g x80_assistant_group --revision-suffix <tag>
```

Env vars and secrets are configured directly on the container apps (not
committed to the repo). To update them:

```bash
az containerapp update -n adfel-server -g x80_assistant_group \
  --set-env-vars KEY=value ...
az containerapp update -n adfel-client -g x80_assistant_group \
  --set-env-vars CAS_BASE_URL=... CAS_SERVICE_URL=... CHAINLIT_AUTH_SECRET=... ...
```

> Note: Azure AI Search truncates documents above its size limit and rejects
> oversized files outright. When uploading textbook material, split it
> manually into per-chapter or per-section files before indexing.
