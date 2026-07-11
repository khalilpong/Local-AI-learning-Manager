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
    LocatedText,
    OcrRequiredError,
    chunk_located_text,
    detect_document_type,
    parse_document,
)
from app.services.notion import NotionClient, NotionPage
from app.services.ocr import NullOcrProvider, OcrProvider
from app.services.webcapture import Fetcher, Resolver, capture_page


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
        ocr_provider: OcrProvider | None = None,
    ):
        if max_upload_bytes < 1:
            raise ValueError("max_upload_bytes must be positive")
        self.db = db
        self.embedder = embedder
        self.library_dir = Path(library_dir)
        self.max_upload_bytes = max_upload_bytes
        self.ocr_provider = ocr_provider or NullOcrProvider()

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

    def import_web_page(
        self,
        course_id: int,
        url: str,
        *,
        fetcher: Fetcher | None = None,
        resolver: Resolver | None = None,
    ) -> dict:
        self.db.get_course(course_id)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        page = capture_page(url, fetcher=fetcher, resolver=resolver)

        content_hash = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
        existing = self.db.find_source_document_by_hash(content_hash)
        if existing is not None:
            return self.get_document(existing["id"], duplicate=True)

        safe_filename = sanitize_filename(f"{page.title}.txt")
        managed_path = self.library_dir / f"{content_hash[:16]}-{safe_filename}"
        managed_path.write_text(
            f"# {page.title}\n{page.url}\n\n{page.text}", encoding="utf-8"
        )
        now = datetime.now(timezone.utc).isoformat()
        document = self.db.insert_source_document(
            course_id=course_id,
            title=page.title,
            source_type="web",
            mime_type="text/html",
            managed_path=str(managed_path),
            origin_url=page.url,
            external_id="",
            content_hash=content_hash,
            status="processing",
            error_message="",
            imported_at=now,
            source_updated_at=page.retrieved_at,
            updated_at=now,
        )
        self._index_blocks(
            document["id"],
            [LocatedText(page.text, "web page", page.title)],
        )
        return self.get_document(document["id"])

    def _ocr_and_index(self, document_id: int, managed_path: Path) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.ocr_provider.is_available():
            self.db.update_source_document(
                document_id,
                status="ocr_required",
                error_message="No OCR provider is available for this image",
                updated_at=now,
            )
            return
        try:
            text = self.ocr_provider.extract_text(managed_path).strip()
        except Exception as exc:  # provider/runtime failures keep the file for retry
            self.db.update_source_document(
                document_id,
                status="failed",
                error_message=f"OCR failed: {exc}" or type(exc).__name__,
                updated_at=now,
            )
            return
        if not text:
            self.db.update_source_document(
                document_id,
                status="ocr_required",
                error_message="OCR produced no text; the image may have no readable content",
                updated_at=now,
            )
            return
        self._index_blocks(
            document_id, [LocatedText(text, "image OCR", managed_path.stem)]
        )

    def sync_notion(self, course_id: int, client: NotionClient) -> dict:
        """One-way, idempotent, read-only pull of shared Notion pages.

        Unchanged pages are skipped, edited pages are re-indexed, and pages that
        no longer appear in Notion are archived locally instead of deleted.
        """
        self.db.get_course(course_id)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        pages = client.list_shared_pages()
        seen: set[str] = set()
        imported = updated = unchanged = 0

        for page in pages:
            if not page.id:
                continue
            seen.add(page.id)
            outcome = self._sync_one_notion_page(course_id, page)
            if outcome == "imported":
                imported += 1
            elif outcome == "updated":
                updated += 1
            else:
                unchanged += 1

        archived = 0
        for document in self.db.list_source_documents(
            course_id, source_type="notion", include_archived=False
        ):
            if document["external_id"] and document["external_id"] not in seen:
                now = datetime.now(timezone.utc).isoformat()
                self.db.update_source_document(
                    document["id"], archived_at=now, updated_at=now
                )
                archived += 1

        return {
            "imported": imported,
            "updated": updated,
            "unchanged": unchanged,
            "archived": archived,
        }

    def _sync_one_notion_page(self, course_id: int, page: NotionPage) -> str:
        # Page identity is the Notion id; hash includes it so distinct pages
        # never collide on the unique content_hash even with identical text.
        content_hash = hashlib.sha256(
            f"notion:{page.id}:{page.text}".encode("utf-8")
        ).hexdigest()
        existing = self.db.find_source_document_by_external_id(page.id)
        now = datetime.now(timezone.utc).isoformat()

        if existing is not None:
            unchanged = (
                existing["source_updated_at"] == page.last_edited_time
                and existing["content_hash"] == content_hash
                and not existing["archived_at"]
                and existing["status"] == "ready"
            )
            if unchanged:
                return "unchanged"
            managed_path = Path(existing["managed_path"])
            managed_path.write_text(
                f"# {page.title}\n{page.url}\n\n{page.text}", encoding="utf-8"
            )
            self.db.update_source_document(
                existing["id"],
                title=page.title,
                origin_url=page.url,
                content_hash=content_hash,
                source_updated_at=page.last_edited_time,
                archived_at="",
                status="processing",
                error_message="",
                updated_at=now,
            )
            self._index_blocks(
                existing["id"], [LocatedText(page.text, "notion page", page.title)]
            )
            return "updated"

        safe_filename = sanitize_filename(f"notion-{page.id}.txt")
        managed_path = self.library_dir / safe_filename
        managed_path.write_text(
            f"# {page.title}\n{page.url}\n\n{page.text}", encoding="utf-8"
        )
        document = self.db.insert_source_document(
            course_id=course_id,
            title=page.title,
            source_type="notion",
            mime_type="text/plain",
            managed_path=str(managed_path),
            origin_url=page.url,
            external_id=page.id,
            content_hash=content_hash,
            status="processing",
            error_message="",
            imported_at=now,
            source_updated_at=page.last_edited_time,
            updated_at=now,
        )
        self._index_blocks(
            document["id"], [LocatedText(page.text, "notion page", page.title)]
        )
        return "imported"

    def _index_blocks(self, document_id: int, blocks: list[LocatedText]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        try:
            chunks = chunk_located_text(blocks)
            if not chunks:
                raise DocumentParseError("No extractable text")
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
                document_id, status="ready", error_message="", updated_at=now
            )
        except (DocumentParseError, OSError, ValueError) as exc:
            self.db.update_source_document(
                document_id,
                status="failed",
                error_message=str(exc) or type(exc).__name__,
                updated_at=now,
            )

    def _parse_and_index(
        self, document_id: int, managed_path: Path, document_type: str
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if document_type == "image":
            self._ocr_and_index(document_id, managed_path)
            return
        try:
            parsed = parse_document(managed_path, document_type)
            self._index_blocks(document_id, parsed.blocks)
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
