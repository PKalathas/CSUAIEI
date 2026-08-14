# Architecture

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        AZURE CONTAINER APPS ENVIRONMENT         │
│                                                                  │
│  ┌──────────────────────┐         ┌───────────────────────────┐ │
│  │    LAB COMPANION     │         │    INTEGRITY GUARDIAN     │ │
│  │  (tutoring agent)    │──POST──►│                           │ │
│  │                      │ /valid- │  ┌─────────────────────┐  │ │
│  │  • Chat interface    │  ate    │  │   policy_engine.py  │  │ │
│  │  • OpenAI calls      │         │  │   classify_question │  │ │
│  │  • Lab material      │◄────────│  └────────┬────────────┘  │ │
│  └──────────────────────┘ classif │           │ Azure OpenAI  │ │
│                            ication│           ▼ (classifier)  │ │
│  ┌──────────────────────┐  +      │  ┌─────────────────────┐  │ │
│  │  INSTRUCTOR CO-PILOT │ violation│  │   cosmos_client.py  │  │ │
│  │                      │ signals │  │   sessions +reports │  │ │
│  │  • View reports      │         │  └────────┬────────────┘  │ │
│  │  • Annotate notes    │──GET────►           │               │ │
│  │  • Lab analytics     │ reports │  ┌────────▼────────────┐  │ │
│  └──────────────────────┘         │  │  report_generator   │  │ │
│                                   │  └─────────────────────┘  │ │
│                                   └───────────────────────────┘ │
│                                              │                   │
│                                    ┌─────────▼──────────┐       │
│                                    │  AZURE COSMOS DB   │       │
│                                    │  sessions container│       │
│                                    │  reports container │       │
│                                    └────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## Request Flow — Every Student Message

```
Student types a question in Lab Companion
         │
         ▼
Lab Companion calls POST /validate
         │
         ▼
  [1] Load session from Cosmos (get_session)
         │
         ▼
  [2] Increment question_count on session
         │
         ▼
  [3] Call classify_question() → Azure OpenAI
      • Sends: question text, last 6 conversation turns, session context
      • Returns: classification, confidence, reasoning, concept_tags
      • Fail-safe: if OpenAI unavailable → PROCEDURAL + empty concept_tags
         │
         ▼
  [4] Determine if violation
      • DIRECT_SOLUTION  → violation MAJOR (DIRECT_SOLUTION_REQUEST)
      • ANSWER_FARMING   → violation MINOR (ANSWER_FARMING)
      • All others       → no violation
         │
         ▼
  [5] If violation: append ViolationRecord, increment violation_count
      If violation_count hits 3 for first time:
        → set session.escalated = True
        → emit CRITICAL log (Azure Monitor alert trigger)
         │
         ▼
  [6] Append QuestionRecord (classification + concept_tags + violation flag)
         │
         ▼
  [7] Persist session to Cosmos (upsert_session)
         │
         ▼
  [8] Return ValidateQuestionResponse to Lab Companion
      (classification, violation_detected, violation_count,
       question_count, session_escalated)
         │
         ▼
Lab Companion answers the student freely (no blocking)
```

## Session Lifecycle

```
Lab opens                    Questions asked               Lab closed / submitted
    │                              │                              │
    ▼                              ▼                              ▼
POST /session/start        POST /validate             POST /session/end
Creates SessionDocument    (one call per message)     Closes session
in Cosmos                  Appends QuestionRecord     Generates SESSION report
                           and ViolationRecord        Persists report to Cosmos
                           to session document        Returns report_id + summary
```

## Storage Layout

Two Cosmos DB containers, both partitioned by `student_id`:

```
Database: integrity_guardian
│
├── Container: sessions   (partition key: /student_id)
│   └── SessionDocument
│       ├── id, student_id, session_id, lab_id, course_id
│       ├── started_at, ended_at, status
│       ├── question_count, violation_count, escalated
│       ├── questions[]   ← QuestionRecord per message
│       └── violations[]  ← ViolationRecord per flagged message
│
└── Container: reports    (partition key: /student_id)
    ├── SESSION report    (one per session, from generate_session_report)
    └── POST_LAB report   (one per analysis, from generate_post_lab_report)
```

### Why nested arrays?
The entire session audit trail reads and writes as a single document. Every `/validate` call needs the session's current state (violation count, question count, escalation status) to update it — a single upsert is simpler and cheaper than joining across containers.

### Why partition by student_id?
- Efficient per-student queries (session list, report lookup)
- Cosmos DB point-reads using `(id, partition_key)` are O(1)
- Cross-student queries (lab analytics) use `enable_cross_partition_query=True`

## Separation of Concerns

| Module | Responsibility |
|--------|---------------|
| `app.py` | HTTP routing, auth, request validation, orchestration |
| `policy_engine.py` | LLM classification only — no storage, no HTTP |
| `cosmos_client.py` | All Cosmos DB I/O — no business logic |
| `cosmos_client_memory.py` | Identical interface, in-memory dict storage |
| `report_generator.py` | Report computation and persistence — no HTTP |
| `models.py` | All data shapes — no logic |

## Security

| Control | Implementation |
|---------|---------------|
| No public exposure | `external: false` in `config.yaml` — unreachable from internet |
| Service-to-service auth | `X-Internal-Token` header on every endpoint except `/health` |
| Secret management | API keys and DB credentials stored as Container App secrets |
| Student data isolation | Cosmos DB partitioned by `student_id` |
| Minimal log PII | Only IDs and counts logged above DEBUG; question text stays in Cosmos |
