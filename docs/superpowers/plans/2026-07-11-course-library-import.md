# Course Library And Local Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add course organization and a managed local library that imports Markdown, TXT, PDF, DOCX, PPTX, and image files, then exposes cited document chunks through the existing search and question-answering workflows.

**Architecture:** Keep the current FastAPI, SQLite, and vanilla JavaScript application. Add focused parser, library, and retrieval services around the existing `Database`, `MemoryService`, and embedding provider. Store original files in a managed local directory, store located text chunks and embeddings in SQLite, and preserve all existing note behavior.

**Tech Stack:** Python 3.13, FastAPI, SQLite/FTS5, Jinja2, vanilla JavaScript, pytest, pypdf, python-docx, python-pptx.

## Global Constraints

- Bind only to `127.0.0.1` by default.
- Preserve all existing notes, tags, embeddings, weekly reviews, and review history.
- Keep Ollama optional; all tests run with offline or fake AI clients.
- Store managed source files below `MEMORY_DATA_DIR`; never depend on temporary upload paths.
- Treat image files as `ocr_required`; OCR belongs to Increment B.
- Reject files larger than `MEMORY_MAX_UPLOAD_MB`, default `100` MB.
- Sanitize file names and prevent managed paths from escaping the library directory.
- Deduplicate files by SHA-256 before parsing or embedding.
- Do not add Notion, web capture, VPS, OpenAI API, or Tauri work in this plan.
- Use `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` for verification on this machine.

---

## File Structure

- Create `app/services/documents.py`: parser dispatch, located text blocks, chunking, MIME/extension policy.
- Create `app/services/library.py`: managed file ingestion, hashing, deduplication, parser orchestration, status transitions.
- Create `app/services/retrieval.py`: unified ranking for notes and document chunks.
- Create `tests/test_document_parsers.py`: parser and chunking coverage.
- Create `tests/test_library_service.py`: course, managed storage, deduplication, failure, and citation coverage.
- Modify `app/db.py`: schema migration and course/document/chunk persistence only.
- Modify `app/settings.py`: managed library and upload limit settings.
- Modify `app/schemas.py`: course payloads and note course assignment.
- Modify `app/services/memory.py`: course-aware notes and delegation to unified retrieval.
- Modify `app/main.py`: course/library endpoints and multipart import.
- Modify `app/templates/index.html`: Library panel and course controls.
- Modify `app/static/app.js`: course loading, batch import, document status, filters.
- Modify `app/static/styles.css`: stable responsive dimensions for the new controls.
- Modify `requirements.txt`, `.env.example`, `README.md`, and `project-review.md`.

---

### Task 1: Schema Migration And Course Persistence

**Files:**
- Modify: `app/db.py:20-100,102-248,426-456`
- Modify: `app/schemas.py:1-31`
- Test: `tests/test_library_service.py`

**Interfaces:**
- Consumes: existing `Database.connect()` and `Database.init()`.
- Produces: `Database.create_course(name: str, code: str = "", term: str = "") -> dict`, `list_courses(status: str | None = "active") -> list[dict]`, `get_course(course_id: int) -> dict`, `update_course(course_id: int, *, name: str | None, code: str | None, term: str | None, status: str | None) -> dict`, `insert_source_document(**fields) -> dict`, `find_source_document_by_hash(content_hash: str) -> dict | None`, `update_source_document(document_id: int, **fields) -> dict`, `insert_document_chunks(document_id: int, chunks: list[dict]) -> None`, `list_source_documents(course_id: int | None = None) -> list[dict]`, `get_source_document(document_id: int) -> dict`, and `list_document_chunks(document_id: int) -> list[dict]`.

- [x] **Step 1: Write failing schema and migration tests**

```python
def test_course_and_document_schema_preserves_existing_notes(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    note = db.insert_note(
        title="Existing", content="Keep me", source="manual",
        summary="Keep me", ai_available=False, tags=["keep"],
        embedding=[1.0, 0.0], embedding_model="test-v1",
        created_at="2026-07-11T00:00:00+00:00",
        updated_at="2026-07-11T00:00:00+00:00",
    )

    db.init()
    course = db.create_course(name="Information Theory", code="EE123", term="2026")

    assert db.get_note(note["id"])["title"] == "Existing"
    assert course["status"] == "active"
    assert db.list_courses() == [course]
```

```python
def test_document_chunks_keep_location_labels(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    course = db.create_course(name="Networks")
    document = db.insert_source_document(
        course_id=course["id"], title="Lecture 1", source_type="pdf",
        mime_type="application/pdf", managed_path="library/a.pdf",
        origin_url="", external_id="", content_hash="abc",
        status="processing", error_message="",
        imported_at="2026-07-11T00:00:00+00:00",
        source_updated_at="", updated_at="2026-07-11T00:00:00+00:00",
    )
    db.insert_document_chunks(document["id"], [{
        "position": 0, "location_label": "page 3", "heading": "Entropy",
        "content": "Entropy measures uncertainty.",
        "embedding": [1.0, 0.0], "embedding_model": "test-v1",
    }])

    chunks = db.list_document_chunks(document["id"])
    assert chunks[0]["location_label"] == "page 3"
```

- [x] **Step 2: Run tests and confirm the new APIs are missing**

Run:

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_library_service.py -v
```

Expected: FAIL with `AttributeError: 'Database' object has no attribute 'create_course'`.

- [x] **Step 3: Add tables and transactional persistence**

Add `courses`, `source_documents`, and `document_chunks` tables, indexes on
`course_id`, `content_hash`, and `source_document_id`, plus nullable
`notes.course_id` and `notes.source_document_id` migrations. Use parameterized
queries and return hydrated dictionaries.

```python
def create_course(self, *, name: str, code: str = "", term: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with self.connect() as conn:
        cur = conn.execute(
            "INSERT INTO courses (name, code, term, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', ?, ?)",
            (name, code, term, now, now),
        )
    return self.get_course(int(cur.lastrowid))
```

`insert_document_chunks()` must delete existing chunks for the document and
insert replacements in one connection so retries cannot leave mixed versions.

- [x] **Step 4: Run schema and full regression tests**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_library_service.py tests/test_memory_service.py tests/test_api.py -q
```

Expected: new schema tests pass and all existing 21 tests pass.

- [x] **Step 5: Commit Task 1**

```bash
git add app/db.py app/schemas.py tests/test_library_service.py
git commit -m "Add course library schema"
```

---

### Task 2: Document Parsers And Located Chunking

**Files:**
- Create: `app/services/documents.py`
- Create: `tests/test_document_parsers.py`
- Create: `tests/fixtures/sample.md`
- Create: `tests/fixtures/sample.txt`
- Create: `tests/fixtures/sample.pdf`
- Create: `tests/fixtures/sample.docx`
- Create: `tests/fixtures/sample.pptx`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `LocatedText`, `ParsedDocument`, `DocumentChunkInput`, `detect_document_type(filename, mime_type)`, `parse_document(path, document_type)`, and `chunk_located_text(blocks, max_chars=1800, overlap_chars=180)`.
- Consumes: no application service; parser functions accept a local `Path`.

- [x] **Step 1: Add parser dependencies and failing tests**

Add:

```text
pypdf>=5.0.0
python-docx>=1.1.0
python-pptx>=1.0.0
```

Write tests with committed small fixtures:

```python
@pytest.mark.parametrize(
    ("filename", "expected_label", "expected_text"),
    [
        ("sample.md", "Introduction", "local knowledge"),
        ("sample.txt", "text", "plain text"),
        ("sample.pdf", "page 1", "entropy"),
        ("sample.docx", "paragraph 1", "document paragraph"),
        ("sample.pptx", "slide 1", "presentation slide"),
    ],
)
def test_parse_document_preserves_locations(filename, expected_label, expected_text):
    parsed = parse_document(FIXTURES / filename, detect_document_type(filename, ""))
    assert expected_text in " ".join(block.content.lower() for block in parsed.blocks)
    assert any(expected_label.lower() in block.location_label.lower() for block in parsed.blocks)
```

```python
def test_image_is_registered_for_future_ocr():
    assert detect_document_type("board.png", "image/png") == "image"
    with pytest.raises(OcrRequiredError):
        parse_document(FIXTURES / "board.png", "image")
```

```python
def test_chunking_keeps_source_location():
    blocks = [LocatedText("A" * 1200, "page 2", "Entropy")]
    chunks = chunk_located_text(blocks, max_chars=500, overlap_chars=50)
    assert len(chunks) >= 3
    assert {chunk.location_label for chunk in chunks} == {"page 2"}
```

- [x] **Step 2: Run parser tests and verify import failure**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_document_parsers.py -v
```

Expected: FAIL because `app.services.documents` does not exist.

- [x] **Step 3: Implement parser dispatch and chunking**

```python
@dataclass(frozen=True)
class LocatedText:
    content: str
    location_label: str
    heading: str = ""


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    blocks: list[LocatedText]


@dataclass(frozen=True)
class DocumentChunkInput:
    position: int
    location_label: str
    heading: str
    content: str
```

Use `pypdf.PdfReader`, `docx.Document`, and `pptx.Presentation`. Markdown
headings update the current heading and become citation labels. Normalize
whitespace but preserve paragraph boundaries. Define `DocumentParseError` as
the base exception, with `UnsupportedDocumentError`, `EmptyDocumentError`, and
`OcrRequiredError` subclasses carrying user-facing messages.

- [x] **Step 4: Run parser and full tests**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_document_parsers.py -q
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest -q
```

Expected: parser tests pass; full suite remains green.

- [x] **Step 5: Commit Task 2**

```bash
git add requirements.txt app/services/documents.py tests/test_document_parsers.py tests/fixtures
git commit -m "Add located document parsers"
```

---

### Task 3: Managed Library Import Service

**Files:**
- Create: `app/services/library.py`
- Modify: `app/settings.py:6-43`
- Modify: `.env.example`
- Test: `tests/test_library_service.py`

**Interfaces:**
- Consumes: `Database`, `EmbeddingProvider`, `parse_document()`, and `chunk_located_text()`.
- Produces: `LibraryService.create_course(name: str, code: str = "", term: str = "") -> dict`, `import_file(course_id: int, filename: str, mime_type: str, stream: BinaryIO) -> dict`, `retry_document(document_id: int) -> dict`, `list_documents(course_id: int | None = None) -> list[dict]`, and `get_document(document_id: int) -> dict`.

- [x] **Step 1: Write failing import-service tests**

```python
def test_import_markdown_copies_file_and_embeds_cited_chunks(tmp_path):
    service = make_library_service(tmp_path)
    course = service.create_course(name="Information Theory")
    imported = service.import_file(
        course_id=course["id"], filename="lecture.md",
        mime_type="text/markdown", stream=io.BytesIO(b"# Entropy\nUncertainty."),
    )

    assert imported["status"] == "ready"
    assert Path(imported["managed_path"]).is_file()
    assert imported["chunks"][0]["location_label"] == "Entropy"
    assert imported["chunks"][0]["embedding"] is not None
```

```python
def test_duplicate_import_returns_existing_document(tmp_path):
    service = make_library_service(tmp_path)
    course = service.create_course(name="Networks")
    first = service.import_file(course["id"], "a.txt", "text/plain", io.BytesIO(b"same"))
    second = service.import_file(course["id"], "b.txt", "text/plain", io.BytesIO(b"same"))
    assert second["id"] == first["id"]
    assert second["duplicate"] is True
```

```python
def test_failed_parse_keeps_original_and_can_retry(tmp_path):
    service = make_library_service(tmp_path)
    course = service.create_course(name="Systems")
    result = service.import_file(course["id"], "broken.pdf", "application/pdf", io.BytesIO(b"bad"))
    assert result["status"] == "failed"
    assert Path(result["managed_path"]).exists()
    assert result["error_message"]
```

- [x] **Step 2: Run focused tests and verify the missing service**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_library_service.py -v
```

Expected: FAIL importing `LibraryService`.

- [x] **Step 3: Add settings and minimal import orchestration**

```python
@dataclass(frozen=True)
class Settings:
    # existing fields remain unchanged
    library_dir: Path
    max_upload_bytes: int
```

```python
class LibraryService:
    def __init__(self, db, embedder, library_dir: Path, max_upload_bytes: int):
        self.db = db
        self.embedder = embedder
        self.library_dir = library_dir
        self.max_upload_bytes = max_upload_bytes

    def import_file(
        self, course_id: int, filename: str, mime_type: str, stream: BinaryIO
    ) -> dict:
        self.db.get_course(course_id)
        document_type = detect_document_type(filename, mime_type)
        safe_name = sanitize_filename(filename)
        staged_path, content_hash = self._stage_stream(stream)
        existing = self.db.find_source_document_by_hash(content_hash)
        if existing:
            staged_path.unlink(missing_ok=True)
            return {**existing, "duplicate": True}

        managed_path = self.library_dir / f"{content_hash[:16]}-{safe_name}"
        staged_path.replace(managed_path)
        now = datetime.now(timezone.utc).isoformat()
        document = self.db.insert_source_document(
            course_id=course_id,
            title=safe_name,
            source_type=document_type,
            mime_type=mime_type,
            managed_path=str(managed_path),
            origin_url="",
            external_id="",
            content_hash=content_hash,
            status="processing",
            error_message="",
            imported_at=now,
            source_updated_at="",
            updated_at=now,
        )
        return self._parse_and_index(document)

    def _stage_stream(self, stream: BinaryIO) -> tuple[Path, str]:
        digest = hashlib.sha256()
        size = 0
        self.library_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=self.library_dir, prefix=".import-", delete=False
        ) as target:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > self.max_upload_bytes:
                    Path(target.name).unlink(missing_ok=True)
                    raise UploadTooLargeError(self.max_upload_bytes)
                digest.update(chunk)
                target.write(chunk)
            return Path(target.name), digest.hexdigest()

    def _parse_and_index(self, document: dict) -> dict:
        try:
            parsed = parse_document(
                Path(document["managed_path"]), document["source_type"]
            )
            chunks = chunk_located_text(parsed.blocks)
            records = [
                {
                    "position": item.position,
                    "location_label": item.location_label,
                    "heading": item.heading,
                    "content": item.content,
                    "embedding": self.embedder.embed(item.content),
                    "embedding_model": self.embedder.version,
                }
                for item in chunks
            ]
            self.db.insert_document_chunks(document["id"], records)
            return self.db.update_source_document(
                document["id"], status="ready", error_message=""
            )
        except OcrRequiredError as exc:
            return self.db.update_source_document(
                document["id"], status="ocr_required", error_message=str(exc)
            )
        except DocumentParseError as exc:
            return self.db.update_source_document(
                document["id"], status="failed", error_message=str(exc)
            )
```

Implement streaming size enforcement, SHA-256, `Path(filename).name` plus safe
character normalization, atomic move from a temporary file, status transitions,
chunk embedding, and duplicate lookup. `OcrRequiredError` maps to
`ocr_required`; other parser exceptions map to `failed`. Define
`UploadTooLargeError` in `library.py`. `sanitize_filename()` must first apply
`Path(filename).name`, replace characters outside `[A-Za-z0-9._ -]` with `_`,
trim leading dots and whitespace, and fall back to `document` when empty.

Add to `.env.example`:

```text
MEMORY_LIBRARY_DIR=./data/library
MEMORY_MAX_UPLOAD_MB=100
```

- [x] **Step 4: Verify library service and regression suite**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_library_service.py -q
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest -q
```

Expected: managed import tests and all previous tests pass.

- [x] **Step 5: Commit Task 3**

```bash
git add app/services/library.py app/settings.py .env.example tests/test_library_service.py
git commit -m "Add managed document imports"
```

---

### Task 4: Course And Library APIs

**Files:**
- Modify: `app/main.py:22-213`
- Modify: `app/schemas.py:4-31`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `LibraryService` from Task 3.
- Produces: `GET/POST /api/courses`, `PUT /api/courses/{course_id}`, `GET /api/library/documents`, `POST /api/library/import`, `GET /api/library/documents/{document_id}`, and `POST /api/library/documents/{document_id}/retry`.

- [x] **Step 1: Write failing API tests**

```python
def test_create_course_and_import_markdown_through_api(tmp_path, monkeypatch):
    configure_local_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())
    course = client.post("/api/courses", json={"name": "Networks", "code": "CN"})
    assert course.status_code == 201

    imported = client.post(
        "/api/library/import",
        data={"course_id": str(course.json()["id"])},
        files={"file": ("lecture.md", b"# Routing\nDistance vector", "text/markdown")},
    )
    assert imported.status_code == 201
    assert imported.json()["status"] == "ready"
```

```python
def test_library_api_reports_duplicate_and_missing_course(tmp_path, monkeypatch):
    configure_local_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())
    missing = client.post(
        "/api/library/import", data={"course_id": "999"},
        files={"file": ("a.txt", b"text", "text/plain")},
    )
    assert missing.status_code == 404
```

- [x] **Step 2: Run focused tests and verify 404/route absence**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_api.py -k "course or library" -v
```

Expected: FAIL because the endpoints do not exist.

- [x] **Step 3: Wire services and implement API contracts**

```python
class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(default="", max_length=40)
    term: str = Field(default="", max_length=80)


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=40)
    term: str | None = Field(default=None, max_length=80)
    status: Literal["active", "archived"] | None = None
```

Build one `LibraryService` from the same `Database` and embedding provider used
by `MemoryService`, and store it on `app.state.library_service`. Use FastAPI
`UploadFile` and `Form`. Map size/type errors to 400, missing course/document to
404, and successful duplicate imports to 200 with `duplicate: true`.

- [x] **Step 4: Run API and full tests**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_api.py -q
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest -q
```

Expected: all API contracts and previous behavior pass.

- [x] **Step 5: Commit Task 4**

```bash
git add app/main.py app/schemas.py tests/test_api.py
git commit -m "Expose course library APIs"
```

---

### Task 5: Unified Cited Retrieval

**Files:**
- Create: `app/services/retrieval.py`
- Modify: `app/services/memory.py:11-188`
- Modify: `app/db.py:426-456`
- Modify: `app/main.py:139-150`
- Test: `tests/test_memory_service.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: note rows, hydrated document chunks, `EmbeddingProvider`, and existing AI client.
- Produces: `UnifiedRetrievalService.search(query: str, limit: int = 10, *, tag: str | None = None, course_id: int | None = None, source_document_id: int | None = None) -> list[dict]` and `MemoryService.ask_question(question: str, limit: int = 5, *, course_id: int | None = None, source_document_id: int | None = None) -> dict`.

- [x] **Step 1: Write failing unified-search tests**

```python
def test_unified_search_returns_document_chunk_with_citation(tmp_path):
    memory, library = make_services(tmp_path)
    course = library.create_course(name="Information Theory")
    library.import_file(
        course["id"], "entropy.md", "text/markdown",
        io.BytesIO(b"# Entropy\nEntropy measures uncertainty."),
    )

    results = memory.search_notes("uncertainty", course_id=course["id"])
    assert results[0]["kind"] == "document"
    assert results[0]["source_title"] == "entropy.md"
    assert results[0]["location_label"] == "Entropy"
```

```python
def test_question_sources_include_document_location(tmp_path):
    memory, library = make_services(tmp_path)
    course = library.create_course(name="Networks")
    library.import_file(course["id"], "routing.md", "text/markdown", io.BytesIO(b"# Bellman-Ford\nRouting uses relaxation."))
    answer = memory.ask_question("How does routing update paths?", course_id=course["id"])
    assert answer["sources"][0]["location_label"] == "Bellman-Ford"
```

- [x] **Step 2: Run focused tests and verify signature failure**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_memory_service.py -k "unified or location" -v
```

Expected: FAIL because `search_notes()` does not accept `course_id` and document chunks are not searched.

- [x] **Step 3: Implement unified ranking and preserve note compatibility**

```python
class UnifiedRetrievalService:
    def search(
        self, query: str, limit: int = 10, *, tag: str | None = None,
        course_id: int | None = None, source_document_id: int | None = None,
    ) -> list[dict]:
        clean_query = query.strip()
        query_embedding = self.embedder.embed(clean_query)
        query_tokens = set(tokenize(clean_query))
        records = self._note_records(tag=tag, course_id=course_id)
        records.extend(
            self._document_records(
                course_id=course_id, source_document_id=source_document_id
            )
        )
        scored = []
        for record in records:
            vector_score = cosine_similarity(
                query_embedding, record.get("embedding")
            )
            record_tokens = set(tokenize(record["content"]))
            keyword_score = (
                len(query_tokens & record_tokens) / len(query_tokens)
                if query_tokens else 0.0
            )
            result = {
                key: value for key, value in record.items() if key != "embedding"
            }
            result["score"] = round(
                (0.75 * vector_score) + (0.25 * keyword_score), 6
            )
            scored.append(result)
        scored.sort(
            key=lambda item: (item["score"], item.get("updated_at", "")),
            reverse=True,
        )
        return scored[:limit]
```

Return note results with `kind: "note"` and document results with
`kind: "document"`, `source_document_id`, `source_title`, `course_id`, and
`location_label`. Keep `title`, `content`, `summary`, and `score` on both shapes
so the existing AI client remains compatible. `_note_records()` adapts
`Database.list_notes()` rows to that shape and preserves note embeddings;
`_document_records()` adapts a new
`Database.list_searchable_document_chunks(course_id, source_document_id)` join
across chunks, documents, and courses. Add course/source query parameters to
`/api/search` and `AskRequest`.

- [x] **Step 4: Verify ranking, API response, and regressions**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_memory_service.py tests/test_api.py -q
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest -q
```

Expected: document citations appear and old note searches still rank correctly.

- [ ] **Step 5: Commit Task 5**

```bash
git add app/services/retrieval.py app/services/memory.py app/db.py app/main.py tests/test_memory_service.py tests/test_api.py
git commit -m "Add cited document retrieval"
```

---

### Task 6: Library And Course UI

**Files:**
- Modify: `app/templates/index.html:21-158`
- Modify: `app/static/app.js:1-620`
- Modify: `app/static/styles.css:1-795`

**Interfaces:**
- Consumes: course/library APIs from Task 4 and course-aware search from Task 5.
- Produces: usable Library panel, course selectors, batch import feedback, document status list, and course filtering.

- [x] **Step 1: Add API shell assertions before UI code**

Extend `test_homepage_renders_app_shell`:

```python
assert 'id="library"' in response.text
assert 'id="courseSelect"' in response.text
assert 'id="libraryImportForm"' in response.text
assert 'id="documentList"' in response.text
```

- [x] **Step 2: Run shell test and verify missing controls**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_api.py::test_homepage_renders_app_shell -v
```

Expected: FAIL on missing `id="library"`.

- [x] **Step 3: Add accessible, stable Library markup**

```html
<section class="panel library-panel" id="library">
  <div class="section-heading">
    <h2>Course library</h2>
    <span id="libraryStatus">Local files</span>
  </div>
  <form id="courseForm" class="course-form">
    <input name="name" aria-label="Course name" required maxlength="120">
    <input name="code" aria-label="Course code" maxlength="40">
    <button type="submit">Add course</button>
  </form>
  <form id="libraryImportForm" class="import-form">
    <select id="courseSelect" name="course_id" aria-label="Import course" required></select>
    <input name="files" type="file" multiple accept=".md,.txt,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp">
    <button type="submit">Import files</button>
  </form>
  <div id="documentList" class="document-list"></div>
</section>
```

Add a course selector to note creation and search/ask filters without removing
existing tag filtering.

- [x] **Step 4: Add JavaScript data flow and stable layout**

Implement `loadCourses()`, `loadDocuments()`, `renderDocument()`, and sequential
batch upload so one failed file does not stop the batch. Display `ready`,
`partial`, `ocr_required`, and `failed` states with text plus color, never color
alone. Keep controls within fixed responsive grid tracks and verify long file
names use wrapping or ellipsis without resizing panels.

- [x] **Step 5: Run shell and full tests**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_api.py::test_homepage_renders_app_shell -v
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest -q
```

Expected: shell assertions and full suite pass.

- [ ] **Step 6: Run rendered browser QA**

Start with an isolated database:

```bash
MEMORY_DB_PATH=/private/tmp/local-memory-library-qa.db MEMORY_AI_MODE=offline /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Verify: app identity, no blank/error overlay, no console warnings, create course,
import Markdown, status becomes ready, search returns the cited heading, and
desktop `1280x800` plus mobile `390x900` have no horizontal overflow.

- [ ] **Step 7: Commit Task 6**

```bash
git add app/templates/index.html app/static/app.js app/static/styles.css tests/test_api.py
git commit -m "Add course library interface"
```

Execution note (2026-07-11): Steps 1-5 are verified. Step 6 could not run
because the environment rejected local port binding after the Codex usage limit
was reached. Step 7 is also pending because Git write approval was unavailable.

---

### Task 7: Documentation, Progress, And Release Verification

**Files:**
- Modify: `README.md`
- Modify: `project-review.md`
- Modify: `docs/superpowers/plans/2026-07-11-course-library-import.md`

**Interfaces:**
- Consumes: verified behavior from Tasks 1-6.
- Produces: accurate setup, supported formats, limits, progress, and evidence.

- [x] **Step 1: Update user documentation**

Document:

- course creation and archive behavior;
- supported formats and `ocr_required` meaning;
- managed library location and upload-size setting;
- duplicate behavior and retry flow;
- cited document search and ask filters;
- exact dependency installation and test commands.

- [x] **Step 2: Update project progress only from verified evidence**

Mark only completed 5A checklist items in `project-review.md`. Record the fresh
test count, browser viewports, imported fixture formats, and remaining 5B work.
Do not mark OCR, web capture, Notion, cards, ChatGPT Bridge, or VPS complete.

- [x] **Step 3: Run final verification**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest -q
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m compileall -q app desktop.py
git diff --check
git status -sb
```

Expected: all tests pass, compilation exits 0, diff check is empty, and only
intentional documentation/plan status changes remain before the final commit.

- [ ] **Step 4: Commit verified documentation**

```bash
git add README.md project-review.md docs/superpowers/plans/2026-07-11-course-library-import.md
git commit -m "Document course library upgrade"
```

- [ ] **Step 5: Push and update the GitHub review branch**

```bash
git push -u origin codex/learning-workflow-upgrade
```

Open or update a draft PR targeting `main` with the verified test and browser QA
results. Do not merge without user review.

Execution note (2026-07-11): pytest (`45 passed`), Python compilation,
JavaScript syntax checking, and `git diff --check` passed. Documentation commit,
push, and browser QA remain pending for the approval/usage limit described
above.
