from app.db import Database


NOW = "2026-07-11T00:00:00+00:00"


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
