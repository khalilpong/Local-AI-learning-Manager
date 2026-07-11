import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.db import Database
from app.services.embeddings import HashEmbeddingProvider
from app.services.library import LibraryService
from app.services.memory import MemoryService


class FakeAiClient:
    def summarize_and_tag(self, title: str, content: str):
        return {
            "summary": f"Summary for {title}",
            "tags": ["python", "local-ai"],
            "available": True,
        }

    def answer_question(self, question: str, notes: list[dict]):
        titles = ", ".join(note["title"] for note in notes)
        return {
            "answer": f"Answer based on: {titles}",
            "available": True,
        }

    def weekly_review(self, notes: list[dict], week_start: str, week_end: str):
        return {
            "review": f"Reviewed {len(notes)} notes from {week_start} to {week_end}.",
            "available": True,
        }


def make_service(root: Path):
    db = Database(root / "memory.db")
    db.init()
    return MemoryService(
        db=db,
        embedder=HashEmbeddingProvider(dimensions=64),
        ai_client=FakeAiClient(),
    )


def make_services(root: Path):
    memory = make_service(root)
    library = LibraryService(
        db=memory.db,
        embedder=memory.embedder,
        library_dir=root / "library",
        max_upload_bytes=1024 * 1024,
    )
    return memory, library


class MemoryServiceTest(unittest.TestCase):
    def test_unified_search_returns_document_chunk_with_citation(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory, library = make_services(Path(tmp))
            course = library.create_course(name="Information Theory")
            library.import_file(
                course["id"],
                "entropy.md",
                "text/markdown",
                io.BytesIO(b"# Entropy\nEntropy measures uncertainty."),
            )

            results = memory.search_notes("uncertainty", course_id=course["id"])

            self.assertEqual(results[0]["kind"], "document")
            self.assertEqual(results[0]["source_title"], "entropy.md")
            self.assertEqual(results[0]["location_label"], "Entropy")
            self.assertEqual(results[0]["course_name"], "Information Theory")

    def test_question_sources_include_document_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory, library = make_services(Path(tmp))
            course = library.create_course(name="Networks")
            library.import_file(
                course["id"],
                "routing.md",
                "text/markdown",
                io.BytesIO(b"# Bellman-Ford\nRouting uses relaxation."),
            )

            answer = memory.ask_question(
                "How does routing update paths?", course_id=course["id"]
            )

            self.assertEqual(answer["sources"][0]["location_label"], "Bellman-Ford")
            self.assertIn("routing.md", answer["answer"])

    def test_create_note_stores_summary_tags_and_embedding(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))

            note = service.create_note(
                title="FastAPI project idea",
                content="Build a local knowledge base with SQLite and semantic search.",
                source="project",
            )

            self.assertGreater(note["id"], 0)
            self.assertEqual(note["summary"], "Summary for FastAPI project idea")
            self.assertEqual(note["tags"], ["python", "local-ai"])

            stored = service.get_note(note["id"])
            self.assertEqual(stored["title"], "FastAPI project idea")
            self.assertEqual(stored["source"], "project")
            self.assertIsNotNone(stored["embedding"])


    def test_update_note_regenerates_summary_tags_and_embedding(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            note = service.create_note(
                title="Draft idea",
                content="Rough notes about local search.",
            )

            updated = service.update_note(
                note["id"],
                title="Refined idea",
                content="Polished notes about local vector search.",
            )

            self.assertEqual(updated["title"], "Refined idea")
            self.assertEqual(updated["content"], "Polished notes about local vector search.")
            self.assertEqual(updated["summary"], "Summary for Refined idea")

            stored = service.get_note(note["id"])
            self.assertEqual(stored["title"], "Refined idea")

    def test_delete_note_removes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            note = service.create_note(title="Temp", content="Temporary content to delete.")

            service.delete_note(note["id"])

            with self.assertRaises(KeyError):
                service.get_note(note["id"])

    def test_list_notes_filters_by_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            service.create_note(title="Note A", content="Content about tagging systems.")
            service.create_note(title="Note B", content="Unrelated grocery content.")

            tags = service.list_tags()
            self.assertGreater(len(tags), 0)
            target_tag = tags[0]["tag"]

            filtered = service.list_notes(tag=target_tag)
            self.assertTrue(all(target_tag in note["tags"] for note in filtered))

    def test_semantic_search_returns_relevant_notes_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            service.create_note(
                title="Python vector search",
                content="Embeddings help retrieve similar technical notes.",
            )
            service.create_note(
                title="Grocery list",
                content="Milk, bread, apples, and coffee.",
            )

            results = service.search_notes("How do I search with embeddings?", limit=2)

            self.assertEqual([result["title"] for result in results][0], "Python vector search")
            self.assertGreaterEqual(results[0]["score"], results[1]["score"])


    def test_question_answer_uses_retrieved_notes_as_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            service.create_note(
                title="Ollama setup",
                content="Run ollama serve locally and pull qwen2.5 for summaries.",
            )

            response = service.ask_question("How should I run the model?")

            self.assertIn("Ollama setup", response["answer"])
            self.assertEqual(response["sources"][0]["title"], "Ollama setup")


    def test_chinese_search_matches_multi_character_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            service.create_note(
                title="机器学习笔记",
                content="今天学习了机器学习的基础概念，包括监督学习和无监督学习。",
            )
            service.create_note(
                title="晚餐购物清单",
                content="牛奶、面包、苹果和咖啡。",
            )

            results = service.search_notes("机器学习", limit=2)

            self.assertEqual(results[0]["title"], "机器学习笔记")
            self.assertGreater(results[0]["score"], results[1]["score"])

    def test_stale_embeddings_rebuilt_on_ensure(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            note = service.create_note(
                title="Embedding versioning",
                content="Vectors must be rebuilt when the tokenizer changes.",
            )

            with service.db.connect() as conn:
                conn.execute(
                    "UPDATE note_embeddings SET model = 'hash-v1', vector_json = '[0.0]' "
                    "WHERE note_id = ?",
                    (note["id"],),
                )

            rebuilt = service.ensure_embeddings()

            self.assertEqual(rebuilt, 1)
            state = service.db.get_note(note["id"])
            self.assertGreater(len(state["embedding"]), 1)
            self.assertEqual(service.ensure_embeddings(), 0)

    def test_study_queue_and_grading_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            note = service.create_note(
                title="Recall me",
                content="Spaced repetition strengthens long-term memory.",
            )

            queue = service.study_queue()
            self.assertEqual([item["id"] for item in queue], [note["id"]])

            result = service.grade_note(note["id"], "good")
            self.assertGreaterEqual(result["interval_days"], 1.0)
            self.assertEqual(result["reps"], 1)
            self.assertEqual(service.study_queue(), [])

            again = service.grade_note(note["id"], "again")
            self.assertEqual(again["reps"], 0)
            self.assertLess(again["ease"], 2.5)

            with self.assertRaises(ValueError):
                service.grade_note(note["id"], "meh")
            with self.assertRaises(KeyError):
                service.grade_note(99999, "good")

    def test_stats_reports_activity_and_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            first = service.create_note(title="Note A", content="Alpha content.")
            service.create_note(title="Note B", content="Beta content.")
            service.grade_note(first["id"], "good")

            stats = service.stats()

            self.assertEqual(stats["total_notes"], 2)
            self.assertEqual(stats["due_now"], 1)
            self.assertEqual(stats["reviewed_today"], 1)
            self.assertGreaterEqual(stats["streak_days"], 1)
            self.assertEqual(len(stats["daily_activity"]), 14)
            self.assertEqual(stats["daily_activity"][-1]["count"], 2)

    def test_export_markdown_contains_all_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            service.create_note(title="Exported note", content="Content to export.")

            exported = service.export_markdown()

            self.assertIn("# Local Memory Export", exported)
            self.assertIn("## Exported note", exported)
            self.assertIn("Content to export.", exported)

    def test_weekly_review_persists_generated_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = make_service(Path(tmp))
            service.create_note(
                title="Monday learning",
                content="Practiced English sentences and backend design.",
                created_at=datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
            )

            review = service.generate_weekly_review("2026-07-06", "2026-07-12")

            self.assertEqual(
                review["content"], "Reviewed 1 notes from 2026-07-06 to 2026-07-12."
            )
            self.assertEqual(service.list_weekly_reviews()[0]["week_start"], "2026-07-06")


if __name__ == "__main__":
    unittest.main()
