import io

import pytest

from app.db import Database
from app.services.embeddings import HashEmbeddingProvider
from app.services.library import LibraryService
from app.services.memory import MemoryService
from app.services.study_bridge import StudyBridgeService


class FakeAiClient:
    def summarize_and_tag(self, title, content):
        return {"summary": content[:80], "tags": ["study"], "available": False}


def make_bridge(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    embedder = HashEmbeddingProvider(dimensions=64)
    memory = MemoryService(db=db, embedder=embedder, ai_client=FakeAiClient())
    library = LibraryService(
        db=db,
        embedder=embedder,
        library_dir=tmp_path / "library",
        max_upload_bytes=1024 * 1024,
    )
    return StudyBridgeService(memory), memory, library


def test_export_pack_contains_instructions_notes_documents_and_citations(tmp_path):
    bridge, memory, library = make_bridge(tmp_path)
    course = library.create_course(name="Information Theory", code="IT", term="2026")
    memory.create_note(
        title="Entropy intuition",
        content="Entropy measures uncertainty.",
        source="lecture reflection",
        course_id=course["id"],
    )
    library.import_file(
        course["id"],
        "lecture.md",
        "text/markdown",
        io.BytesIO(b"# Mutual information\nIt measures shared information."),
    )

    exported = bridge.export_pack(course["id"])

    assert "# Local Memory Study Pack" in exported
    assert "## ChatGPT Project Instructions" in exported
    assert "Information Theory" in exported
    assert "Entropy intuition" in exported
    assert "lecture.md" in exported
    assert "Mutual information" in exported
    assert "Do not invent" in exported
    assert str(tmp_path) not in exported
    assert "NOTION_TOKEN" not in exported


def test_import_structured_result_creates_note_and_candidate(tmp_path):
    bridge, memory, library = make_bridge(tmp_path)
    course = library.create_course(name="Networks")
    markdown = """# Local Memory Study Result

## Reviewed Note
Title: Distance vector mistake
Source: ChatGPT study result
### Content
Count-to-infinity happens after some failures.

## Card Candidate
Prompt: What is count-to-infinity?
Source: routing.md · Bellman-Ford
### Answer
It is slow convergence caused by repeated metric increases.
"""

    summary = bridge.import_result(course["id"], markdown)

    assert summary == {"notes": 1, "card_candidates": 1}
    notes = memory.list_notes()
    assert notes[0]["title"] == "Distance vector mistake"
    assert notes[0]["course_id"] == course["id"]
    candidates = memory.study.list_candidates(course_id=course["id"])
    assert any(card["prompt"] == "What is count-to-infinity?" for card in candidates)
    assert all(card["state"] == "candidate" for card in candidates)


@pytest.mark.parametrize(
    "markdown",
    [
        "",
        "# Local Memory Study Result\nNo structured sections.",
        "## Reviewed Note\nTitle: Missing content",
        "## Card Candidate\nPrompt: Missing answer",
    ],
)
def test_import_rejects_empty_or_malformed_results(tmp_path, markdown):
    bridge, _, library = make_bridge(tmp_path)
    course = library.create_course(name="Validation")

    with pytest.raises(ValueError):
        bridge.import_result(course["id"], markdown)
