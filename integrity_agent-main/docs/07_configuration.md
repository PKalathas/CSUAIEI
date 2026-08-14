# Configuration & Deployment

---

## Environment Variables

Set in `.env` for local development, or as Container App secrets in production.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | yes | — | Classifier deployment URL, e.g. `https://myresource.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | yes | — | API key for the classifier deployment |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | yes | — | Deployment name, e.g. `gpt-4o-mini` |
| `AZURE_OPENAI_API_VERSION` | no | `2024-12-01-preview` | Azure OpenAI API version |
| `COSMOS_URL` | prod only | — | Cosmos DB account URL, e.g. `https://myaccount.documents.azure.com:443/` |
| `COSMOS_KEY` | prod only | — | Cosmos DB primary key |
| `COSMOS_DATABASE` | no | `integrity_guardian` | Cosmos database name |
| `INTERNAL_API_TOKEN` | yes | `demo-token` | Shared secret with Lab Companion (`X-Internal-Token` header) |
| `USE_MEMORY_STORE` | no | `false` | Set `true` for local dev/demo — replaces Cosmos with in-memory dicts |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

> **Security:** Never commit `.env`. It is in `.gitignore`. In production, all secrets are Container App secrets — never plain environment variable literals.

---

## Policy Thresholds

These are hardcoded in `policy_engine.py` and `report_generator.py`. They are uniform across all labs and courses.

| Threshold | Value | Where Used |
|-----------|-------|-----------|
| Escalation limit | 3 violations | `app.py` validate handler — sets `session.escalated = True` and emits CRITICAL log |
| Conversation history window | 6 turns (last 3 exchanges) | `policy_engine.py` classify_question — trimmed before sending to LLM |
| Rapid question gap | 30 seconds | `report_generator.py` `_check_rapid_successive` |
| High direct-solution ratio | 20% | `report_generator.py` `generate_post_lab_report` |
| NEEDS_HELP threshold | >50% CONCEPTUAL | `app.py` analytics endpoint per-student status |
| Repeated violation threshold | 3 occurrences | `report_generator.py` `repeated_violation_types` indicator |

---

## Azure OpenAI Configuration

The Guardian uses a **dedicated Azure OpenAI deployment** separate from Lab Companion's deployment. This is intentional — sharing a deployment would cause classification calls to compete for rate limits with tutoring calls, potentially triggering the fail-safe path for legitimate students.

**Recommended model:** `gpt-4o-mini`
- Classification prompt is short (~200 tokens input)
- `temperature=0.0` and `max_completion_tokens=400` keep cost predictable
- Each `/validate` call produces one completion

---

## Azure Cosmos DB Setup

On first startup (when `USE_MEMORY_STORE=false`), the Guardian automatically creates the database and containers if they don't exist:

```python
await db.create_database_if_not_exists(id="integrity_guardian")
await db.create_container_if_not_exists(
    id="sessions", partition_key=PartitionKey(path="/student_id")
)
await db.create_container_if_not_exists(
    id="reports", partition_key=PartitionKey(path="/student_id")
)
```

Only the Cosmos **account** must be provisioned manually. Use the Azure portal or CLI.

**Recommended settings:**
- Consistency level: Session (default)
- Region: Same as Container Apps environment (West US per `config.yaml`)

---

## Azure Container Apps Deployment

The deployment manifest is at `config.yaml`:

```yaml
name: integrity-guardian-app
location: West US
environment: x80-environment
ingress:
  external: false        # internal only — not reachable from internet
  targetPort: 8000
resources:
  cpu: 0.5
  memory: 1Gi
scale:
  minReplicas: 1         # keep warm — avoid cold starts on /validate
  maxReplicas: 5
image: x80registry.azurecr.io/integrity-guardian:v1
secrets:
  - COSMOS_KEY
  - AZURE_OPENAI_API_KEY
  - INTERNAL_API_TOKEN
```

`minReplicas: 1` is required because Lab Companion calls `/validate` synchronously on every student message. A cold start (from 0 replicas) would stall the first question of every session.

### Build and Deploy

```bash
# Build and push image
docker build -t x80registry.azurecr.io/integrity-guardian:v1 .
docker push x80registry.azurecr.io/integrity-guardian:v1

# Deploy Container App
az containerapp create --yaml config.yaml
```

---

## Azure Monitor Alert

Set up an alert on the Container App's Log Analytics workspace to fire when a CRITICAL log line containing `"INTEGRITY ESCALATION"` appears. This is the real-time instructor notification path.

Log query:
```kusto
ContainerAppConsoleLogs
| where Log contains "INTEGRITY ESCALATION"
| where TimeGenerated > ago(5m)
```

Route the alert to the instructor notification channel (email or Teams webhook).

---

## Rate Limiting

`POST /validate` is rate limited to **60 requests per minute per `student_id`** using `slowapi`. The key is `student_id` from the request body (not client IP, since all calls originate from Lab Companion's container).

A normal student session has at most 20–30 questions total. 60/minute is generous enough to never affect legitimate usage while blocking runaway retry loops.

Rate limit exceeded returns `429 Too Many Requests`.
