from datetime import datetime, timezone

from app.db import Database
from app.services.study import StudyService


NOW = "2026-07-11T08:00:00+00:00"


def insert_legacy_note(db: Database, title: str = "Legacy note") -> dict:
    return db.insert_note(
        title=title,
        content="Legacy review content.",
        source="manual",
        summary="Legacy review content.",
        ai_available=False,
        tags=["legacy"],
        embedding=[1.0, 0.0],
        embedding_model="test-v1",
        created_at=NOW,
        updated_at=NOW,
    )


def test_migrates_existing_note_and_review_state_idempotently(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    note = insert_legacy_note(db)
    db.upsert_review_state(
        note_id=note["id"],
        due_at="2026-07-20T08:00:00+00:00",
        interval_days=7.0,
        ease=2.35,
        reps=4,
        last_grade="good",
        updated_at=NOW,
    )
    with db.connect() as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = 3")

    db.init()
    db.init()

    cards = db.list_study_cards(state="active")
    assert len(cards) == 1
    assert cards[0]["note_id"] == note["id"]
    assert cards[0]["prompt"] == "Legacy note"
    assert cards[0]["due_at"] == "2026-07-20T08:00:00+00:00"
    assert cards[0]["interval_days"] == 7.0
    assert cards[0]["ease"] == 2.35
    assert cards[0]["reps"] == 4
    assert cards[0]["last_grade"] == "good"


def test_candidate_approval_queue_grading_and_suspend(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    service = StudyService(db)
    candidate = service.create_candidate(
        prompt="Original prompt",
        answer="Original answer",
        source_label="manual",
    )

    assert service.queue() == []
    assert service.list_candidates()[0]["id"] == candidate["id"]

    approved = service.approve(
        candidate["id"], prompt="Edited prompt", answer="Edited answer"
    )
    assert approved["state"] == "active"
    assert approved["prompt"] == "Edited prompt"
    assert service.queue()[0]["id"] == candidate["id"]

    graded = service.grade(candidate["id"], "good")
    assert graded["reps"] == 1
    assert graded["interval_days"] >= 1.0
    assert service.queue() == []

    suspended = service.suspend(candidate["id"])
    assert suspended["state"] == "suspended"


def test_reject_requires_candidate_state(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    service = StudyService(db)
    candidate = service.create_candidate(
        prompt="Question", answer="Answer", source_label="source"
    )

    rejected = service.reject(candidate["id"])
    assert rejected["state"] == "rejected"

    try:
        service.approve(candidate["id"])
    except ValueError as exc:
        assert "candidate" in str(exc).lower()
    else:
        raise AssertionError("Rejected card must not be approvable")
