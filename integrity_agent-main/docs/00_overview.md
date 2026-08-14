# Integrity Guardian — Overview

## What It Is

Integrity Guardian is a FastAPI microservice that enforces Cal Poly's academic integrity policy inside an AI-assisted STEM lab tutoring system. It sits between the Lab Companion (the tutoring agent students interact with) and the rest of the AIEIC platform, observing every student question, classifying it with an LLM, logging integrity signals, and producing structured reports and analytics for instructors.

## Role in the AIEIC System

```
Student
  └─► Lab Companion (tutoring agent)
            └─► POST /validate ──► Integrity Guardian ──► Azure Cosmos DB
                                          │
                                          └─► Azure OpenAI (classifier)

Instructor Co-pilot
  └─► GET /report/{id}        ──► Integrity Guardian
  └─► POST /report/post-lab   ──► Integrity Guardian
  └─► GET /analytics/lab/{id} ──► Integrity Guardian
```

The Guardian is **never student-facing**. Students interact only with Lab Companion. The Guardian is a purely internal service — it is deployed with `external: false` on Azure Container Apps and is unreachable from the public internet.

## What It Does

For every student question in a lab session, the Guardian:

1. **Classifies** the question into one of five categories using an Azure OpenAI call (CONCEPTUAL, PROCEDURAL, CLARIFICATION, DIRECT_SOLUTION, ANSWER_FARMING)
2. **Extracts concept tags** — short technical labels identifying what topic the question is about (e.g. "BJT biasing", "KVL mesh analysis")
3. **Logs violations** — DIRECT_SOLUTION and ANSWER_FARMING classifications are flagged as integrity violations and stored in the session record
4. **Tracks escalation** — when a student accumulates 3 violations in a session, the session is marked `escalated` and a `CRITICAL` log fires for Azure Monitor alerting
5. **Persists everything** to Azure Cosmos DB for audit and reporting

At the end of a session, it generates an **integrity report** summarising question patterns, violation types, and struggling concepts. A separate **post-lab report** analyses multiple sessions together for over-reliance patterns. A **lab analytics endpoint** aggregates all students in a lab for instructor dashboard consumption.

## What It Does NOT Do

The Guardian is **observational only** — it does not block, restrict, or alter Lab Companion's responses. Earlier versions of this system returned `approved`/`guidance_level`/`student_message` fields that controlled Lab Companion's behaviour; that enforcement layer has been removed to eliminate latency on the hot path. The tutoring agent now operates freely; the Guardian's role is purely to watch, classify, and report.

## Technology Stack

| Component | Technology |
|-----------|-----------|
| API framework | FastAPI + Uvicorn |
| LLM classifier | Azure OpenAI (gpt-4o-mini, dedicated deployment) |
| Database | Azure Cosmos DB (NoSQL, async) |
| Runtime | Python 3.12, async/await throughout |
| Deployment | Azure Container Apps (internal ingress) |
| Auth | Shared secret header (`X-Internal-Token`) |
| Dev/demo mode | In-memory store (no Azure required) |

## File Map

```
integrity_agent/
├── app.py                    — FastAPI application, all endpoints, lifespan
├── models.py                 — All Pydantic models, enums, Cosmos document schemas
├── policy_engine.py          — LLM classifier (classify_question)
├── cosmos_client.py          — Azure Cosmos DB async client (production)
├── cosmos_client_memory.py   — In-memory drop-in (demo / local dev)
├── report_generator.py       — Session and post-lab report generation
├── demo.py                   — End-to-end walkthrough script
├── requirements.txt          — Python dependencies
├── Dockerfile                — Container image
├── config.yaml               — Azure Container App deployment manifest
└── docs/                     — This documentation folder
```
