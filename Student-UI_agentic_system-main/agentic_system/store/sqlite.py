"""
Default SQLite implementations of `ParticipantStore` and `GuardianStore`.

One file per agent on disk:
  - participant DB: `interactions` table.
  - guardian DB:    `sessions`, `questions`, `violations`, `verifications`.

Each store owns its own DB path. To swap to a remote-API backend later,
implement the same Protocol in another module and inject it into `LabHarness`.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


# =========================================================================
# Participant
# =========================================================================
PARTICIPANT_SCHEMA = """
CREATE TABLE IF NOT EXISTS interactions (
    id                TEXT PRIMARY KEY,
    student_id        TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    timestamp         TEXT NOT NULL,
    message           TEXT NOT NULL,
    question_type     TEXT NOT NULL,
    hint_level        INTEGER NOT NULL,
    difficulty        TEXT NOT NULL,
    response_time_ms  INTEGER NOT NULL DEFAULT 0,
    lab_id            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interactions_student
    ON interactions(student_id);
CREATE INDEX IF NOT EXISTS idx_interactions_student_session
    ON interactions(student_id, session_id);
"""


class SqliteParticipantStore:
    """Default `ParticipantStore` impl. SQLite at the configured path."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)

    # ----------------------------------------------------------- lifecycle
    def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # journal_mode=OFF avoids stale journal files on Azure Files (SMB)
        conn = sqlite3.connect(self._path, timeout=30, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = OFF")
            for stmt in PARTICIPANT_SCHEMA.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            conn.execute("PRAGMA journal_mode = DELETE")
        finally:
            conn.close()

    def close(self) -> None:  # nothing pooled
        return None

    # ----------------------------------------------------------- helpers
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ----------------------------------------------------------- writes
    def insert_interaction(self, item: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO interactions (
                    id, student_id, session_id, timestamp, message,
                    question_type, hint_level, difficulty,
                    response_time_ms, lab_id
                ) VALUES (
                    :id, :student_id, :session_id, :timestamp, :message,
                    :question_type, :hint_level, :difficulty,
                    :response_time_ms, :lab_id
                )
                """,
                item,
            )
            conn.commit()

    # ----------------------------------------------------------- reads
    def fetch_for_student(self, student_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM interactions WHERE student_id = ? "
                "ORDER BY timestamp ASC",
                (student_id,),
            ).fetchall()
        return [dict(row) for row in rows]


# =========================================================================
# Guardian
# =========================================================================
GUARDIAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id        TEXT PRIMARY KEY,
    student_id        TEXT NOT NULL,
    lab_id            TEXT NOT NULL,
    course_id         TEXT NOT NULL,
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    question_count    INTEGER NOT NULL DEFAULT 0,
    violation_count   INTEGER NOT NULL DEFAULT 0,
    escalated         INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'active',
    report_generated  INTEGER NOT NULL DEFAULT 0,
    report_id         TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_student ON sessions(student_id);
CREATE INDEX IF NOT EXISTS idx_sessions_lab ON sessions(lab_id);

CREATE TABLE IF NOT EXISTS questions (
    question_id       TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL,
    student_id        TEXT NOT NULL,
    sequence_number   INTEGER NOT NULL,
    timestamp         TEXT NOT NULL,
    text              TEXT NOT NULL,
    classification    TEXT NOT NULL,
    violation         INTEGER NOT NULL DEFAULT 0,
    violation_type    TEXT,
    concept_tags      TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);
CREATE INDEX IF NOT EXISTS idx_questions_session ON questions(session_id);

CREATE TABLE IF NOT EXISTS violations (
    violation_id      TEXT PRIMARY KEY,
    question_id       TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    student_id        TEXT NOT NULL,
    sequence_number   INTEGER NOT NULL,
    timestamp         TEXT NOT NULL,
    violation_type    TEXT NOT NULL,
    severity          TEXT NOT NULL,
    question_text     TEXT NOT NULL,
    FOREIGN KEY(question_id) REFERENCES questions(question_id)
);
CREATE INDEX IF NOT EXISTS idx_violations_session ON violations(session_id);

CREATE TABLE IF NOT EXISTS verifications (
    verification_id   TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL,
    student_id        TEXT NOT NULL,
    question_id       TEXT,
    timestamp         TEXT NOT NULL,
    passes            INTEGER NOT NULL,
    reason            TEXT,
    guidance_level    TEXT NOT NULL DEFAULT 'FULL',
    draft_excerpt     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_verifications_session ON verifications(session_id);
"""


class SqliteGuardianStore:
    """Default `GuardianStore` impl. SQLite at the configured path."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)

    # ----------------------------------------------------------- lifecycle
    def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # journal_mode=OFF avoids stale journal files on Azure Files (SMB)
        conn = sqlite3.connect(self._path, timeout=30, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = OFF")
            for stmt in GUARDIAN_SCHEMA.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            conn.execute("PRAGMA journal_mode = DELETE")
        finally:
            conn.close()

    def close(self) -> None:
        return None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ----------------------------------------------------------- sessions
    def create_session(self, doc: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, student_id, lab_id, course_id, started_at, status
                ) VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (
                    doc["session_id"],
                    doc["student_id"],
                    doc["lab_id"],
                    doc.get("course_id", "CSC580"),
                    doc["started_at"],
                ),
            )
            conn.commit()

    def get_session(self, session_id: str, student_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ? AND student_id = ?",
                (session_id, student_id),
            ).fetchone()
            if row is None:
                return None
            session = dict(row)
            session["escalated"] = bool(session["escalated"])
            session["report_generated"] = bool(session["report_generated"])
            session["questions"] = self._fetch_questions(conn, session_id)
            session["violations"] = self._fetch_violations(conn, session_id)
            return session

    @staticmethod
    def _fetch_questions(conn: sqlite3.Connection, session_id: str) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM questions WHERE session_id = ? "
            "ORDER BY sequence_number ASC",
            (session_id,),
        ).fetchall()
        out: list[dict] = []
        for row in rows:
            d = dict(row)
            d["violation"] = bool(d["violation"])
            d["concept_tags"] = json.loads(d["concept_tags"] or "[]")
            out.append(d)
        return out

    @staticmethod
    def _fetch_violations(conn: sqlite3.Connection, session_id: str) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM violations WHERE session_id = ? "
            "ORDER BY sequence_number ASC",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_session_counters(
        self,
        session_id: str,
        student_id: str,
        *,
        question_count: int,
        violation_count: int,
        escalated: bool,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                   SET question_count = ?,
                       violation_count = ?,
                       escalated = ?
                 WHERE session_id = ? AND student_id = ?
                """,
                (
                    question_count,
                    violation_count,
                    1 if escalated else 0,
                    session_id,
                    student_id,
                ),
            )
            conn.commit()

    def close_session(
        self,
        session_id: str,
        student_id: str,
        ended_at: str,
        report_id: Optional[str],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                   SET status = 'closed',
                       ended_at = ?,
                       report_generated = ?,
                       report_id = ?
                 WHERE session_id = ? AND student_id = ?
                """,
                (
                    ended_at,
                    1 if report_id else 0,
                    report_id,
                    session_id,
                    student_id,
                ),
            )
            conn.commit()

    # ----------------------------------------------------------- inserts
    def insert_question(self, session_id: str, student_id: str, record: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO questions (
                    question_id, session_id, student_id, sequence_number,
                    timestamp, text, classification, violation, violation_type,
                    concept_tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["question_id"],
                    session_id,
                    student_id,
                    record["sequence_number"],
                    record["timestamp"],
                    record["text"],
                    record["classification"],
                    1 if record.get("violation") else 0,
                    record.get("violation_type"),
                    json.dumps(record.get("concept_tags", [])),
                ),
            )
            conn.commit()

    def insert_violation(self, session_id: str, student_id: str, record: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO violations (
                    violation_id, question_id, session_id, student_id,
                    sequence_number, timestamp, violation_type, severity,
                    question_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["violation_id"],
                    record["question_id"],
                    session_id,
                    student_id,
                    record["sequence_number"],
                    record["timestamp"],
                    record["violation_type"],
                    record["severity"],
                    record["question_text"],
                ),
            )
            conn.commit()

    def insert_verification(
        self, session_id: str, student_id: str, record: dict
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO verifications (
                    verification_id, session_id, student_id, question_id,
                    timestamp, passes, reason, guidance_level, draft_excerpt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["verification_id"],
                    session_id,
                    student_id,
                    record.get("question_id"),
                    record["timestamp"],
                    1 if record["passes"] else 0,
                    record.get("reason"),
                    record.get("guidance_level", "FULL"),
                    record.get("draft_excerpt", ""),
                ),
            )
            conn.commit()
