# Data Models

All models are defined in `models.py`.

---

## Enums

### `QuestionClassification`
The five categories the LLM classifier can assign to a student question.

| Value | Meaning |
|-------|---------|
| `CONCEPTUAL` | Student seeks to understand a principle, theory, or formula |
| `PROCEDURAL` | Student asks how to approach a problem type in general (not their specific answer) |
| `CLARIFICATION` | Student asks about lab instructions, wording, or logistics |
| `DIRECT_SOLUTION` | Student requests their specific numerical answer, derivation, or finished code — **violation** |
| `ANSWER_FARMING` | Pattern of incremental questions extracting a complete solution step by step — **violation** |

### `ViolationType`
```python
DIRECT_SOLUTION_REQUEST  # classified as DIRECT_SOLUTION
ANSWER_FARMING           # classified as ANSWER_FARMING
FREQ_LIMIT_EXCEEDED      # retained for backward compatibility; not actively triggered
```

### `ViolationSeverity`
```python
MAJOR   # DIRECT_SOLUTION_REQUEST
MINOR   # ANSWER_FARMING
```

### `SessionStatus`
```python
ACTIVE   # session in progress
CLOSED   # session ended (POST /session/end called)
```

### `ReportType`
```python
SESSION   # per-session integrity report
POST_LAB  # cross-session over-reliance analysis
```

### `FinalStatus`
Used in SESSION reports to summarise overall integrity outcome.
```python
CLEAN      # no violations detected
WARNING    # violations detected but below escalation threshold
ESCALATED  # 3+ violations; session flagged for instructor review
```

---

## API Request / Response Models

### `ValidateQuestionRequest`
Sent by Lab Companion on every student message.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `student_id` | `str` | yes | Cal Poly username |
| `session_id` | `str` | yes | UUID from `POST /session/start` |
| `lab_id` | `str` | yes | e.g. `"lab03"` |
| `course_id` | `str` | no | default `"CSC580"` |
| `question_text` | `str` | yes | 1–4000 chars |
| `conversation_history` | `list[dict]` | no | `[{"role": "user"|"assistant", "content": str}]` — required for ANSWER_FARMING detection |

### `ValidateQuestionResponse`
Returned to Lab Companion. Purely observational — does not instruct Lab Companion to block or restrict anything.

| Field | Type | Description |
|-------|------|-------------|
| `classification` | `QuestionClassification` | LLM's category |
| `violation_detected` | `bool` | True if DIRECT_SOLUTION or ANSWER_FARMING |
| `violation_type` | `ViolationType \| null` | Specific type if violation |
| `violation_count` | `int` | Cumulative violations in session |
| `question_count` | `int` | Cumulative questions in session |
| `session_escalated` | `bool` | True after 3rd violation |

### `StartSessionRequest` / `StartSessionResponse`
See [API Reference](02_api_reference.md).

### `PatchReportRequest`
```json
{ "student_id": "alice123", "instructor_notes": { ... any dict ... } }
```

### `PostLabCheckRequest`
```json
{ "student_id": "alice123", "session_ids": ["uuid1", "uuid2"], "lab_id": "lab03", "course_id": "CSC580" }
```

### `LabAnalyticsResponse` / `StudentLabSummary`
See [Analytics](06_analytics.md) for full field descriptions.

---

## Cosmos DB Document Models

These are the documents persisted to Azure Cosmos DB.

### `QuestionRecord`
One record per student message, stored in `SessionDocument.questions[]`.

| Field | Type | Description |
|-------|------|-------------|
| `question_id` | `str` | UUID (auto-generated) |
| `sequence_number` | `int` | Position in session (1-indexed) |
| `timestamp` | `str` | ISO 8601 UTC |
| `text` | `str` | Full question text |
| `classification` | `QuestionClassification` | LLM's category |
| `violation` | `bool` | Whether this question is a violation |
| `violation_type` | `ViolationType \| null` | Type if violation |
| `concept_tags` | `list[str]` | 1–3 technical topic labels from the LLM (e.g. `["BJT biasing"]`) |

### `ViolationRecord`
One record per detected violation, stored in `SessionDocument.violations[]`.

| Field | Type | Description |
|-------|------|-------------|
| `violation_id` | `str` | UUID (auto-generated) |
| `question_id` | `str` | Links to the corresponding `QuestionRecord` |
| `sequence_number` | `int` | Question position in session |
| `timestamp` | `str` | ISO 8601 UTC |
| `violation_type` | `ViolationType` | DIRECT_SOLUTION_REQUEST or ANSWER_FARMING |
| `severity` | `ViolationSeverity` | MAJOR or MINOR |
| `question_text` | `str` | The full question that triggered the violation |

### `SessionDocument`
One document per lab session. Partition key: `student_id`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | — | = `session_id` (Cosmos document ID) |
| `student_id` | `str` | — | Partition key |
| `session_id` | `str` | — | Same as `id` |
| `lab_id` | `str` | — | Lab assignment identifier |
| `course_id` | `str` | — | Course identifier |
| `started_at` | `str` | — | ISO 8601 UTC |
| `ended_at` | `str \| null` | `null` | Set on `POST /session/end` |
| `question_count` | `int` | `0` | Incremented on each `/validate` call |
| `violation_count` | `int` | `0` | Incremented on each detected violation |
| `escalated` | `bool` | `false` | Set to `true` when `violation_count` reaches 3 |
| `status` | `SessionStatus` | `ACTIVE` | Set to `CLOSED` on `POST /session/end` |
| `questions` | `list[QuestionRecord]` | `[]` | Appended on each `/validate` call |
| `violations` | `list[ViolationRecord]` | `[]` | Appended on each detected violation |
| `report_generated` | `bool` | `false` | Set to `true` after report is created |
| `report_id` | `str \| null` | `null` | Set to the generated report's ID |

### Report Document (SESSION type)
Stored in the `reports` container. Full schema:

```json
{
  "id": "<report_uuid>",
  "report_id": "<report_uuid>",
  "student_id": "alice123",
  "session_id": "<session_uuid>",
  "lab_id": "lab03",
  "course_id": "CSC580",
  "generated_at": "2026-01-15T15:30:00Z",
  "report_type": "SESSION",
  "summary": {
    "total_questions": 12,
    "violation_count": 1,
    "escalated": false,
    "final_status": "WARNING",
    "classification_distribution": {
      "CONCEPTUAL": 6, "PROCEDURAL": 4, "CLARIFICATION": 1,
      "DIRECT_SOLUTION": 1, "ANSWER_FARMING": 0
    },
    "concept_struggle_summary": [
      { "concept": "BJT biasing", "count": 1, "violation_types": ["DIRECT_SOLUTION_REQUEST"] }
    ]
  },
  "violations_detail": [ ... list of ViolationRecord dicts ... ],
  "escalation_log": {
    "escalated": false,
    "escalation_timestamp": null,
    "reason": null
  },
  "instructor_notes": "",
  "raw_session_snapshot": { ... full SessionDocument ... }
}
```

### Report Document (POST_LAB type)
```json
{
  "id": "<report_uuid>",
  "report_id": "<report_uuid>",
  "student_id": "alice123",
  "lab_id": "lab03",
  "session_ids": ["uuid1", "uuid2"],
  "generated_at": "2026-01-15T16:00:00Z",
  "report_type": "POST_LAB",
  "summary_text": "3 over-reliance indicators detected. Strong recommendation for instructor review.",
  "stats": {
    "total_questions": 28,
    "total_violations": 5,
    "sessions_analysed": 2
  },
  "over_reliance_indicators": {
    "high_direct_solution_ratio": true,
    "rapid_successive_questions": false,
    "escalated_any_session": true,
    "repeated_violation_types": { "DIRECT_SOLUTION_REQUEST": 4 },
    "concept_struggle_areas": [
      { "concept": "BJT biasing", "count": 3 }
    ]
  },
  "violations_detail": [ ... aggregated ViolationRecord dicts ... ],
  "instructor_notes": ""
}
```
