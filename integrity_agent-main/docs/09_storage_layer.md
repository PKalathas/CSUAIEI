# Storage Layer

The storage layer is abstracted behind a shared interface implemented by two classes: `CosmosIntegrityClient` (production) and `MemoryIntegrityClient` (local dev / tests). Switching between them requires only changing `USE_MEMORY_STORE` in the environment.

---

## Interface Contract

Both clients expose the same public methods. `test_cosmos_contract.py` enforces this automatically — if a method is added to one client and not the other, the test suite fails.

| Method | Description |
|--------|-------------|
| `initialize()` | Set up DB/containers (Cosmos) or log startup (memory) |
| `create_session(doc)` | Insert a new session document; raises on duplicate ID |
| `get_session(session_id, student_id)` | Point-read by ID and partition key; returns `None` if not found |
| `upsert_session(doc)` | Insert or replace a session document |
| `get_all_sessions_for_student(student_id, lab_id=None)` | All sessions for a student, optionally filtered by lab |
| `get_all_sessions_for_lab(lab_id, course_id=None)` | All sessions for a lab across all students (cross-partition) |
| `create_report(doc)` | Insert a new report document |
| `get_report(report_id, student_id)` | Point-read report; returns `None` if not found |
| `upsert_report(doc)` | Insert or replace a report document |
| `get_reports_for_session(session_id, student_id)` | All reports linked to a session |
| `close()` | Close the Cosmos client / log shutdown |

---

## `CosmosIntegrityClient` (production)

**File:** `cosmos_client.py`

Uses the Azure Cosmos DB async SDK (`azure-cosmos`). All methods are `async`.

### Initialisation

```python
client = CosmosIntegrityClient(
    url=settings.COSMOS_URL,
    key=settings.COSMOS_KEY,
    database=settings.COSMOS_DATABASE,  # default: "integrity_guardian"
)
await client.initialize()
```

`initialize()` calls `create_database_if_not_exists` and `create_container_if_not_exists` for both containers — safe to call on every startup.

### Sessions Container

- Container name: `sessions`
- Partition key: `/student_id`
- Point-reads (`get_session`) use `(item=session_id, partition_key=student_id)` — O(1)
- Per-student queries use `partition_key=student_id` — single-partition scan
- Per-lab queries use `enable_cross_partition_query=True` — fan-out across all partitions

### Reports Container

- Container name: `reports`
- Partition key: `/student_id`
- Same read patterns as sessions

### Error Handling

`get_session` and `get_report` catch `CosmosResourceNotFoundError` and return `None` rather than raising — callers check for `None` and raise `404` as appropriate.

`create_session` does not catch conflicts — the caller in `app.py` catches the exception, checks for `"409"` or `"Conflict"` in the message, and returns HTTP 409.

---

## `MemoryIntegrityClient` (dev / tests)

**File:** `cosmos_client_memory.py`

Stores everything in plain Python dicts. Zero external dependencies.

```python
# Internal storage
self._sessions: dict[str, dict] = {}   # key: session_id
self._reports: dict[str, dict] = {}    # key: report_id
```

`create_session` raises a plain `Exception("409 Conflict: ...")` on duplicate — the caller's same string-check catches it.

`get_all_sessions_for_student` and `get_all_sessions_for_lab` use list comprehensions over `self._sessions.values()` — no query language.

**Data lifetime:** In-memory only. All data is lost when the process exits. Not suitable for production.

---

## How App.py Selects a Client

In `app.py`'s lifespan handler:

```python
if settings.USE_MEMORY_STORE:
    cosmos = MemoryIntegrityClient()
else:
    cosmos = CosmosIntegrityClient(
        url=settings.COSMOS_URL,
        key=settings.COSMOS_KEY,
        database=settings.COSMOS_DATABASE,
    )
await cosmos.initialize()
app.state.cosmos = cosmos
```

The client is stored on `app.state` and injected into endpoints via `Depends(get_cosmos)`. No endpoint knows which implementation it has — they call the same methods on either.

---

## Cosmos DB Document Design Notes

### Why one document per session?

The entire session (questions, violations, counts, escalation flag) is read and written atomically on every `/validate` call. Splitting it across multiple documents would require:
- Multiple reads to assemble state
- Multiple writes to update it
- Transaction coordination to keep it consistent

A single document upsert is simpler and Cosmos DB handles it as an atomic operation.

### Why partition by `student_id`?

- All per-student operations (get session, get report, check all sessions) are single-partition queries
- The `X-Internal-Token` auth model already scopes requests to a student — data isolation aligns with the partition
- The tradeoff is that per-lab analytics (`get_all_sessions_for_lab`) becomes a cross-partition query, but this is called infrequently (instructor dashboard) vs per-message `/validate` calls

### Document size

Each `QuestionRecord` is roughly 300–500 bytes. A session with 30 questions and 3 violations is approximately 15–20 KB. Cosmos DB's maximum document size is 2 MB — well within range even for unusually long sessions.
