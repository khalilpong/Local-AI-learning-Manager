from datetime import datetime, timedelta, timezone

from app.db import Database
from app.services.dashboard import DashboardService


def make_db(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    return db


def add_card(db, course_id, *, state="active", due_at, ease=2.5, reps=1, last_grade="good", prompt="Q"):
    card = db.insert_study_card(
        course_id=course_id,
        prompt=prompt,
        answer="A",
        source_label="manual",
        state=state,
        due_at=due_at,
    )
    return db.update_study_card(
        card["id"], ease=ease, reps=reps, last_grade=last_grade, due_at=due_at, state=state
    )


def test_dashboard_counts_notes_documents_and_cards(tmp_path):
    db = make_db(tmp_path)
    course = db.create_course(name="Systems", code="CS", term="F26")
    now = datetime.now(timezone.utc)

    db.insert_note(
        title="Note", content="Body", source="manual", summary="s",
        ai_available=False, tags=[], embedding=[1.0], embedding_model="t",
        created_at=now.isoformat(), updated_at=now.isoformat(), course_id=course["id"],
    )
    db.insert_source_document(
        course_id=course["id"], title="ok.md", source_type="markdown", mime_type="",
        managed_path="/tmp/ok.md", origin_url="", external_id="", content_hash="h1",
        status="ready", error_message="", imported_at=now.isoformat(),
        source_updated_at="", updated_at=now.isoformat(),
    )
    db.insert_source_document(
        course_id=course["id"], title="bad.pdf", source_type="pdf", mime_type="",
        managed_path="/tmp/bad.pdf", origin_url="", external_id="", content_hash="h2",
        status="failed", error_message="broken", imported_at=now.isoformat(),
        source_updated_at="", updated_at=now.isoformat(),
    )

    add_card(db, course["id"], state="candidate", due_at=now.isoformat())
    add_card(db, course["id"], state="active", due_at=(now - timedelta(days=1)).isoformat())
    add_card(db, course["id"], state="active", due_at=(now + timedelta(days=3)).isoformat())

    report = DashboardService(db).course_dashboard(course["id"])

    assert report["course"]["name"] == "Systems"
    assert report["notes"] == 1
    assert report["documents"]["total"] == 2
    assert report["documents"]["unresolved"] == 1
    assert report["cards"]["candidate"] == 1
    assert report["cards"]["active"] == 2
    assert report["cards"]["due"] == 1  # only the overdue active card is due now


def test_dashboard_surfaces_weak_cards(tmp_path):
    db = make_db(tmp_path)
    course = db.create_course(name="Weak")
    now = datetime.now(timezone.utc)

    add_card(db, course["id"], due_at=now.isoformat(), ease=2.6, prompt="Strong")
    add_card(db, course["id"], due_at=now.isoformat(), ease=1.4, prompt="Weak one")
    add_card(db, course["id"], due_at=now.isoformat(), ease=2.5, last_grade="again", prompt="Forgot")

    report = DashboardService(db).course_dashboard(course["id"])
    prompts = [c["prompt"] for c in report["weak_cards"]]

    assert "Weak one" in prompts
    assert "Forgot" in prompts
    assert "Strong" not in prompts


def test_dashboard_review_load_is_seven_days_with_overdue_today(tmp_path):
    db = make_db(tmp_path)
    course = db.create_course(name="Load")
    now = datetime.now(timezone.utc)
    today = now.date()

    add_card(db, course["id"], due_at=(now - timedelta(days=2)).isoformat())  # overdue
    add_card(db, course["id"], due_at=now.isoformat())  # today
    add_card(db, course["id"], due_at=(now + timedelta(days=2)).isoformat())  # day 2

    report = DashboardService(db).course_dashboard(course["id"])
    load = report["review_load"]

    assert len(load) == 7
    assert load[0]["date"] == today.isoformat()
    assert load[0]["count"] == 2  # overdue folded into today + the card due today
    assert load[2]["count"] == 1


def test_dashboard_missing_course_raises(tmp_path):
    db = make_db(tmp_path)
    try:
        DashboardService(db).course_dashboard(999)
    except KeyError:
        return
    raise AssertionError("expected KeyError for missing course")
