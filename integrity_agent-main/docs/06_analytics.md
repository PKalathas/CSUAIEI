# Analytics & Faculty Dashboard

The `GET /analytics/lab/{lab_id}` endpoint aggregates integrity data across all students in a lab. It is the primary data source for the faculty statistics dashboard.

---

## Endpoint

```
GET /analytics/lab/{lab_id}?course_id=<optional>
X-Internal-Token: <token>
```

Returns a `LabAnalyticsResponse`. All computation happens in-memory from the session documents returned by `get_all_sessions_for_lab()`.

---

## Response Fields

### `session_stats`
High-level session counts.
```json
{
  "total_sessions": 35,
  "active_sessions": 0,
  "closed_sessions": 35
}
```
Maps to dashboard "Submissions" card: `closed_sessions / total_sessions`.

---

### `question_stats`
AI assistance statistics across all students.
```json
{
  "total_questions": 195,
  "avg_questions_per_student": 16.3,
  "direct_solution_attempts": 14,
  "answer_farming_attempts": 8,
  "escalated_session_count": 3
}
```

| Field | Dashboard label |
|-------|----------------|
| `total_questions` | Total prompts |
| `avg_questions_per_student` | Avg per student |
| `direct_solution_attempts` | Direct answers attempted |
| `answer_farming_attempts` | Answer farming patterns detected |
| `escalated_session_count` | Escalations to instructor |

---

### `classification_distribution`
Count of each question category across all students. Good for a bar or pie chart.
```json
{
  "CONCEPTUAL": 87,
  "PROCEDURAL": 62,
  "CLARIFICATION": 24,
  "DIRECT_SOLUTION": 14,
  "ANSWER_FARMING": 8
}
```
`PROCEDURAL` questions are hint-equivalent — questions where the student is asking how to approach something rather than asking for the answer.

---

### `avg_session_duration_minutes`
Mean session length in minutes, computed only from closed sessions that have both `started_at` and `ended_at` timestamps. `null` if no closed sessions exist.

---

### `per_student`
One entry per student, usable as rows in a per-student table.

```json
[
  {
    "student_id": "alice_m",
    "question_count": 12,
    "violation_count": 0,
    "status": "ON_TRACK",
    "classification_breakdown": {
      "CONCEPTUAL": 6, "PROCEDURAL": 4, "CLARIFICATION": 2,
      "DIRECT_SOLUTION": 0, "ANSWER_FARMING": 0
    }
  },
  {
    "student_id": "carlos_r",
    "question_count": 31,
    "violation_count": 3,
    "status": "FLAGGED",
    "classification_breakdown": { ... }
  },
  {
    "student_id": "ethan_l",
    "question_count": 22,
    "violation_count": 0,
    "status": "NEEDS_HELP",
    "classification_breakdown": {
      "CONCEPTUAL": 15, "PROCEDURAL": 5, "CLARIFICATION": 2,
      "DIRECT_SOLUTION": 0, "ANSWER_FARMING": 0
    }
  }
]
```

#### Status Logic

| Status | Condition | Meaning |
|--------|-----------|---------|
| `FLAGGED` | `violation_count >= 2` OR any session `escalated == true` | Student attempted to get direct solutions multiple times |
| `NEEDS_HELP` | >50% of questions are `CONCEPTUAL` | Student is genuinely struggling with concepts — not cheating, but needs instructor attention |
| `ON_TRACK` | All other cases | Normal help-seeking behaviour |

#### `classification_breakdown`
Granular per-student question type counts. The frontend can derive:
- **Prompts** column → `question_count`
- **Hints** column → `classification_breakdown.PROCEDURAL` (procedural questions are hint-like)
- **Integrity flags** → `classification_breakdown.DIRECT_SOLUTION + ANSWER_FARMING`

---

### `concept_struggle_summary`
All concepts mentioned across all student questions, sorted by frequency descending.

```json
[
  { "concept": "BJT biasing",      "frequency": 18, "from_violations": true },
  { "concept": "KVL mesh analysis", "frequency": 12, "from_violations": false },
  { "concept": "op-amp gain",       "frequency": 9,  "from_violations": true },
  { "concept": "Thevenin equivalent","frequency": 6, "from_violations": false }
]
```

| Field | Description |
|-------|-------------|
| `concept` | Short technical topic label from the LLM |
| `frequency` | Total times this concept appeared across all questions from all students |
| `from_violations` | `true` if this concept appeared in at least one violation question |

**Reading `from_violations`:**
- `true` → students were trying to get direct solutions on this concept — they are actively avoiding it
- `false` → students were asking about it legitimately — they may just need more instruction on it

Both are useful signals for instructors: the first suggests a difficulty with academic honesty around that topic; the second suggests it may need to be re-taught.

---

## What the Analytics Endpoint Does NOT Provide

- **Grades / scores** — these come from the assessment/grading system; the `student_id` is the join key for merging
- **Submission status** (auto-graded, needs review) — also from the assessment system
- **Class average** — no grade data in the Guardian

The faculty dashboard frontend is expected to merge this endpoint's response with grade data from the assessment system using `student_id` as the key.

---

## Underlying Query

The analytics endpoint calls `cosmos.get_all_sessions_for_lab(lab_id, course_id)`, which performs a **cross-partition query** on the `sessions` container:

```sql
SELECT * FROM c WHERE c.lab_id = @lab_id AND c.course_id = @cid
```

Cross-partition queries in Cosmos DB are more expensive than point-reads. For large classes (100+ students), this query will fan out across partitions. If performance becomes a concern, consider:
- Adding a composite index on `(lab_id, course_id)` in Cosmos DB
- Caching the analytics response (TTL of a few minutes) since it's read-heavy during active labs
