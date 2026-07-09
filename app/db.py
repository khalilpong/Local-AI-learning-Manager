from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    ai_available INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS note_tags (
                    note_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    PRIMARY KEY (note_id, tag),
                    FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS note_embeddings (
                    note_id INTEGER PRIMARY KEY,
                    vector_json TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT 'hash-v1',
                    FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS weekly_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_start TEXT NOT NULL,
                    week_end TEXT NOT NULL,
                    content TEXT NOT NULL,
                    ai_available INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE (week_start, week_end)
                );

                CREATE TABLE IF NOT EXISTS review_states (
                    note_id INTEGER PRIMARY KEY,
                    due_at TEXT NOT NULL,
                    interval_days REAL NOT NULL DEFAULT 0,
                    ease REAL NOT NULL DEFAULT 2.5,
                    reps INTEGER NOT NULL DEFAULT 0,
                    last_grade TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
                );
                """
            )
            self._migrate(conn)
            self._init_fts(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(note_embeddings)").fetchall()
        }
        if "model" not in columns:
            conn.execute(
                "ALTER TABLE note_embeddings ADD COLUMN model TEXT NOT NULL DEFAULT 'hash-v1'"
            )

    def _init_fts(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
                USING fts5(title, content, summary)
                """
            )
        except sqlite3.OperationalError:
            # Some Python builds omit FTS5. Semantic search and token scoring
            # still work, so the app should remain usable.
            pass

    def insert_note(
        self,
        *,
        title: str,
        content: str,
        source: str,
        summary: str,
        ai_available: bool,
        tags: Iterable[str],
        embedding: list[float],
        embedding_model: str,
        created_at: str,
        updated_at: str,
    ) -> dict:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO notes
                    (title, content, source, summary, ai_available, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, content, source, summary, int(ai_available), created_at, updated_at),
            )
            note_id = int(cur.lastrowid)
            conn.executemany(
                "INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?)",
                [(note_id, tag) for tag in tags],
            )
            conn.execute(
                "INSERT INTO note_embeddings (note_id, vector_json, model) VALUES (?, ?, ?)",
                (note_id, json.dumps(embedding), embedding_model),
            )
            self._upsert_fts(conn, note_id, title, content, summary)
        return self.get_note(note_id)

    def _upsert_fts(
        self,
        conn: sqlite3.Connection,
        note_id: int,
        title: str,
        content: str,
        summary: str,
    ) -> None:
        try:
            conn.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
            conn.execute(
                "INSERT INTO notes_fts(rowid, title, content, summary) VALUES (?, ?, ?, ?)",
                (note_id, title, content, summary),
            )
        except sqlite3.OperationalError:
            pass

    def get_note(self, note_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            if row is None:
                raise KeyError(f"Note {note_id} not found")
            return self._hydrate_note(conn, row)

    def update_note(
        self,
        note_id: int,
        *,
        title: str,
        content: str,
        source: str,
        summary: str,
        ai_available: bool,
        tags: Iterable[str],
        embedding: list[float],
        embedding_model: str,
        updated_at: str,
    ) -> dict:
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE notes
                SET title = ?, content = ?, source = ?, summary = ?,
                    ai_available = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, content, source, summary, int(ai_available), updated_at, note_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"Note {note_id} not found")
            conn.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
            conn.executemany(
                "INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?)",
                [(note_id, tag) for tag in tags],
            )
            conn.execute(
                """
                INSERT INTO note_embeddings (note_id, vector_json, model) VALUES (?, ?, ?)
                ON CONFLICT(note_id) DO UPDATE SET
                    vector_json = excluded.vector_json,
                    model = excluded.model
                """,
                (note_id, json.dumps(embedding), embedding_model),
            )
            self._upsert_fts(conn, note_id, title, content, summary)
        return self.get_note(note_id)

    def delete_note(self, note_id: int) -> None:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            if cur.rowcount == 0:
                raise KeyError(f"Note {note_id} not found")
            try:
                conn.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
            except sqlite3.OperationalError:
                pass

    def list_notes(self, limit: int = 100, offset: int = 0, tag: str | None = None) -> list[dict]:
        with self.connect() as conn:
            if tag:
                rows = conn.execute(
                    """
                    SELECT notes.* FROM notes
                    JOIN note_tags ON note_tags.note_id = notes.id
                    WHERE note_tags.tag = ?
                    ORDER BY datetime(notes.created_at) DESC, notes.id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (tag, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM notes
                    ORDER BY datetime(created_at) DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
            return [self._hydrate_note(conn, row) for row in rows]

    def list_tags(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT tag, COUNT(*) AS count FROM note_tags
                GROUP BY tag
                ORDER BY count DESC, tag ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_notes_between(self, week_start: str, week_end: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM notes
                WHERE date(created_at) BETWEEN date(?) AND date(?)
                ORDER BY datetime(created_at) ASC, id ASC
                """,
                (week_start, week_end),
            ).fetchall()
            return [self._hydrate_note(conn, row) for row in rows]

    def save_weekly_review(
        self,
        *,
        week_start: str,
        week_end: str,
        content: str,
        ai_available: bool,
        created_at: str,
    ) -> dict:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO weekly_reviews
                    (week_start, week_end, content, ai_available, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(week_start, week_end)
                DO UPDATE SET
                    content = excluded.content,
                    ai_available = excluded.ai_available,
                    created_at = excluded.created_at
                """,
                (week_start, week_end, content, int(ai_available), created_at),
            )
            row = conn.execute(
                """
                SELECT * FROM weekly_reviews
                WHERE week_start = ? AND week_end = ?
                """,
                (week_start, week_end),
            ).fetchone()
            return dict(row)

    def list_weekly_reviews(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM weekly_reviews
                ORDER BY date(week_start) DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_setting(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def list_stale_embedding_note_ids(self, current_model: str) -> list[int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT note_id FROM note_embeddings WHERE model != ?",
                (current_model,),
            ).fetchall()
            return [int(row["note_id"]) for row in rows]

    def update_embedding(self, note_id: int, embedding: list[float], model: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO note_embeddings (note_id, vector_json, model) VALUES (?, ?, ?)
                ON CONFLICT(note_id) DO UPDATE SET
                    vector_json = excluded.vector_json,
                    model = excluded.model
                """,
                (note_id, json.dumps(embedding), model),
            )

    def get_review_state(self, note_id: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_states WHERE note_id = ?", (note_id,)
            ).fetchone()
            return dict(row) if row else None

    def upsert_review_state(
        self,
        *,
        note_id: int,
        due_at: str,
        interval_days: float,
        ease: float,
        reps: int,
        last_grade: str,
        updated_at: str,
    ) -> dict:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO review_states
                    (note_id, due_at, interval_days, ease, reps, last_grade, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(note_id) DO UPDATE SET
                    due_at = excluded.due_at,
                    interval_days = excluded.interval_days,
                    ease = excluded.ease,
                    reps = excluded.reps,
                    last_grade = excluded.last_grade,
                    updated_at = excluded.updated_at
                """,
                (note_id, due_at, interval_days, ease, reps, last_grade, updated_at),
            )
        state = self.get_review_state(note_id)
        assert state is not None
        return state

    def list_due_notes(self, now_iso: str, limit: int = 10) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT notes.*, review_states.due_at AS due_at, review_states.reps AS reps
                FROM notes
                LEFT JOIN review_states ON review_states.note_id = notes.id
                WHERE review_states.due_at IS NULL OR review_states.due_at <= ?
                ORDER BY (review_states.due_at IS NULL) DESC,
                         review_states.due_at ASC,
                         datetime(notes.created_at) ASC
                LIMIT ?
                """,
                (now_iso, limit),
            ).fetchall()
            return [self._hydrate_note(conn, row) for row in rows]

    def count_due_notes(self, now_iso: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM notes
                LEFT JOIN review_states ON review_states.note_id = notes.id
                WHERE review_states.due_at IS NULL OR review_states.due_at <= ?
                """,
                (now_iso,),
            ).fetchone()
            return int(row["count"])

    def count_reviews_on(self, day: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM review_states
                WHERE substr(updated_at, 1, 10) = ? AND last_grade != ''
                """,
                (day,),
            ).fetchone()
            return int(row["count"])

    def list_note_dates(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT substr(created_at, 1, 10) AS day FROM notes"
            ).fetchall()
            return [row["day"] for row in rows]

    def fts_search_ids(self, query: str, limit: int = 20) -> list[int]:
        with self.connect() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT rowid FROM notes_fts
                    WHERE notes_fts MATCH ?
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
            return [int(row["rowid"]) for row in rows]

    def _hydrate_note(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
        note = dict(row)
        note["ai_available"] = bool(note["ai_available"])
        note["tags"] = [
            tag_row["tag"]
            for tag_row in conn.execute(
                "SELECT tag FROM note_tags WHERE note_id = ? ORDER BY rowid",
                (note["id"],),
            ).fetchall()
        ]
        embedding_row = conn.execute(
            "SELECT vector_json FROM note_embeddings WHERE note_id = ?",
            (note["id"],),
        ).fetchone()
        note["embedding"] = json.loads(embedding_row["vector_json"]) if embedding_row else None
        return note
