from __future__ import annotations

from app.db import Database
from app.services.embeddings import EmbeddingProvider, cosine_similarity, tokenize


class UnifiedRetrievalService:
    def __init__(self, db: Database, embedder: EmbeddingProvider):
        self.db = db
        self.embedder = embedder

    def search(
        self,
        query: str,
        limit: int = 10,
        *,
        tag: str | None = None,
        course_id: int | None = None,
        source_document_id: int | None = None,
    ) -> list[dict]:
        clean_query = query.strip()
        records = self._note_records(
            tag=tag,
            course_id=course_id,
            source_document_id=source_document_id,
        )
        records.extend(
            self._document_records(
                course_id=course_id,
                source_document_id=source_document_id,
            )
        )
        if not clean_query:
            return [self._without_embedding(record, score=0.0) for record in records[:limit]]

        query_embedding = self.embedder.embed(clean_query)
        query_tokens = set(tokenize(clean_query))
        scored: list[dict] = []
        for record in records:
            vector_score = cosine_similarity(
                query_embedding, record.get("embedding")
            )
            record_tokens = set(
                tokenize(
                    f"{record['title']} {record.get('summary', '')} {record['content']}"
                )
            )
            keyword_score = (
                len(query_tokens & record_tokens) / len(query_tokens)
                if query_tokens
                else 0.0
            )
            score = (0.75 * vector_score) + (0.25 * keyword_score)
            scored.append(self._without_embedding(record, score=score))
        scored.sort(
            key=lambda item: (item["score"], item.get("updated_at", "")),
            reverse=True,
        )
        return scored[:limit]

    def _note_records(
        self,
        *,
        tag: str | None,
        course_id: int | None,
        source_document_id: int | None,
    ) -> list[dict]:
        records = []
        for note in self.db.list_notes(limit=1000, tag=tag):
            if course_id is not None and note.get("course_id") != course_id:
                continue
            if (
                source_document_id is not None
                and note.get("source_document_id") != source_document_id
            ):
                continue
            records.append({**note, "kind": "note"})
        return records

    def _document_records(
        self,
        *,
        course_id: int | None,
        source_document_id: int | None,
    ) -> list[dict]:
        records = []
        for chunk in self.db.list_searchable_document_chunks(
            course_id=course_id,
            source_document_id=source_document_id,
        ):
            records.append(
                {
                    "id": chunk["id"],
                    "kind": "document",
                    "title": chunk["source_title"],
                    "content": chunk["content"],
                    "summary": chunk["content"][:180],
                    "tags": [],
                    "source": chunk["course_name"],
                    "source_document_id": chunk["source_document_id"],
                    "source_title": chunk["source_title"],
                    "course_id": chunk["course_id"],
                    "course_name": chunk["course_name"],
                    "location_label": chunk["location_label"],
                    "heading": chunk["heading"],
                    "source_type": chunk["source_type"],
                    "created_at": chunk["imported_at"],
                    "updated_at": chunk["updated_at"],
                    "embedding": chunk["embedding"],
                }
            )
        return records

    @staticmethod
    def _without_embedding(record: dict, *, score: float) -> dict:
        result = {key: value for key, value in record.items() if key != "embedding"}
        result["score"] = round(float(score), 6)
        return result
