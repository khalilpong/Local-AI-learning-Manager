from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import Database


class StudyService:
    def __init__(self, db: Database):
        self.db = db

    def create_candidate(
        self,
        *,
        prompt: str,
        answer: str,
        source_label: str,
        course_id: int | None = None,
        note_id: int | None = None,
        source_document_id: int | None = None,
        source_chunk_id: int | None = None,
    ) -> dict:
        clean_prompt = prompt.strip()
        clean_answer = answer.strip()
        if not clean_prompt or not clean_answer:
            raise ValueError("Card prompt and answer are required")
        return self.db.insert_study_card(
            prompt=clean_prompt,
            answer=clean_answer,
            source_label=source_label.strip(),
            state="candidate",
            course_id=course_id,
            note_id=note_id,
            source_document_id=source_document_id,
            source_chunk_id=source_chunk_id,
        )

    def list_candidates(
        self, course_id: int | None = None, limit: int = 100
    ) -> list[dict]:
        return self.db.list_study_cards(
            state="candidate", course_id=course_id, limit=limit
        )

    def approve(
        self,
        card_id: int,
        *,
        prompt: str | None = None,
        answer: str | None = None,
    ) -> dict:
        card = self._require_state(card_id, "candidate")
        clean_prompt = card["prompt"] if prompt is None else prompt.strip()
        clean_answer = card["answer"] if answer is None else answer.strip()
        if not clean_prompt or not clean_answer:
            raise ValueError("Card prompt and answer are required")
        now = self._iso(datetime.now(timezone.utc))
        return self.db.update_study_card(
            card_id,
            prompt=clean_prompt,
            answer=clean_answer,
            state="active",
            due_at=now,
            updated_at=now,
        )

    def reject(self, card_id: int) -> dict:
        self._require_state(card_id, "candidate")
        return self.db.update_study_card(
            card_id,
            state="rejected",
            updated_at=self._iso(datetime.now(timezone.utc)),
        )

    def suspend(self, card_id: int) -> dict:
        self._require_state(card_id, "active")
        return self.db.update_study_card(
            card_id,
            state="suspended",
            updated_at=self._iso(datetime.now(timezone.utc)),
        )

    def queue(
        self, limit: int = 20, course_id: int | None = None
    ) -> list[dict]:
        return self.db.list_due_study_cards(
            self._iso(datetime.now(timezone.utc)),
            limit=limit,
            course_id=course_id,
        )

    def grade(self, card_id: int, grade: str) -> dict:
        clean_grade = grade.strip().lower()
        if clean_grade not in {"again", "good", "easy"}:
            raise ValueError("Grade must be one of: again, good, easy")
        card = self._require_state(card_id, "active")
        ease = float(card["ease"])
        interval = float(card["interval_days"])
        reps = int(card["reps"])
        now = datetime.now(timezone.utc)

        if clean_grade == "again":
            ease = max(1.3, ease - 0.2)
            reps = 0
            interval = 0.0
            due = now + timedelta(minutes=10)
        elif clean_grade == "good":
            interval = 1.0 if reps == 0 else max(1.0, interval * ease)
            reps += 1
            due = now + timedelta(days=interval)
        else:
            ease += 0.15
            interval = 3.0 if reps == 0 else max(3.0, interval * ease * 1.3)
            reps += 1
            due = now + timedelta(days=interval)

        updated = self.db.update_study_card(
            card_id,
            due_at=self._iso(due),
            interval_days=round(interval, 2),
            ease=round(ease, 2),
            reps=reps,
            last_grade=clean_grade,
            updated_at=self._iso(now),
        )
        return {
            "card_id": card_id,
            "grade": clean_grade,
            "due_at": updated["due_at"],
            "interval_days": updated["interval_days"],
            "ease": updated["ease"],
            "reps": updated["reps"],
        }

    def _require_state(self, card_id: int, expected: str) -> dict:
        card = self.db.get_study_card(card_id)
        if card["state"] != expected:
            raise ValueError(f"Study card must be {expected}")
        return card

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()
