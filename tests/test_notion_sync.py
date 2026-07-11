from app.db import Database
from app.services.library import LibraryService
from app.services.notion import NotionPage


class FakeEmbedder:
    version = "test-v1"

    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]


class FakeNotionClient:
    def __init__(self, pages: list[NotionPage]):
        self.pages = pages

    def list_shared_pages(self) -> list[NotionPage]:
        return list(self.pages)


def make_service(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    return LibraryService(
        db=db,
        embedder=FakeEmbedder(),
        library_dir=tmp_path / "library",
        max_upload_bytes=1024 * 1024,
    )


def page(pid, text, edited, title=None):
    return NotionPage(
        id=pid,
        title=title or f"Page {pid}",
        url=f"https://notion.so/{pid}",
        last_edited_time=edited,
        text=text,
    )


def test_initial_sync_imports_and_indexes(tmp_path):
    service = make_service(tmp_path)
    course = service.create_course(name="Notion")
    client = FakeNotionClient(
        [
            page("a1", "Support vector machines maximize the margin.", "2026-07-01T00:00:00Z"),
            page("b2", "K-means clustering groups unlabeled data.", "2026-07-01T00:00:00Z"),
        ]
    )

    summary = service.sync_notion(course["id"], client)

    assert summary == {"imported": 2, "updated": 0, "unchanged": 0, "archived": 0}
    documents = service.list_documents(course["id"])
    assert {d["source_type"] for d in documents} == {"notion"}
    assert all(d["status"] == "ready" for d in documents)


def test_resync_is_idempotent(tmp_path):
    service = make_service(tmp_path)
    course = service.create_course(name="Notion")
    client = FakeNotionClient([page("a1", "Stable content.", "2026-07-01T00:00:00Z")])

    service.sync_notion(course["id"], client)
    summary = service.sync_notion(course["id"], client)

    assert summary == {"imported": 0, "updated": 0, "unchanged": 1, "archived": 0}
    assert len(service.list_documents(course["id"])) == 1


def test_edited_page_is_reindexed(tmp_path):
    service = make_service(tmp_path)
    course = service.create_course(name="Notion")
    client = FakeNotionClient([page("a1", "Original text.", "2026-07-01T00:00:00Z")])
    service.sync_notion(course["id"], client)

    client.pages = [page("a1", "Revised and expanded text.", "2026-07-02T00:00:00Z")]
    summary = service.sync_notion(course["id"], client)

    assert summary["updated"] == 1
    assert summary["imported"] == 0
    documents = service.list_documents(course["id"])
    assert len(documents) == 1
    assert "Revised" in documents[0]["chunks"][0]["content"]


def test_removed_page_is_archived_not_deleted(tmp_path):
    service = make_service(tmp_path)
    course = service.create_course(name="Notion")
    client = FakeNotionClient(
        [
            page("a1", "First page.", "2026-07-01T00:00:00Z"),
            page("b2", "Second page.", "2026-07-01T00:00:00Z"),
        ]
    )
    service.sync_notion(course["id"], client)

    client.pages = [page("a1", "First page.", "2026-07-01T00:00:00Z")]
    summary = service.sync_notion(course["id"], client)

    assert summary["archived"] == 1
    # Active listing hides the archived page, but it is retained locally.
    active = service.list_documents(course["id"])
    assert {d["external_id"] for d in active} == {"a1"}
    archived = service.db.list_source_documents(
        course["id"], source_type="notion", include_archived=True
    )
    assert {d["external_id"] for d in archived} == {"a1", "b2"}
    # Archived content is excluded from unified search.
    chunks = service.db.list_searchable_document_chunks(course_id=course["id"])
    assert all("Second page" not in c["content"] for c in chunks)


def test_reappearing_page_is_unarchived(tmp_path):
    service = make_service(tmp_path)
    course = service.create_course(name="Notion")
    full = [
        page("a1", "First.", "2026-07-01T00:00:00Z"),
        page("b2", "Second.", "2026-07-01T00:00:00Z"),
    ]
    client = FakeNotionClient(full)
    service.sync_notion(course["id"], client)
    client.pages = [full[0]]
    service.sync_notion(course["id"], client)

    # b2 comes back with a newer edit time.
    client.pages = [full[0], page("b2", "Second, restored.", "2026-07-03T00:00:00Z")]
    summary = service.sync_notion(course["id"], client)

    assert summary["updated"] == 1
    active = service.list_documents(course["id"])
    assert {d["external_id"] for d in active} == {"a1", "b2"}
