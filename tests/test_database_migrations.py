import sqlite3

import pytest

from app.db import Database


def test_fresh_database_records_numbered_schema_versions(tmp_path):
    db = Database(tmp_path / "memory.db")

    db.init()
    db.init()

    assert db.schema_version() == 3
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert [row["version"] for row in rows] == [1, 2, 3]


def test_existing_notes_survive_versioned_upgrade(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                ai_available INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO notes (
                title, content, source, summary, ai_available, created_at, updated_at
            ) VALUES ('Legacy', 'Keep this', '', '', 0, '2026-01-01', '2026-01-01');
            """
        )

    db = Database(path)
    db.init()

    assert db.get_note(1)["title"] == "Legacy"
    assert db.schema_version() == 3


def test_failed_migration_rolls_back_statements_and_version_record(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()

    def failing(conn):
        conn.execute("CREATE TABLE rollback_probe (id INTEGER)")
        conn.execute("INSERT INTO missing_table VALUES (1)")

    with db.connect() as conn:
        with pytest.raises(sqlite3.OperationalError):
            db._apply_migration(conn, 99, "failing test migration", failing)

    with db.connect() as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'rollback_probe'"
        ).fetchone()
        version = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = 99"
        ).fetchone()
    assert table is None
    assert version is None
