"""
Participant Agent Core Logic
Handles interaction logging, classification, and context retrieval

Storage: Azure Cosmos DB (NoSQL API, Serverless)
  - Database: aieic-lab
  - Container: interactions  (partitionKey: /student_id)
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from azure.cosmos import CosmosClient, PartitionKey
from openai import AzureOpenAI


class ParticipantAgent:
    """
    Participant Agent for tracking student interactions.
    Uses Cosmos DB NoSQL for flexible querying and cross-agent analytics.
    """

    DATABASE_NAME = "aieic-lab"
    CONTAINER_NAME = "interactions"

    def __init__(self):
        self._container_client = None
        self._openai_client = None

    def _get_container_client(self):
        """Lazy initialization of Cosmos DB container client."""
        if self._container_client is None:
            endpoint = os.getenv("COSMOS_ENDPOINT")
            key = os.getenv("COSMOS_KEY")
            if not endpoint or not key:
                raise ValueError(
                    "COSMOS_ENDPOINT and COSMOS_KEY must be set. "
                    "Find them in Azure Portal → Cosmos DB account → Keys."
                )

            client = CosmosClient(url=endpoint, credential=key)

            # Create database and container if they don't exist yet
            database = client.create_database_if_not_exists(id=self.DATABASE_NAME)
            self._container_client = database.create_container_if_not_exists(
                id=self.CONTAINER_NAME,
                partition_key=PartitionKey(path="/student_id"),
            )

        return self._container_client

    def _get_openai_client(self):
        """Lazy initialization of Azure OpenAI client."""
        if self._openai_client is None:
            self._openai_client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            )
        return self._openai_client

    async def classify_question(self, message: str) -> dict:
        """
        Classify a student question using LLM.
        Returns: question_type, hint_level, difficulty
        """
        client = self._get_openai_client()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")

        prompt = f"""Analyze this student question and classify it.

Question: {message[:500]}

Return a JSON object with:
- question_type: one of "debugging", "concept", "setup", "other"
- hint_level: 1 (simple hint needed), 2 (explain error), 3 (point to docs)
- difficulty: one of "low", "medium", "high"

Return ONLY valid JSON, no other text."""

        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100,
            )
            import json
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {"question_type": "other", "hint_level": 1, "difficulty": "medium"}

    async def log_interaction(
        self,
        student_id: str,
        session_id: str,
        message: str,
        response_time_ms: Optional[int] = None,
    ) -> str:
        """
        Log a student interaction to Cosmos DB.
        Returns: interaction_id
        """
        classification = await self.classify_question(message)
        interaction_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # Cosmos DB document — id + partitionKey (/student_id) are required
        item = {
            "id": interaction_id,                          # Cosmos DB document id
            "student_id": student_id,                      # partition key
            "session_id": session_id,
            "timestamp": timestamp,
            "message": message[:500],
            "question_type": classification.get("question_type", "other"),
            "hint_level": classification.get("hint_level", 1),
            "difficulty": classification.get("difficulty", "medium"),
            "response_time_ms": response_time_ms or 0,
            # lab_id enables cross-lab analytics by Reflection Agent (future)
            "lab_id": os.getenv("LAB_ID", "default-lab"),
        }

        container = self._get_container_client()
        container.upsert_item(item)

        return interaction_id

    async def _generate_summary(
        self,
        total: int,
        type_counts: dict,
        avg_hint: float,
        sessions_count: int,
        avg_questions_per_session: float,
        primary_type: str,
    ) -> str:
        """Generate an LLM-powered narrative summary for Lab Companion to use as context."""
        client = self._get_openai_client()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")

        prompt = f"""You are a learning analytics assistant. Generate a concise 2-3 sentence summary of a student's learning behavior for a tutoring AI to use as context.

Student stats:
- Total questions: {total} across {sessions_count} session(s)
- Questions per session (avg): {avg_questions_per_session:.1f}
- Question type breakdown: {type_counts}
- Primary question type: {primary_type}
- Average hint level needed: {avg_hint:.1f} (1=minimal hint, 2=explain error, 3=point to full docs)

Write a helpful, actionable summary that tells the tutor how to best support this student. Be specific. No bullet points."""

        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            # Fallback to rule-based if LLM fails
            summary = f"Student has asked {total} questions across {sessions_count} session(s). "
            summary += f"Primary focus: {primary_type} questions. "
            if avg_hint > 2:
                summary += "Often needs detailed explanations."
            elif avg_hint > 1.5:
                summary += "Moderate assistance level."
            else:
                summary += "Often understands with minimal hints."
            return summary

    async def get_student_context(self, student_id: str) -> dict:
        """
        Retrieve aggregated context for a student.
        Used by Lab Companion to personalize its system prompt.

        Uses partition_key routing so only the student's partition is scanned —
        efficient regardless of total data volume.
        """
        container = self._get_container_client()

        # Parameterized query — no string interpolation, safe against injection
        items = list(
            container.query_items(
                query="SELECT * FROM c WHERE c.student_id = @student_id",
                parameters=[{"name": "@student_id", "value": student_id}],
                partition_key=student_id,   # routes to single partition
            )
        )

        if not items:
            return {
                "total_questions": 0,
                "question_type_distribution": {},
                "avg_hint_level": 0.0,
                "sessions_count": 0,
                "avg_questions_per_session": 0.0,
                "session_help_frequency": {},
                "summary": "New student - no previous interactions recorded.",
            }

        total = len(items)
        type_counts: dict = {}
        hint_levels: list = []
        session_counts: dict = {}

        for item in items:
            q_type = item.get("question_type", "other")
            type_counts[q_type] = type_counts.get(q_type, 0) + 1
            hint_levels.append(item.get("hint_level", 1))
            sid = item.get("session_id", "unknown")
            session_counts[sid] = session_counts.get(sid, 0) + 1

        avg_hint = sum(hint_levels) / len(hint_levels) if hint_levels else 0.0
        sessions_count = len(session_counts)
        avg_questions_per_session = total / sessions_count if sessions_count else 0.0
        primary_type = max(type_counts, key=type_counts.get) if type_counts else "unknown"

        summary = await self._generate_summary(
            total=total,
            type_counts=type_counts,
            avg_hint=avg_hint,
            sessions_count=sessions_count,
            avg_questions_per_session=avg_questions_per_session,
            primary_type=primary_type,
        )

        return {
            "total_questions": total,
            "question_type_distribution": type_counts,
            "avg_hint_level": round(avg_hint, 2),
            "sessions_count": sessions_count,
            "avg_questions_per_session": round(avg_questions_per_session, 1),
            "session_help_frequency": session_counts,
            "summary": summary,
        }
