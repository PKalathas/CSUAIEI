"""
Participant Agent Core Logic
Handles interaction logging, classification, and context retrieval

Storage: Azure Cosmos DB (NoSQL API, Serverless)
  - Database: aieic-lab
  - Container: interactions  (partitionKey: /student_id)
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from azure.cosmos import CosmosClient, PartitionKey
from openai import AzureOpenAI
try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False


class ParticipantAgent:
    """
    Participant Agent for tracking student interactions.
    Uses Cosmos DB NoSQL for flexible querying and cross-agent analytics.
    """

    DATABASE_NAME = "aieic-lab"
    CONTAINER_NAME = "interactions"

    CONTEXT_CACHE_TTL = 300  # 5 minutes
    CONTEXT_CACHE_KEY = "student_context:{student_id}"

    def __init__(self):
        self._container_client = None
        self._openai_client = None
        self._redis_client = None

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

    def _get_redis_client(self):
        """Returns a redis client if REDIS_URL is set, otherwise None."""
        if not _REDIS_AVAILABLE:
            return None
        if self._redis_client is None:
            url = os.getenv("REDIS_URL")
            if not url:
                return None
            self._redis_client = redis.from_url(url, decode_responses=True)
        return self._redis_client

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
        Returns: question_type, hint_level, difficulty, classification_confidence
        """
        client = self._get_openai_client()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")

        prompt = f"""Analyze this student question and classify it.

Question: {message[:500]}

Return a JSON object with:
- question_type: one of "debugging", "concept", "setup", "other"
- hint_level: 1 (simple hint needed), 2 (explain error), 3 (point to docs)
- difficulty: one of "low", "medium", "high"
- classification_confidence: number from 0.0 to 1.0 representing confidence in this classification

Return ONLY valid JSON, no other text."""

        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=125,
            )
            import json
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {"question_type": "other", "hint_level": 1, "difficulty": "medium", "classification_confidence": 0.0}

    async def build_interaction_record(
        self,
        student_id: str,
        session_id: str,
        message: str,
        response_time_ms: Optional[int] = None,
        feedback_score: Optional[str] = None,
    ) -> dict:
        """Builds the interaction doc without writing it — write is handled separately."""
        classification = await self.classify_question(message)
        interaction_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # doc shape hasn't changed, just moved the write out
        item = {
            "id": interaction_id,
            "student_id": student_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "message": message[:500],
            "question_type": classification.get("question_type", "other"),
            "hint_level": classification.get("hint_level", 1),
            "difficulty": classification.get("difficulty", "medium"),
            "classification_confidence": classification.get("classification_confidence", 0.0),
            "response_time_ms": response_time_ms or 0,
            "lab_id": os.getenv("LAB_ID", "default-lab"),
            "feedback_score": feedback_score,
        }

        return item

    def save_interaction(self, item: dict) -> None:
        """Writes the interaction to Cosmos. Sync so BackgroundTasks can run it in a threadpool."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            container = self._get_container_client()
            container.upsert_item(item)
        except Exception as e:
            logger.error(f"background write failed for {item.get('id')}: {e}")

    async def log_interaction(
        self,
        student_id: str,
        session_id: str,
        message: str,
        response_time_ms: Optional[int] = None,
        feedback_score: Optional[str] = None,
    ) -> str:
        """Synchronous classify + write in one shot. Kept for demo_simulation.py and direct callers."""
        item = await self.build_interaction_record(
            student_id=student_id,
            session_id=session_id,
            message=message,
            response_time_ms=response_time_ms,
            feedback_score=feedback_score,
        )
        self.save_interaction(item)
        return item["id"]

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
        Returns aggregated context for a student.
        Checks Redis first (5-min TTL), falls back to Cosmos if not cached.
        """
        import logging
        logger = logging.getLogger(__name__)
        cache_key = self.CONTEXT_CACHE_KEY.format(student_id=student_id)

        # cache hit — skip the cosmos query and llm call
        try:
            r = self._get_redis_client()
            if r:
                cached = r.get(cache_key)
                if cached:
                    return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis read failed, falling back to Cosmos: {e}")

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

        result = {
            "total_questions": total,
            "question_type_distribution": type_counts,
            "avg_hint_level": round(avg_hint, 2),
            "sessions_count": sessions_count,
            "avg_questions_per_session": round(avg_questions_per_session, 1),
            "session_help_frequency": session_counts,
            "summary": summary,
        }

        # caching in case of redis failure
        try:
            r = self._get_redis_client()
            if r:
                r.setex(cache_key, self.CONTEXT_CACHE_TTL, json.dumps(result))
        except Exception as e:
            logger.warning(f"Redis write failed, result not cached: {e}")

        return result
