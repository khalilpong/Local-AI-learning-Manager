# Personal Memory App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable local-first AI personal memory app.

**Architecture:** FastAPI exposes local web pages and JSON APIs. SQLite stores
notes, tags, embeddings, and reviews. Ollama powers AI behavior when available,
with local fallback behavior so core workflows keep running.

**Tech Stack:** Python, FastAPI, SQLite, Jinja2, vanilla CSS/JS, Ollama.

## Global Constraints

- Bind locally by default using `127.0.0.1`.
- Store all user data in local SQLite.
- Use local embeddings for semantic search.
- Use Ollama for summarization, tagging, QA, and weekly review when available.
- Keep the structure ready for a later Tauri/Electron desktop shell.

---

### Task 1: Storage And Services

**Files:**
- Create: `app/db.py`
- Create: `app/services/embeddings.py`
- Create: `app/services/ollama.py`
- Create: `app/services/memory.py`
- Test: `tests/test_memory_service.py`

**Interfaces:**
- Produces: `Database.init()`, `HashEmbeddingProvider.embed(text)`,
  `MemoryService.create_note()`, `search_notes()`, `ask_question()`,
  `generate_weekly_review()`.

- [x] Write failing service tests.
- [x] Verify tests fail because `app` does not exist.
- [ ] Implement storage and services.
- [ ] Run service tests until green.

### Task 2: FastAPI And UI

**Files:**
- Create: `app/main.py`
- Create: `app/schemas.py`
- Create: `app/templates/*.html`
- Create: `app/static/styles.css`
- Create: `app/static/app.js`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `MemoryService`.
- Produces: `/api/health`, `/api/notes`, `/api/search`, `/api/ask`,
  `/api/reviews/weekly`, and matching web pages.

- [x] Write failing API tests.
- [ ] Implement API routes and web UI.
- [ ] Run API tests until green.

### Task 3: Documentation And Verification

**Files:**
- Create: `README.md`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `.gitignore`

**Interfaces:**
- Produces: install, run, test, Ollama, privacy, and desktop migration docs.

- [ ] Verify tests.
- [ ] Start local server.
- [ ] Smoke-test primary UI.
