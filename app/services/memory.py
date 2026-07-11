from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import Database
from app.services.embeddings import EmbeddingProvider, cosine_similarity, tokenize
from app.services.retrieval import UnifiedRetrievalService


class MemoryService:
    def __init__(self, db: Database, embedder: EmbeddingProvider, ai_client: Any):
        self.db = db
        self.embedder = embedder
        self.ai_client = ai_client
        self.retrieval = UnifiedRetrievalService(db, embedder)

    @property
    def embedding_version(self) -> str:
        return getattr(self.embedder, "version", "hash-v1")

    def ensure_embeddings(self) -> int:
        """Re-embed notes whose stored vectors were built by a different
        tokenizer or embedding model, so query and note vectors stay comparable."""
        stale_ids = self.db.list_stale_embedding_note_ids(self.embedding_version)
        for note_id in stale_ids:
            note = self.db.get_note(note_id)
            embedding = self.embedder.embed(
                f"{note['title']}\n{note['content']}\n{note['summary']}\n{' '.join(note['tags'])}"
            )
            self.db.update_embedding(note_id, embedding, self.embedding_version)
        return len(stale_ids)

    def set_ollama_model(self, model: str) -> str:
        clean_model = model.strip()
        if not clean_model:
            raise ValueError("Model name is required")
        self.db.set_setting("ollama_model", clean_model)
        setter = getattr(self.ai_client, "set_model", None)
        if callable(setter):
            setter(clean_model)
        return clean_model

    def create_note(
        self,
        *,
        title: str,
        content: str,
        source: str = "",
        course_id: int | None = None,
        created_at: datetime | None = None,
    ) -> dict:
        clean_title = title.strip()
        clean_content = content.strip()
        clean_source = source.strip()
        if not clean_title:
            raise ValueError("Title is required")
        if not clean_content:
            raise ValueError("Content is required")
        if course_id is not None:
            self.db.get_course(course_id)

        ai = self.ai_client.summarize_and_tag(clean_title, clean_content)
        summary = str(ai.get("summary") or clean_content[:180]).strip()
        tags = self._clean_tags(ai.get("tags") or [])
        timestamp = self._iso(created_at or datetime.now(timezone.utc))
        embedding = self.embedder.embed(
            f"{clean_title}\n{clean_content}\n{summary}\n{' '.join(tags)}"
        )
        return self.db.insert_note(
            title=clean_title,
            content=clean_content,
            source=clean_source,
            summary=summary,
            ai_available=bool(ai.get("available")),
            tags=tags,
            embedding=embedding,
            embedding_model=self.embedding_version,
            created_at=timestamp,
            updated_at=timestamp,
            course_id=course_id,
        )

    def get_note(self, note_id: int) -> dict:
        return self.db.get_note(note_id)

    def update_note(
        self,
        note_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        source: str | None = None,
    ) -> dict:
        existing = self.db.get_note(note_id)
        new_title = (title if title is not None else existing["title"]).strip()
        new_content = (content if content is not None else existing["content"]).strip()
        new_source = (source if source is not None else existing["source"]).strip()
        if not new_title:
            raise ValueError("Title is required")
        if not new_content:
            raise ValueError("Content is required")

        ai = self.ai_client.summarize_and_tag(new_title, new_content)
        summary = str(ai.get("summary") or new_content[:180]).strip()
        tags = self._clean_tags(ai.get("tags") or [])
        timestamp = self._iso(datetime.now(timezone.utc))
        embedding = self.embedder.embed(
            f"{new_title}\n{new_content}\n{summary}\n{' '.join(tags)}"
        )
        return self.db.update_note(
            note_id,
            title=new_title,
            content=new_content,
            source=new_source,
            summary=summary,
            ai_available=bool(ai.get("available")),
            tags=tags,
            embedding=embedding,
            embedding_model=self.embedding_version,
            updated_at=timestamp,
        )

    def delete_note(self, note_id: int) -> None:
        self.db.delete_note(note_id)

    def list_tags(self) -> list[dict]:
        return self.db.list_tags()

    def list_notes(self, limit: int = 100, offset: int = 0, tag: str | None = None) -> list[dict]:
        return self.db.list_notes(limit=limit, offset=offset, tag=tag)

    def search_notes(
        self,
        query: str,
        limit: int = 10,
        tag: str | None = None,
        *,
        course_id: int | None = None,
        source_document_id: int | None = None,
    ) -> list[dict]:
        return self.retrieval.search(
            query,
            limit=limit,
            tag=tag,
            course_id=course_id,
            source_document_id=source_document_id,
        )

    def similar_notes(self, note_id: int, limit: int = 5) -> list[dict]:
        source = self.get_note(note_id)
        scored: list[dict] = []
        for note in self.db.list_notes(limit=1000):
            if note["id"] == note_id:
                continue
            score = cosine_similarity(source.get("embedding"), note.get("embedding"))
            result = {key: value for key, value in note.items() if key != "embedding"}
            result["score"] = round(float(score), 6)
            scored.append(result)
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]

    def ask_question(
        self,
        question: str,
        limit: int = 5,
        *,
        course_id: int | None = None,
        source_document_id: int | None = None,
    ) -> dict:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("Question is required")
        sources = self.search_notes(
            clean_question,
            limit=limit,
            course_id=course_id,
            source_document_id=source_document_id,
        )
        answer = self.ai_client.answer_question(clean_question, sources)
        return {
            "question": clean_question,
            "answer": answer.get("answer", ""),
            "ai_available": bool(answer.get("available")),
            "sources": sources,
        }

    def generate_weekly_review(self, week_start: str, week_end: str) -> dict:
        notes = self.db.list_notes_between(week_start, week_end)
        generated = self.ai_client.weekly_review(notes, week_start, week_end)
        review = self.db.save_weekly_review(
            week_start=week_start,
            week_end=week_end,
            content=str(generated.get("review") or ""),
            ai_available=bool(generated.get("available")),
            created_at=self._iso(datetime.now(timezone.utc)),
        )
        return review

    def list_weekly_reviews(self) -> list[dict]:
        return self.db.list_weekly_reviews()

    def study_queue(self, limit: int = 10) -> list[dict]:
        now = self._iso(datetime.now(timezone.utc))
        notes = self.db.list_due_notes(now, limit=limit)
        return [
            {key: value for key, value in note.items() if key != "embedding"}
            for note in notes
        ]

    def grade_note(self, note_id: int, grade: str) -> dict:
        clean_grade = grade.strip().lower()
        if clean_grade not in {"again", "good", "easy"}:
            raise ValueError("Grade must be one of: again, good, easy")
        self.db.get_note(note_id)

        state = self.db.get_review_state(note_id)
        ease = state["ease"] if state else 2.5
        interval = state["interval_days"] if state else 0.0
        reps = state["reps"] if state else 0

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
            ease = ease + 0.15
            interval = 3.0 if reps == 0 else max(3.0, interval * ease * 1.3)
            reps += 1
            due = now + timedelta(days=interval)

        saved = self.db.upsert_review_state(
            note_id=note_id,
            due_at=self._iso(due),
            interval_days=round(interval, 2),
            ease=round(ease, 2),
            reps=reps,
            last_grade=clean_grade,
            updated_at=self._iso(now),
        )
        return {
            "note_id": note_id,
            "grade": clean_grade,
            "due_at": saved["due_at"],
            "interval_days": saved["interval_days"],
            "ease": saved["ease"],
            "reps": saved["reps"],
        }

    def stats(self) -> dict:
        now = datetime.now(timezone.utc)
        today = now.date()
        counts = Counter(self.db.list_note_dates())

        days = [today - timedelta(days=offset) for offset in range(13, -1, -1)]
        activity = [
            {"date": day.isoformat(), "count": counts.get(day.isoformat(), 0)}
            for day in days
        ]

        streak = 0
        cursor = today if counts.get(today.isoformat()) else today - timedelta(days=1)
        while counts.get(cursor.isoformat()):
            streak += 1
            cursor -= timedelta(days=1)

        monday = today - timedelta(days=today.weekday())
        notes_this_week = sum(
            count for day, count in counts.items() if day >= monday.isoformat()
        )

        return {
            "total_notes": sum(counts.values()),
            "notes_this_week": notes_this_week,
            "streak_days": streak,
            "due_now": self.db.count_due_notes(self._iso(now)),
            "reviewed_today": self.db.count_reviews_on(today.isoformat()),
            "daily_activity": activity,
            "top_tags": self.db.list_tags()[:8],
        }

    def export_markdown(self) -> str:
        notes = self.db.list_notes(limit=100000)
        lines = ["# Local Memory Export", ""]
        for note in reversed(notes):
            lines.append(f"## {note['title']}")
            lines.append("")
            lines.append(f"- Created: {note['created_at'][:10]}")
            if note["source"]:
                lines.append(f"- Source: {note['source']}")
            if note["tags"]:
                lines.append(f"- Tags: {', '.join(note['tags'])}")
            if note["summary"]:
                lines.append(f"- Summary: {note['summary']}")
            lines.append("")
            lines.append(note["content"])
            lines.append("")
        return "\n".join(lines)

    def health(self) -> dict:
        return {
            "storage": "sqlite",
            "database": str(self.db.path),
            "local_only": True,
            "ollama_available": bool(getattr(self.ai_client, "is_available", lambda: False)()),
            "ollama_model": getattr(self.ai_client, "current_model", ""),
            "embedding": self.embedding_version,
        }

    def _keyword_score(self, query_tokens: set[str], note: dict) -> float:
        if not query_tokens:
            return 0.0
        haystack = " ".join(
            [
                note.get("title", ""),
                note.get("content", ""),
                note.get("summary", ""),
                " ".join(note.get("tags", [])),
            ]
        )
        note_tokens = set(tokenize(haystack))
        if not note_tokens:
            return 0.0
        overlap = len(query_tokens & note_tokens)
        return overlap / len(query_tokens)

    def _fts_query(self, query: str) -> str:
        tokens = tokenize(query)
        if not tokens:
            return query
        return " OR ".join(tokens)

    def _clean_tags(self, tags: list[Any]) -> list[str]:
        cleaned: list[str] = []
        for tag in tags:
            value = str(tag).strip().lower().replace(" ", "-")
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned[:8] or ["memory"]

    def _iso(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
