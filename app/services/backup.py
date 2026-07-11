from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app.db import Database


class BackupError(ValueError):
    pass


class BackupService:
    FORMAT_VERSION = 1

    def __init__(self, db_path: str | Path, library_dir: str | Path):
        self.db_path = Path(db_path)
        self.library_dir = Path(library_dir)

    def create_backup(self, target: str | Path) -> dict:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.is_file():
            raise BackupError("Database does not exist")

        with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
            temporary_dir = Path(temporary)
            snapshot = temporary_dir / "database.sqlite3"
            with sqlite3.connect(self.db_path) as source, sqlite3.connect(snapshot) as dest:
                source.backup(dest)

            library_files = [
                path
                for path in self.library_dir.rglob("*")
                if path.is_file() and not path.is_symlink()
            ] if self.library_dir.exists() else []
            manifest = {
                "format_version": self.FORMAT_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "schema_version": Database(snapshot).schema_version(),
                "library_files": len(library_files),
            }
            staged_archive = temporary_dir / "backup.zip"
            with zipfile.ZipFile(
                staged_archive, "w", compression=zipfile.ZIP_DEFLATED
            ) as bundle:
                bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
                bundle.write(snapshot, "database.sqlite3")
                for path in library_files:
                    relative = path.relative_to(self.library_dir)
                    bundle.write(path, (PurePosixPath("library") / relative).as_posix())
            staged_archive.replace(target)
        return manifest

    def inspect_backup(self, archive: str | Path) -> dict:
        archive = Path(archive)
        if not zipfile.is_zipfile(archive):
            raise BackupError("Backup is not a valid ZIP archive")
        try:
            with zipfile.ZipFile(archive) as bundle:
                self._validate_members(bundle.namelist())
                manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
                if "database.sqlite3" not in bundle.namelist():
                    raise BackupError("Backup database is missing")
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            raise BackupError("Backup manifest is invalid") from exc
        if manifest.get("format_version") != self.FORMAT_VERSION:
            raise BackupError("Unsupported backup format")
        return manifest

    def restore_backup(self, archive: str | Path) -> dict:
        archive = Path(archive)
        manifest = self.inspect_backup(archive)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.db_path.parent) as temporary:
            stage = Path(temporary)
            staged_db = stage / "database.sqlite3"
            staged_library = stage / "library"
            with zipfile.ZipFile(archive) as bundle:
                for info in bundle.infolist():
                    if info.filename == "database.sqlite3":
                        with bundle.open(info) as source, staged_db.open("wb") as target:
                            shutil.copyfileobj(source, target)
                    elif info.filename.startswith("library/") and not info.is_dir():
                        relative = PurePosixPath(info.filename).relative_to("library")
                        target = staged_library.joinpath(*relative.parts)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with bundle.open(info) as source, target.open("wb") as output:
                            shutil.copyfileobj(source, output)

            self._validate_database(staged_db)
            old_db = self.db_path.with_name(f".{self.db_path.name}.restore-old")
            old_library = self.library_dir.with_name(
                f".{self.library_dir.name}.restore-old"
            )
            old_db.unlink(missing_ok=True)
            if old_library.exists():
                shutil.rmtree(old_library)
            try:
                if self.db_path.exists():
                    os.replace(self.db_path, old_db)
                if self.library_dir.exists():
                    os.replace(self.library_dir, old_library)
                os.replace(staged_db, self.db_path)
                staged_library.mkdir(exist_ok=True)
                os.replace(staged_library, self.library_dir)
            except Exception:
                self.db_path.unlink(missing_ok=True)
                if old_db.exists():
                    os.replace(old_db, self.db_path)
                if self.library_dir.exists():
                    shutil.rmtree(self.library_dir)
                if old_library.exists():
                    os.replace(old_library, self.library_dir)
                raise
            finally:
                old_db.unlink(missing_ok=True)
                if old_library.exists():
                    shutil.rmtree(old_library)
                for suffix in ("-wal", "-shm"):
                    Path(f"{self.db_path}{suffix}").unlink(missing_ok=True)
        return manifest

    @staticmethod
    def _validate_members(names: list[str]) -> None:
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise BackupError(f"Backup contains unsafe path: {name}")
        if "manifest.json" not in names:
            raise BackupError("Backup manifest is missing")

    @staticmethod
    def _validate_database(path: Path) -> None:
        try:
            with sqlite3.connect(path) as conn:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                notes = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='notes'"
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise BackupError("Backup database is invalid") from exc
        if integrity != "ok" or notes is None:
            raise BackupError("Backup database failed integrity validation")
