"""Per-course learning dashboard metrics computed from local data only."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.db import Database


class DashboardService:
    def __init__(self, db: Database):
        self.db = db

    def course_dashboard(self, course_id: int) -> dict:
        course = self.db.get_course(course_id)
        now = datetime.now(timezone.utc)
        today = now.date()

        document_status = self.db.course_document_status_counts(course_id)
        unresolved = document_status.get("failed", 0) + document_status.get(
            "ocr_required", 0
        )
        card_states = self.db.study_card_state_counts(course_id)

        weak_cards = [
            {
                "id": card["id"],
                "prompt": card["prompt"],
                "ease": round(float(card["ease"]), 2),
                "reps": card["reps"],
                "source_label": card.get("source_label", ""),
            }
            for card in self.db.list_weak_study_cards(course_id)
        ]

        review_load = self._review_load(course_id, today, now)

        return {
            "course": {
                "id": course["id"],
                "name": course["name"],
                "code": course["code"],
                "term": course["term"],
                "status": course["status"],
            },
            "notes": self.db.count_notes_for_course(course_id),
            "documents": {
                "total": sum(document_status.values()),
                "by_status": document_status,
                "unresolved": unresolved,
            },
            "cards": {
                "candidate": card_states.get("candidate", 0),
                "active": card_states.get("active", 0),
                "suspended": card_states.get("suspended", 0),
                "due": self._due_count(course_id, now),
            },
            "weak_cards": weak_cards,
            "review_load": review_load,
        }

    def _due_count(self, course_id: int, now: datetime) -> int:
        return len(
            self.db.list_due_study_cards(
                now.isoformat(), limit=100000, course_id=course_id
            )
        )

    def _review_load(self, course_id: int, today: date, now: datetime) -> list[dict]:
        days = [(today + timedelta(days=offset)).isoformat() for offset in range(7)]
        counts = self.db.study_review_load(course_id, days)
        # Active cards whose due date is before today are already late; fold them
        # into today's bar so the upcoming-load view never hides overdue work.
        overdue = self.db.count_active_cards_due_before(course_id, today.isoformat())
        return [
            {
                "date": day,
                "count": counts.get(day, 0) + (overdue if index == 0 else 0),
            }
            for index, day in enumerate(days)
        ]
