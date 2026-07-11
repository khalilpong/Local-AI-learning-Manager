from __future__ import annotations

import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from app.db import Database
from app.services.documents import (
    DocumentParseError,
    OcrRequiredError,
    chunk_located_text,
    detect_document_type,
    parse_document,
)


class UploadTooLargeError(ValueError):
    pass


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name or "document"


class LibraryService:
    def __init__(
        self,
        *,
        db: Database,
        embedder,
        library_dir: str | Path,
        max_upload_bytes: int,
    ):
        if max_upload_bytes < 1:
            raise ValueError("max_upload_bytes must be positive")
        self.db = db
        self.embedder = embedder
        self.library_dir = Path(library_dir)
        self.max_upload_bytes = max_upload_bytes

    def create_course(self, *, name: str, code: str = "", term: str = "") -> dict:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Course name is required")
        return self.db.create_course(
            name=clean_name,
            code=code.strip(),
            term=term.strip(),
        )

    def import_file(
        self,
        course_id: int,
        filename: str,
        mime_type: str,
        stream: BinaryIO,
    ) -> dict:
        self.db.get_course(course_id)
        safe_filename = sanitize_filename(filename)
        document_type = detect_document_type(safe_filename, mime_type)
        self.library_dir.mkdir(parents=True, exist_ok=True)

        temporary_path, content_hash = self._stage_upload(stream)
        existing = self.db.find_source_document_by_hash(content_hash)
        if existing is not None:
            temporary_path.unlink(missing_ok=True)
            return self.get_document(existing["id"], duplicate=True)

        managed_path = self.library_dir / f"{content_hash[:16]}-{safe_filename}"
        temporary_path.replace(managed_path)
        now = datetime.now(timezone.utc).isoformat()
        document = self.db.insert_source_document(
            course_id=course_id,
            title=safe_filename,
            source_type=document_type,
            mime_type=mime_type,
            managed_path=str(managed_path),
            origin_url="",
            external_id="",
            content_hash=content_hash,
            status="processing",
            error_message="",
            imported_at=now,
            source_updated_at="",
            updated_at=now,
        )
        self._parse_and_index(document["id"], managed_path, document_type)
        return self.get_document(document["id"])

    def _stage_upload(self, stream: BinaryIO) -> tuple[Path, str]:
        digest = hashlib.sha256()
        size = 0
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".import-", dir=self.library_dir
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as target:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.max_upload_bytes:
                        raise UploadTooLargeError(
                            f"Upload exceeds the {self.max_upload_bytes}-byte limit"
                        )
                    digest.update(chunk)
                    target.write(chunk)
            return temporary_path, digest.hexdigest()
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def _parse_and_index(
        self, document_id: int, managed_path: Path, document_type: str
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        try:
            parsed = parse_document(managed_path, document_type)
            chunks = chunk_located_text(parsed.blocks)
            indexed_chunks = [
                {
                    "position": chunk.position,
                    "location_label": chunk.location_label,
                    "heading": chunk.heading,
                    "content": chunk.content,
                    "embedding": self.embedder.embed(chunk.content),
                    "embedding_model": self.embedder.version,
                }
                for chunk in chunks
            ]
            self.db.insert_document_chunks(document_id, indexed_chunks)
            self.db.update_source_document(
                document_id,
                status="ready",
                error_message="",
                updated_at=now,
            )
        except OcrRequiredError as exc:
            self.db.update_source_document(
                document_id,
                status="ocr_required",
                error_message=str(exc),
                updated_at=now,
            )
        except (DocumentParseError, OSError, ValueError) as exc:
            self.db.update_source_document(
                document_id,
                status="failed",
                error_message=str(exc) or type(exc).__name__,
                updated_at=now,
            )

    def get_document(self, document_id: int, *, duplicate: bool = False) -> dict:
        document = self.db.get_source_document(document_id)
        document["stored_filename"] = Path(document["managed_path"]).name
        document["chunks"] = self.db.list_document_chunks(document_id)
        document["duplicate"] = duplicate
        return document

    def list_documents(self, course_id: int | None = None) -> list[dict]:
        return [
            self.get_document(document["id"])
            for document in self.db.list_source_documents(course_id)
        ]

    def retry_document(self, document_id: int) -> dict:
        document = self.db.get_source_document(document_id)
        managed_path = Path(document["managed_path"])
        self.db.update_source_document(
            document_id,
            status="processing",
            error_message="",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._parse_and_index(document_id, managed_path, document["source_type"])
        return self.get_document(document_id)
