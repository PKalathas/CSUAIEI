# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

ADFEL is a hint-style tutoring assistant for Cal Poly's CSC 580 lab course.
Three agents collaborate per turn — a **Lab Companion** generates the
response, a **Guardian** classifies the question and verifies the draft for
academic-integrity violations, and a **Participant** logs the interaction
and tracks the student's learning context.

The system runs as two processes:

- **Server** (`server/`) — a FastAPI app that hosts `LabHarness` and all
  agent logic. Owns session state, LLM clients, and persistent stores
  (SQLite — persists to `./data/` locally; in Azure it lives on the
  server container's **ephemeral storage**, because SMB locking on Azure
  Files is incompatible with SQLite — see the `journal_mode` dance in
  `agentic_system/store/sqlite.py`). Also serves the instructor
  file-upload and indexer-status endpoints.
- **Client** (`app.py`) — a thin Chainlit shell that forwards every turn
  to the server over HTTP and renders streamed step-progress events via
  SSE. Holds only a `session_id` per user; imports nothing from
  `agentic_system/`.

`agentic_system/` is the core package — deliberately decoupled from both
the UI and the server framework.

## Common commands

The project uses [pixi](https://pixi.sh/) for environment management; pixi
sets `PARTICIPANT_DB_PATH` / `GUARDIAN_DB_PATH` to absolute paths under
`./data/` automatically. Required env (in `.env`, loaded by `python-dotenv`):
`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_DEPLOYMENT_NAME`. `AZURE_SEARCH_*` is optional — leave the
three vars blank to disable RAG. The client needs
`ADFEL_SERVER_URL` (defaults to `http://localhost:8080`).

```bash
pixi install

# Local dev — run server and client in separate terminals:
pixi run dev-server     # uvicorn server.main:app --reload --port 8080
pixi run dev-client     # chainlit run app.py -w (http://localhost:8000)

# Production:
pixi run start-server   # uvicorn ... --host 0.0.0.0 --port 8080
pixi run start-client   # chainlit run app.py -h --host 0.0.0.0 --port 8000

pixi run reset-db       # nuke local SQLite stores under data/

docker compose up --build   # containerized: server + client; ./data mounted
```

The server image builds from `Dockerfile.server` + `requirements-server.txt`;
the client image builds from `Dockerfile` + `requirements-client.txt`. Keep
both `requirements-*.txt` files in sync with `pixi.toml`'s
`[pypi-dependencies]` when adding deps — pixi is the source of truth for
local dev, but the containers don't use it.

`reset-db` is essential when iterating on policy/escalation behavior — the
3-violation escalation is *persisted* per session and `STUDENT_ID` defaults
to a single shared identity in the prototype.

There is no test suite in this repo.

## Architecture rules of the road

The repo went through a "decouple the agentic system" refactor (commits
`34b680a`, `1503ca8`) and a follow-up LLM decouple (`4ea1acf`). The shape
that came out of those refactors is the contract; please preserve it.

1. **Chainlit is imported in exactly one file: `app.py`.** Nothing under
   `agentic_system/` should `import chainlit`. If you find yourself wanting
   to, push the abstraction back into the harness's public types instead
   (e.g., the `on_step` callback on `handle_turn`).

2. **`LabHarness` (in `agentic_system/api.py`) is the only public entry
   point.** `agentic_system/__init__.py` re-exports a few result types
   (`SessionState`, `TurnResult`, `GuidanceLevel`, etc.) for the embedder's
   convenience. Don't grow that surface casually — extension is supposed
   to happen via injected backends, not new top-level functions.

3. **Backends are `typing.Protocol`s, not subclasses.** `ParticipantStore`,
   `GuardianStore`, `KnowledgeBase`, and `LLMClient` are all duck-typed.
   The default implementations (`SqliteParticipantStore`,
   `SqliteGuardianStore`, `AzureSearchKB`, `NullKB`, `AzureOpenAILLM`)
   live next to the protocol definition. New backends
   should be new files implementing the same Protocol — don't widen the
   protocol to fit a backend.

   **Vendor SDKs are contained per-file.** Only
   `agentic_system/llm/azure_openai.py` may import the `openai` SDK; only
   `agentic_system/llm/claude.py` may import the `anthropic` SDK; only
   `agentic_system/kb/azure_search.py` may import
   `azure.search.documents`. Every other module talks to the LLM through
   `LLMClient.complete()` and to retrieval through `KnowledgeBase.search()`.
   Heavy SDKs should be lazy-imported inside the methods that need them.

4. **`SystemConfig` is the *only* place env vars are read inside the
   package.** Constructed once via `SystemConfig.from_env()` (or built
   directly by an embedder that has its own settings system) and threaded
   through agents via constructor injection. Agents and policy code must
   never call `os.getenv` themselves.

5. **The policy engine is a pure module.** `agentic_system/policy/engine.py`
   contains the classification system prompt, the verification system
   prompt, and `derive_guidance_level` (a pure function from classification
   + counters → guidance). Auditability is the point — the rules are in
   one place. Don't fragment policy across agents.

6. **All three agents follow constructor injection.** Each takes
   `(store=, llm=, config=)` (or just `llm=, config=` for Lab Companion,
   which has no store). `llm` is an `LLMClient`, not a raw SDK object.
   No globals, no module-level clients, no lazy singletons inside the
   package.

7. **Fail-safe over fail-loud, by design.** Every external call in the
   orchestrator is wrapped:
   - Classifier error → fall back to `PROCEDURAL` / `MODERATE`.
   - Verifier error → pass the draft through (fail-open).
   - KB error → empty context, proceed.
   - Companion error → return a polite "please rephrase" message.
   - Participant log error → swallow + log a warning.

   When adding new external integrations, match this pattern: log, fall
   back, keep the user-facing turn alive.

## Per-turn flow

`Orchestrator.handle_turn` in `agentic_system/orchestrator.py`:

1. **`KB.search(question)`** → `rag_docs` + `rag_context`. **RAG runs
   first** so the classifier can see what lab material the question
   semantically targets (KB match rule #5 in
   `policy/engine.py:CLASSIFICATION_SYSTEM_PROMPT`).
2. **`Guardian.validate(question, history, rag_docs)`** → `ValidateResult`.
   - Hard short-circuit on `REJECTED` or session-escalated.
3. **`LabCompanion.respond(...)`** → draft (constrained by guidance level).
4. **`Guardian.verify(question, draft, guidance_level)`** → pass/fail +
   feedback.
   - On fail: re-call `respond()` with feedback as `verifier_feedback`,
     up to `VERIFIER_MAX_RETRIES` (default 2).
   - On final retry failing: emit `SAFE_FALLBACK` from
     `agents/lab_companion.py`.
5. **`Participant.log_interaction`** (best-effort).
6. Append `(user, assistant)` pair to `state.conversation_history`.

`SessionState` is the opaque object the server holds across turns. It
carries the session id, the prefetched `StudentContext`, and the running
conversation history. The server's in-memory `SessionRegistry` stores
these keyed by `session_id` with a 1-hour idle TTL; a 5-minute
background sweep (`run_ttl_sweep`, started in the FastAPI lifespan)
evicts stale entries. The Chainlit client never sees the full object.

`handle_turn` accepts an optional `on_step: Callable[[name, type, output], None]`
for streaming progress events to the UI (used by the server to emit SSE
`step` events that the Chainlit client renders as live Steps). The callback
fires from the worker thread; `server/routes/student.py` marshals events
via an `asyncio.Queue` into the SSE stream.

## Code map

```
app.py                              Chainlit client shell. Thin HTTP/SSE
                                    proxy to the server. Holds a session_id
                                    + the CAS session token per user. No
                                    agentic_system imports. Drives the CAS
                                    browser flow: mounts /login/cas[/callback]
                                    on chainlit.server.app, validates the
                                    ticket via the server, sets an HttpOnly
                                    cookie, and reads it back in
                                    header_auth_callback; attaches the JWT as
                                    a per-request Bearer. Reads ADFEL_SERVER_URL,
                                    CAS_BASE_URL, CAS_SERVICE_URL, CAS_MOCK,
                                    ADFEL_COOKIE_SECURE, CHAINLIT_AUTH_SECRET
                                    directly. The "no env reads outside
                                    config.py" rule applies inside the
                                    agentic_system/ package; app.py is
                                    the embedder boundary.

server/
  main.py                           FastAPI app. Lifespan opens the system
                                    DB, runs migration.bootstrap, builds
                                    HarnessRegistry + SessionRegistry, and
                                    attaches config + system_store +
                                    harnesses + sessions to app.state.
                                    No single global LabHarness anymore.
  schemas.py                        Pydantic request/response models for
                                    the HTTP API (turn IO + admin/course
                                    CRUD).
  session_store.py                  In-memory SessionRegistry with TTL
                                    sweep for stale sessions.
  harness_registry.py               Lazy course_id → LabHarness cache.
                                    Builds each entry with per-course
                                    paths/index/container via
                                    dataclasses.replace(base_config, ...).
  auth.py                           Session-JWT verification (require_user
                                    builds AuthedUser from the token claims,
                                    no per-request DB load) and role/enrollment
                                    FastAPI dependencies (require_admin,
                                    require_instructor, require_course_member,
                                    require_course_instructor). Also owns the
                                    Cal Poly CAS back-channel (validate_cas_ticket,
                                    with a cas_mock short-circuit), the
                                    provider-neutral resolve_or_create_user
                                    (anchor: sso_subject), and mint/verify of
                                    the session JWT. Lazy-imports jwt + httpx.
                                    Honors ADFEL_DEV_AUTH_BYPASS.
  routes/auth.py                    POST /api/v1/auth/cas/validate — the only
                                    auth-free route. Validates a CAS ticket,
                                    resolves/creates the user, returns a
                                    session JWT for the client to carry.
  provisioning.py                   Per-course blob container create/delete
                                    and local data/courses/{id}/ cleanup.
                                    Lazy-imports azure.storage.blob.
  migration.py                      Idempotent startup bootstrap: seed
                                    admin user and a "default" course
                                    pointed at legacy SQLite paths so the
                                    un-prefixed routes keep working.
  indexing.py                       Blob upload + Azure AI Search indexer
                                    trigger/status. The only file in
                                    server/ besides provisioning.py that
                                    imports azure.storage.blob.
  routes/
    student.py                      POST   /api/v1/courses/{cid}/sessions,
                                    POST   /api/v1/courses/{cid}/sessions/{sid}/turn,
                                    DELETE /api/v1/courses/{cid}/sessions/{sid}.
                                    Legacy un-prefixed routes preserved,
                                    resolving to the default course.
                                    Session ownership enforced by
                                    comparing state.student_id to the
                                    authed user.id.
    instructor.py                   POST /api/v1/courses/{cid}/instructor/upload
                                    GET  /api/v1/courses/{cid}/instructor/indexer/status
                                    plus legacy un-prefixed mirrors.
                                    Uses the per-course harness's config
                                    so each upload lands in that course's
                                    blob container.
    admin.py                        /api/v1/admin/users (admin),
                                    /api/v1/admin/courses (instructor),
                                    /api/v1/admin/courses/{cid}/enroll +
                                    enrollments (course instructor).
                                    Course creation auto-provisions the
                                    blob container; search resources must
                                    be pre-provisioned externally.

agentic_system/
  api.py                            LabHarness.build() — wires defaults
                                    from SystemConfig, allows injection
                                    of stores, KB, and llm (LLMClient).
                                    handle_turn(state, q, on_step=) is
                                    the main entry point.
  config.py                         SystemConfig dataclass. .from_env()
                                    is the only env-aware constructor.
                                    Carries Azure OpenAI, Azure Search,
                                    and Azure Blob/indexer fields plus
                                    tutoring knobs. Use the derived
                                    properties (.llm_configured,
                                    .search_enabled, .indexing_enabled)
                                    for feature gates instead of
                                    re-deriving the underlying env
                                    conditions.
  orchestrator.py                   The pipeline. RAG → validate → draft
                                    → verify → log. Read this first when
                                    debugging behavior.
  models.py                         Enums (QuestionClassification,
                                    GuidanceLevel, ViolationType/Severity),
                                    Pydantic records (QuestionRecord,
                                    ViolationRecord, VerificationRecord),
                                    result dataclasses (ValidateResult,
                                    VerifyResult, TurnResult, SessionState,
                                    StudentContext).

  agents/
    lab_companion.py                Builds the system prompt with the
                                    GUIDANCE_INSTRUCTIONS table, RAG
                                    context, and (on retry) verifier
                                    feedback. SAFE_FALLBACK lives here.
    guardian.py                     validate() + verify(). Validate
                                    accepts rag_docs and forwards them
                                    into the classifier so KB match rule
                                    #5 fires. Owns session lifecycle on
                                    the guardian DB; triggers escalation
                                    at violation #3.
    participant.py                  classify_question() (per-message LLM
                                    tag), log_interaction(),
                                    get_student_context() (LLM-generated
                                    narrative summary with rule-based
                                    fallback).

  policy/
    engine.py                       CLASSIFICATION_SYSTEM_PROMPT,
                                    VERIFICATION_SYSTEM_PROMPT,
                                    classify_question() (takes rag_context
                                    so KB match rule applies),
                                    verify_response(),
                                    derive_guidance_level() (pure mapping).
                                    Takes an LLMClient — no SDK awareness.

  llm/
    base.py                         LLMClient Protocol — one method,
                                    `complete(messages, *, temperature,
                                    max_tokens, json_mode) -> str`.
    azure_openai.py                 AzureOpenAILLM (lazy-imports openai).
    claude.py                       ClaudeLLM (lazy-imports anthropic).
                                    Defaults to claude-opus-4-7, prompt
                                    caching on the system prompt, drops
                                    sampling params for Opus 4.7.
                                    api_key= for keys, auth_token= for
                                    OAuth bearers.

  kb/
    base.py                         KnowledgeBase Protocol, RetrievedDoc,
                                    format_context() helper.
    azure_search.py                 AzureSearchKB (lazy-imports
                                    azure.search.documents). Expects
                                    index fields: parent_id, chunk_id,
                                    chunk, title.
    null.py                         NullKB. Returns []. Used when the
                                    AZURE_SEARCH_* env vars are blank.

  store/
    base.py                         ParticipantStore + GuardianStore +
                                    SystemStore Protocols. Sync API. dict
                                    in / dict out (no Pydantic across the
                                    protocol boundary).
    sqlite.py                       Default per-course impls. One file
                                    each for participant + guardian.
                                    Schemas declared at the top.
    system.py                       SqliteSystemStore — multi-tenant
                                    metadata (users, courses,
                                    enrollments). Used by the server,
                                    NOT injected into LabHarness.
```

## Multi-tenancy

The server is multi-tenant. The agentic_system package is still
single-course at the LabHarness level — multi-tenancy lives one layer up
in `server/harness_registry.py`, which keeps one `LabHarness` per
`course_id` and derives each one from a base `SystemConfig` via
`dataclasses.replace`. Per-course state:

- SQLite stores at `data/courses/{course_id}/{participant,guardian}.db`
  (the legacy default course keeps `data/{participant,guardian}.db` via
  the `participant_db_path` / `guardian_db_path` columns on `courses`).
- Azure Blob container named `course-{uuid_short}` (auto-created at
  course creation).
- Azure AI Search index/indexer/datasource named on the course row;
  these are pre-provisioned externally (Bicep / ARM / portal), NOT
  auto-created.

User identity comes from Cal Poly **CAS** SSO. The Chainlit client drives
the browser redirect; the server validates the service ticket back-channel
(`server/auth.py:validate_cas_ticket`) and mints a session JWT the client
carries as `Authorization: Bearer`. `require_user` verifies that JWT and
builds the `AuthedUser` from its claims. The identity anchor on the `users`
table is the provider-neutral `sso_subject` (the CAS netid), nullable so
instructors can pre-enroll students by email and have the netid late-bind on
first login. The authed `user.id` is threaded into `SessionState.student_id`
at session start and read by the orchestrator on every turn — there's no
process-wide `STUDENT_ID` anymore. Course-scoped routes enforce enrollment
via `require_course_member`. For local dev without a live Cal Poly IdP, set
`CAS_MOCK=1` (server + client) to run the full flow against a fixed netid.

The legacy un-prefixed routes (`/api/v1/sessions`, `/api/v1/instructor/*`)
are preserved and resolve to the "default course" created on first boot
by `server/migration.py`, so the existing Chainlit client keeps working
while the client-side `?course=` wiring is added.

## Policy at a glance

`agentic_system/policy/engine.py` — a pure module so the behavior is
auditable in one place.

**Question classifications** (input gate):
`CONCEPTUAL`, `PROCEDURAL`, `CLARIFICATION` allowed; `DIRECT_SOLUTION`
hard rejected; `ANSWER_FARMING` allowed but throttled.

**Guidance levels** (response shape):
`FULL` (normal), `MODERATE` (nudge toward independence), `MINIMAL` (one
hint, no code), `REJECTED` (politely decline).

**Throttling** (`derive_guidance_level`):
- 3 violations in a session → escalate; all subsequent turns rejected.
- Q12+ or any violation → at least `MODERATE`. Q14+ → `MINIMAL`.
  Q16+ → `REJECTED`.
- Any `DIRECT_SOLUTION` classification → `REJECTED` for that turn.
- Any `ANSWER_FARMING` classification → `MINIMAL` for that turn.

The Lab Companion's tone-by-guidance-level table is in
`agents/lab_companion.py` (`GUIDANCE_INSTRUCTIONS`).

## Conventions

- **No new env reads outside `config.py`.** Add a field to `SystemConfig`
  and wire it through `from_env()` instead.
- **Result types are dataclasses; persistence rows are dicts.** Pydantic
  `*Record` models exist for inserts but are immediately `.model_dump()`-ed
  before crossing the store boundary so the protocol stays JSON-shaped.
- **All store/agent methods are sync.** The server offloads to a thread
  (`asyncio.to_thread` in `server/routes/student.py`) for the async
  FastAPI endpoints.
- **Logging, not print.** `logging.getLogger(__name__)` at the top of
  every module. The embedder configures handlers; the package never does.
- **Lazy-import heavy SDKs.** Follow the pattern in `kb/azure_search.py`
  and `llm/claude.py`.
- **Default values where it makes sense.** `SystemConfig` ships with
  sane defaults so tests / one-off scripts can build a harness without
  juggling 15 env vars; `LabHarness.build()` only refuses to start if
  Azure OpenAI is unconfigured *and* no `llm` was injected.

## Common extension recipes

### Swap the LLM
```python
from agentic_system import LabHarness, ClaudeLLM
_harness = LabHarness.build(llm=ClaudeLLM())  # reads ANTHROPIC_API_KEY
```
For a new provider: implement `LLMClient.complete(...)` in a new file
under `agentic_system/llm/`. When `json_mode=True`, the implementation
must return parseable JSON (callers `json.loads`). Don't reach into a
vendor SDK from agents or policy code.

### Swap a store
1. Implement `ParticipantStore` (or `GuardianStore`) in a new module
   under `agentic_system/store/`.
2. Inject: `LabHarness.build(participant_store=MyRemoteStore(...))`.
3. Don't touch the agents — they only see the protocol.

### Tweak integrity policy
Almost everything lives in `agentic_system/policy/engine.py`:
- `CLASSIFICATION_SYSTEM_PROMPT` — input gate behavior.
- `VERIFICATION_SYSTEM_PROMPT` — output gate behavior.
- `derive_guidance_level` — throttling thresholds (Q12 / Q14 / Q16 and
  the violation-count → escalation rule).

## When in doubt

- `agentic_system/orchestrator.py` is the source of truth for runtime
  behavior.
- `agentic_system/policy/engine.py` is the source of truth for what
  counts as a violation.
- `agentic_system/api.py` is the source of truth for the embedder
  contract.
- `agentic_system/__init__.py` is the source of truth for the public
  surface — if you'd add an export that doesn't already live there,
  consider whether the harness should expose the capability through
  `LabHarness` instead.
