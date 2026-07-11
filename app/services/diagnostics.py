from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
from pathlib import Path

from app.db import Database


class DiagnosticsService:
    def __init__(self, *, db: Database, library_dir, embedder, ai_client, ocr_provider):
        self.db = db
        self.library_dir = Path(library_dir)
        self.embedder = embedder
        self.ai_client = ai_client
        self.ocr_provider = ocr_provider

    def report(self) -> dict:
        self.library_dir.mkdir(parents=True, exist_ok=True)
        storage_writable = self._writable(self.library_dir)
        database_writable = self._database_writable()
        return {
            "database": {
                "writable": database_writable,
                "schema_version": self.db.schema_version(),
                "size_bytes": self.db.path.stat().st_size if self.db.path.exists() else 0,
            },
            "storage": {
                "writable": storage_writable,
                "free_bytes": shutil.disk_usage(self.library_dir).free,
            },
            "parsers": {
                "pdf": importlib.util.find_spec("pypdf") is not None,
                "docx": importlib.util.find_spec("docx") is not None,
                "pptx": importlib.util.find_spec("pptx") is not None,
            },
            "ocr": {
                "available": bool(self.ocr_provider.is_available()),
                "provider": getattr(self.ocr_provider, "name", "unknown"),
            },
            "embedding": {"version": getattr(self.embedder, "version", "unknown")},
            "ollama": {"available": bool(self.ai_client.is_available())},
            "notion": {"configured": bool(os.getenv("NOTION_TOKEN", "").strip())},
        }

    def _database_writable(self) -> bool:
        try:
            with self.db.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("ROLLBACK")
            return True
        except Exception:
            return False

    @staticmethod
    def _writable(directory: Path) -> bool:
        try:
            descriptor, name = tempfile.mkstemp(dir=directory)
            os.close(descriptor)
            Path(name).unlink(missing_ok=True)
            return True
        except OSError:
            return False
