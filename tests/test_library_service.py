import io

import pytest

from app.db import Database
from app.services.library import LibraryService, UploadTooLargeError


NOW = "2026-07-11T00:00:00+00:00"


class FakeEmbedder:
    version = "test-v1"

    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]


def make_library_service(tmp_path, max_upload_bytes: int = 1024 * 1024):
    db = Database(tmp_path / "memory.db")
    db.init()
    return LibraryService(
        db=db,
        embedder=FakeEmbedder(),
        library_dir=tmp_path / "library",
        max_upload_bytes=max_upload_bytes,
    )


def test_course_schema_preserves_existing_notes(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    note = db.insert_note(
        title="Existing",
        content="Keep me",
        source="manual",
        summary="Keep me",
        ai_available=False,
        tags=["keep"],
        embedding=[1.0, 0.0],
        embedding_model="test-v1",
        created_at=NOW,
        updated_at=NOW,
    )

    db.init()
    course = db.create_course(
        name="Information Theory",
        code="EE123",
        term="2026",
    )

    assert db.get_note(note["id"])["title"] == "Existing"
    assert course["status"] == "active"
    assert db.list_courses() == [course]


def test_document_chunks_keep_location_labels(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    course = db.create_course(name="Networks")
    document = db.insert_source_document(
        course_id=course["id"],
        title="Lecture 1",
        source_type="pdf",
        mime_type="application/pdf",
        managed_path="library/a.pdf",
        origin_url="",
        external_id="",
        content_hash="abc",
        status="processing",
        error_message="",
        imported_at=NOW,
        source_updated_at="",
        updated_at=NOW,
    )
    db.insert_document_chunks(
        document["id"],
        [
            {
                "position": 0,
                "location_label": "page 3",
                "heading": "Entropy",
                "content": "Entropy measures uncertainty.",
                "embedding": [1.0, 0.0],
                "embedding_model": "test-v1",
            }
        ],
    )

    chunks = db.list_document_chunks(document["id"])

    assert chunks[0]["location_label"] == "page 3"
    assert chunks[0]["heading"] == "Entropy"
    assert chunks[0]["embedding"] == [1.0, 0.0]


def test_import_markdown_copies_file_and_embeds_cited_chunks(tmp_path):
    service = make_library_service(tmp_path)
    course = service.create_course(name="Information Theory")

    imported = service.import_file(
        course_id=course["id"],
        filename="lecture.md",
        mime_type="text/markdown",
        stream=io.BytesIO(b"# Entropy\nUncertainty is measurable."),
    )

    assert imported["status"] == "ready"
    assert imported["duplicate"] is False
    assert (tmp_path / "library" / imported["stored_filename"]).is_file()
    assert imported["chunks"][0]["location_label"] == "Entropy"
    assert imported["chunks"][0]["embedding"] is not None
    candidates = service.db.list_study_cards(state="candidate")
    assert candidates[0]["source_document_id"] == imported["id"]
    assert candidates[0]["source_label"] == "Entropy"


def test_retrying_document_does_not_duplicate_card_candidates(tmp_path):
    service = make_library_service(tmp_path)
    course = service.create_course(name="Information Theory")
    imported = service.import_file(
        course["id"],
        "lecture.md",
        "text/markdown",
        io.BytesIO(b"# Entropy\nUncertainty is measurable."),
    )

    service.retry_document(imported["id"])

    candidates = service.db.list_study_cards(state="candidate")
    assert len(candidates) == 1
    assert candidates[0]["source_label"] == "Entropy"


def test_duplicate_import_returns_existing_document(tmp_path):
    service = make_library_service(tmp_path)
    course = service.create_course(name="Networks")

    first = service.import_file(
        course["id"], "a.txt", "text/plain", io.BytesIO(b"same content")
    )
    second = service.import_file(
        course["id"], "b.txt", "text/plain", io.BytesIO(b"same content")
    )

    assert second["id"] == first["id"]
    assert second["duplicate"] is True
    assert len(service.list_documents()) == 1


def test_failed_parse_keeps_original_and_reports_error(tmp_path):
    service = make_library_service(tmp_path)
    course = service.create_course(name="Systems")

    result = service.import_file(
        course["id"],
        "broken.pdf",
        "application/pdf",
        io.BytesIO(b"not a pdf"),
    )

    assert result["status"] == "failed"
    assert (tmp_path / "library" / result["stored_filename"]).exists()
    assert result["error_message"]


def test_image_import_waits_for_ocr(tmp_path):
    service = make_library_service(tmp_path)
    course = service.create_course(name="Whiteboard")

    result = service.import_file(
        course["id"], "board.png", "image/png", io.BytesIO(b"\x89PNG\r\n\x1a\n")
    )

    assert result["status"] == "ocr_required"
    assert "OCR" in result["error_message"]


def test_import_rejects_file_over_size_limit_without_leaving_temp_file(tmp_path):
    service = make_library_service(tmp_path, max_upload_bytes=4)
    course = service.create_course(name="Limits")

    with pytest.raises(UploadTooLargeError):
        service.import_file(
            course["id"], "large.txt", "text/plain", io.BytesIO(b"12345")
        )

    assert list((tmp_path / "library").glob(".import-*")) == []
