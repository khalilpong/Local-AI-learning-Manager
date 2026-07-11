import zipfile

import pytest

from app.db import Database
from app.services.backup import BackupError, BackupService


def make_data(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    note = db.insert_note(
        title="Backup note",
        content="Restore this content.",
        source="manual",
        summary="Restore this content.",
        ai_available=False,
        tags=["backup"],
        embedding=[1.0],
        embedding_model="test-v1",
        created_at="2026-07-11T00:00:00+00:00",
        updated_at="2026-07-11T00:00:00+00:00",
    )
    library = tmp_path / "library"
    library.mkdir()
    (library / "lecture.md").write_text("# Original", encoding="utf-8")
    return db, library, note


def test_backup_restore_round_trip_includes_database_and_library(tmp_path):
    db, library, note = make_data(tmp_path)
    service = BackupService(db.path, library)
    archive = tmp_path / "backup.zip"

    summary = service.create_backup(archive)

    assert summary["schema_version"] == 3
    assert summary["library_files"] == 1
    with zipfile.ZipFile(archive) as bundle:
        assert {"manifest.json", "database.sqlite3", "library/lecture.md"} <= set(
            bundle.namelist()
        )

    db.delete_note(note["id"])
    (library / "lecture.md").write_text("changed", encoding="utf-8")
    service.restore_backup(archive)

    assert db.get_note(note["id"])["content"] == "Restore this content."
    assert (library / "lecture.md").read_text(encoding="utf-8") == "# Original"


def test_restore_rejects_corrupt_archive_without_changing_data(tmp_path):
    db, library, note = make_data(tmp_path)
    archive = tmp_path / "broken.zip"
    archive.write_bytes(b"not a zip")

    with pytest.raises(BackupError):
        BackupService(db.path, library).restore_backup(archive)

    assert db.get_note(note["id"])["title"] == "Backup note"


def test_restore_rejects_zip_path_traversal(tmp_path):
    db, library, note = make_data(tmp_path)
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "bad")
        bundle.writestr("manifest.json", "{}")
        bundle.writestr("database.sqlite3", "bad")

    with pytest.raises(BackupError, match="unsafe"):
        BackupService(db.path, library).restore_backup(archive)

    assert db.get_note(note["id"])["title"] == "Backup note"
    assert not (tmp_path.parent / "escape.txt").exists()
