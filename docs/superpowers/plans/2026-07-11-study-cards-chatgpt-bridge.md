# Study Cards And ChatGPT Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple spaced-repetition cards from notes, require candidate approval, and add cited Markdown exchange with ChatGPT without an OpenAI API dependency.

**Architecture:** SQLite owns card state and scheduling. `StudyService` manages candidates, migration, approval, queueing, and grading; `StudyBridgeService` produces and consumes a constrained Markdown format. Existing FastAPI and vanilla JavaScript surfaces call these local services.

**Tech Stack:** Python 3.13, FastAPI, SQLite, Pydantic, pytest, HTML/CSS/JavaScript.

## Global Constraints

- All data stays local; no direct OpenAI API or automatic ChatGPT upload.
- Existing review history must survive migration.
- New content is never active until the user approves its candidate.
- Study exports include course, source title, and location labels.
- Tests run without Ollama, Notion, network, or OCR dependencies.

---

### Task 1: Study Card Schema And Migration

**Files:**
- Modify: `app/db.py`
- Create: `app/services/study.py`
- Create: `tests/test_study_service.py`

**Interfaces:**
- Produces `Database.insert_study_card()`, `list_study_cards()`, `get_study_card()`, `update_study_card()`, `list_due_study_cards()`, and `StudyService` candidate/queue methods.

- [x] **Step 1: Write failing migration tests**

Create a legacy note plus `review_states` row, rerun `Database.init()`, and assert one `active` card preserves `due_at`, `interval_days`, `ease`, `reps`, and `last_grade`. Assert repeated initialization is idempotent.

- [x] **Step 2: Run the focused test**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/test_study_service.py -v
```

Expected: failure because `study_cards` and `StudyService` do not exist.

- [x] **Step 3: Implement schema and migration**

Create `study_cards` with `candidate|active|suspended|rejected` state, nullable note/document/chunk references, scheduling fields, timestamps, and a unique nullable `note_id`. During `init()`, insert one active card for every existing note not already represented; left join `review_states` to preserve history and use the note timestamp as the default due date.

- [x] **Step 4: Implement `StudyService`**

Provide:

```python
list_candidates(course_id: int | None = None, limit: int = 100) -> list[dict]
approve(card_id: int, prompt: str | None = None, answer: str | None = None) -> dict
reject(card_id: int) -> dict
suspend(card_id: int) -> dict
queue(limit: int = 20, course_id: int | None = None) -> list[dict]
grade(card_id: int, grade: str) -> dict
```

Approval may edit prompt/answer and sets `due_at` to now. Grading retains the current Again/Good/Easy schedule.

- [x] **Step 5: Verify and commit**

Run focused and full tests, then commit `Add independent study cards`.

---

### Task 2: Candidate Generation For New Content

**Files:**
- Modify: `app/services/memory.py`
- Modify: `app/services/library.py`
- Modify: `tests/test_memory_service.py`
- Modify: `tests/test_library_service.py`

**Interfaces:**
- New notes create one note-backed candidate.
- Successfully indexed documents create idempotent chunk-backed candidates.

- [x] **Step 1: Write failing candidate tests**

Assert a newly created note is absent from the active queue and appears in candidates. Assert a Markdown document creates candidates with `source_label` equal to its heading and retrying does not duplicate them.

- [x] **Step 2: Run tests and observe the old automatic queue behavior**

Expected: new notes appear directly in the old queue and documents create no candidates.

- [x] **Step 3: Add deterministic candidates**

For a note, use its title as prompt and full content as answer. For each document chunk, use `Review <source title> at <location label>` as prompt, chunk content as answer, and preserve the source label. Replace a document's non-reviewed candidates transactionally after successful re-indexing.

- [x] **Step 4: Verify and commit**

Run full tests and commit `Generate review card candidates`.

---

### Task 3: Card API And Study UI

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/main.py`
- Modify: `app/templates/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Modify: `tests/test_api.py`

**Interfaces:**
- `GET /api/study/candidates`
- `PUT /api/study/cards/{card_id}/approve`
- `POST /api/study/cards/{card_id}/reject`
- `POST /api/study/cards/{card_id}/suspend`
- `GET /api/study/queue`
- `POST /api/study/cards/{card_id}/grade`

- [x] **Step 1: Write failing API and shell tests**

Create a note, assert it appears only in candidates, approve it with edited prompt, grade it, and suspend it. Assert candidate inbox controls are present in rendered HTML.

- [x] **Step 2: Implement API contracts**

Map missing cards to 404, invalid state transitions/grades to 400, and return card objects without embeddings.

- [x] **Step 3: Replace the old note queue UI**

Add a candidate inbox with Edit/Approve/Reject and show active card prompt, answer, citation, and Again/Good/Easy controls. Candidate approval must refresh both inbox and queue.

- [x] **Step 4: Verify and commit**

Run API and full tests, then commit `Add candidate approval workflow`.

---

### Task 4: Cited Study Pack Export And Markdown Import

**Files:**
- Create: `app/services/study_bridge.py`
- Modify: `app/main.py`
- Modify: `app/templates/index.html`
- Modify: `app/static/app.js`
- Modify: `tests/test_study_bridge.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- `StudyBridgeService.export_pack(course_id: int) -> str`
- `StudyBridgeService.import_result(course_id: int, markdown: str) -> dict`
- `GET /api/study-pack?course_id=<id>`
- `POST /api/study-pack/import` multipart fields `course_id` and `file`

- [x] **Step 1: Write failing bridge tests**

Export must include project instructions, course metadata, note/document content, and citations. Import must accept repeated `## Reviewed Note` and `## Card Candidate` sections, create local notes/candidates, reject malformed/empty input, and never call a network API.

- [x] **Step 2: Implement the constrained Markdown format**

Use these exact sections:

```markdown
# Local Memory Study Result
## Reviewed Note
Title: Example
Source: ChatGPT study result
### Content
Reviewed content
## Card Candidate
Prompt: Question
Source: lecture.pdf · page 2
### Answer
Answer text
```

Parse headings and field prefixes line by line; do not execute HTML or interpret paths/URLs. Imported notes and cards remain local and cards remain candidates.

- [x] **Step 3: Add API and UI controls**

Provide course-scoped Study Pack download and `.md` import controls. Display imported note/card counts and refresh candidates.

- [x] **Step 4: Verify and commit**

Run bridge, API, and full tests, then commit `Add ChatGPT study pack bridge`.

---

### Task 5: Documentation, Browser QA, And Publish

**Files:**
- Modify: `README.md`
- Modify: `project-review.md`
- Modify: this plan

- [x] **Step 1: Update documentation from verified behavior**

Document candidate states, migration behavior, Study Pack workflow, Markdown import format, privacy boundary, and unsupported automatic ChatGPT upload.

- [x] **Step 2: Run final verification**

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest -q
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m compileall -q app desktop.py
node --check app/static/app.js
git diff --check
```

- [x] **Step 3: Run browser QA**

At desktop `1280x800` and mobile `390x900`, verify: create note -> candidate only -> edit/approve -> active queue -> reveal/grade; export Study Pack; import structured result; no console errors or horizontal overflow.

- [x] **Step 4: Commit and push**

Commit verified docs, then push `codex/stage-5c-study-bridge` to `origin` (`https://github.com/khalilpong/Local-AI-learning-Manager.git`). Do not merge to `main` without review.
