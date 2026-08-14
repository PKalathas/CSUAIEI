"""Default SQLite implementation of `SystemStore`.

Holds multi-tenant metadata: users, courses, enrollments. Mirrors the
connection idioms used by the participant/guardian SQLite stores
(`PRAGMA busy_timeout`, `journal_mode=DELETE` to avoid stale SMB journal
files on Azure Files).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


SYSTEM_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name        TEXT NOT NULL DEFAULT '',
    sso_subject TEXT UNIQUE,
    role        TEXT NOT NULL CHECK (role IN ('admin','instructor','student')),
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_sso   ON users(sso_subject);

CREATE TABLE IF NOT EXISTS courses (
    id                     TEXT PRIMARY KEY,
    name                   TEXT NOT NULL,
    instructor_id          TEXT NOT NULL,
    blob_container_name    TEXT NOT NULL,
    search_index_name      TEXT NOT NULL,
    search_indexer_name    TEXT NOT NULL,
    search_datasource_name TEXT NOT NULL,
    -- NULL when the course uses the default data/courses/{id}/ convention.
    -- Populated for the legacy default course so the un-prefixed routes
    -- keep reading data/participant.db & data/guardian.db.
    participant_db_path    TEXT,
    guardian_db_path       TEXT,
    created_at             TEXT NOT NULL,
    FOREIGN KEY(instructor_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_courses_instructor ON courses(instructor_id);

CREATE TABLE IF NOT EXISTS enrollments (
    course_id   TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    enrolled_at TEXT NOT NULL,
    PRIMARY KEY (course_id, user_id),
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id)   REFERENCES users(id)   ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_enrollments_user ON enrollments(user_id);
"""


class SqliteSystemStore:
    """Default `SystemStore` impl. One SQLite file holds all metadata."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)

    def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path, timeout=30, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = OFF")
            for stmt in SYSTEM_SCHEMA.strip().split(";"):
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
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------- users
    def insert_user(self, item: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, email, name, sso_subject, role, created_at)
                VALUES (:id, :email, :name, :sso_subject, :role, :created_at)
                """,
                {
                    "id": item["id"],
                    "email": item["email"],
                    "name": item.get("name", ""),
                    "sso_subject": item.get("sso_subject"),
                    "role": item["role"],
                    "created_at": item["created_at"],
                },
            )
            conn.commit()

    def get_user(self, user_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_sso_subject(self, subject: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE sso_subject = ?", (subject,)
            ).fetchone()
            return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_user_sso_subject(self, user_id: str, sso_subject: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET sso_subject = ? WHERE id = ?",
                (sso_subject, user_id),
            )
            conn.commit()

    def delete_user(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()

    # ----------------------------------------------------------- courses
    def insert_course(self, item: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO courses (
                    id, name, instructor_id,
                    blob_container_name, search_index_name,
                    search_indexer_name, search_datasource_name,
                    participant_db_path, guardian_db_path,
                    created_at
                ) VALUES (
                    :id, :name, :instructor_id,
                    :blob_container_name, :search_index_name,
                    :search_indexer_name, :search_datasource_name,
                    :participant_db_path, :guardian_db_path,
                    :created_at
                )
                """,
                {
                    "id": item["id"],
                    "name": item["name"],
                    "instructor_id": item["instructor_id"],
                    "blob_container_name": item["blob_container_name"],
                    "search_index_name": item["search_index_name"],
                    "search_indexer_name": item["search_indexer_name"],
                    "search_datasource_name": item["search_datasource_name"],
                    "participant_db_path": item.get("participant_db_path"),
                    "guardian_db_path": item.get("guardian_db_path"),
                    "created_at": item["created_at"],
                },
            )
            conn.commit()

    def get_course(self, course_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_courses(self, *, instructor_id: Optional[str] = None) -> list[dict]:
        with self._connect() as conn:
            if instructor_id is None:
                rows = conn.execute(
                    "SELECT * FROM courses ORDER BY created_at ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM courses WHERE instructor_id = ? "
                    "ORDER BY created_at ASC",
                    (instructor_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def update_course(self, course_id: str, patch: dict) -> None:
        if not patch:
            return
        fields = ", ".join(f"{k} = ?" for k in patch.keys())
        with self._connect() as conn:
            conn.execute(
                f"UPDATE courses SET {fields} WHERE id = ?",
                (*patch.values(), course_id),
            )
            conn.commit()

    def delete_course(self, course_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
            conn.commit()

    # ------------------------------------------------------- enrollments
    def insert_enrollment(self, course_id: str, user_id: str, enrolled_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO enrollments (course_id, user_id, enrolled_at) "
                "VALUES (?, ?, ?)",
                (course_id, user_id, enrolled_at),
            )
            conn.commit()

    def delete_enrollment(self, course_id: str, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM enrollments WHERE course_id = ? AND user_id = ?",
                (course_id, user_id),
            )
            conn.commit()

    def is_enrolled(self, course_id: str, user_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM enrollments WHERE course_id = ? AND user_id = ?",
                (course_id, user_id),
            ).fetchone()
            return row is not None

    def list_enrolled_users(self, course_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT u.*, e.enrolled_at
                  FROM users u
                  JOIN enrollments e ON e.user_id = u.id
                 WHERE e.course_id = ?
                 ORDER BY e.enrolled_at ASC
                """,
                (course_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_courses_for_user(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*
                  FROM courses c
                  JOIN enrollments e ON e.course_id = c.id
                 WHERE e.user_id = ?
                 ORDER BY c.created_at ASC
                """,
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
