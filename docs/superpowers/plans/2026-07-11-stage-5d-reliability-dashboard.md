# Stage 5D Reliability And Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the local-first learning workflow with versioned migrations, safe local backup/restore, diagnostics, and an actionable course dashboard.

**Architecture:** SQLite remains authoritative. Migrations are numbered and savepoint-protected; backups use SQLite's online backup API plus a validated ZIP; diagnostics expose capability booleans without secrets; dashboard metrics are computed from existing course, document, note, and study-card data.

**Tech Stack:** Python 3.13 standard library, FastAPI, SQLite, pytest, vanilla HTML/CSS/JavaScript.

## Global Constraints

- No VPS, public listener, analytics, or remote backup.
- Restore rejects ZIP path traversal and invalid manifests before replacing data.
- Diagnostics never return tokens, environment values, or note content.
- Every migration is idempotent, numbered, and rolled back on failure.

---

### Task 1: Versioned Transactional Migrations

**Files:** `app/db.py`, `tests/test_database_migrations.py`

- [x] Write tests asserting fresh and upgraded databases record schema versions, repeated init is idempotent, and a failing migration rolls back all statements in that version.
- [x] Add `schema_migrations(version, name, applied_at)` and `Database.schema_version()`.
- [x] Run each numbered migration inside a SQLite savepoint and record it only after success.
- [x] Run migration/full tests and commit `Add versioned database migrations`.

### Task 2: Local Backup And Restore

**Files:** create `app/services/backup.py`, modify `app/main.py`, `app/templates/index.html`, `app/static/app.js`, test `tests/test_backup.py`, `tests/test_api.py`.

- [x] Test backup manifest/database/library inclusion, successful round trip, corrupt archive rejection, and `../` traversal rejection.
- [x] Implement `BackupService.create_backup(target)`, `inspect_backup(path)`, and `restore_backup(path)` using staging directories and SQLite backup.
- [x] Add download/upload APIs and local Settings controls with explicit confirmation before restore.
- [x] Verify and commit `Add local backup and restore`.

### Task 3: Privacy-Safe Diagnostics

**Files:** create `app/services/diagnostics.py`, modify `app/main.py`, `app/templates/index.html`, `app/static/app.js`, test `tests/test_diagnostics.py`, `tests/test_api.py`.

- [x] Test parser availability, database/library write checks, OCR/embedding/Ollama/Notion status, free bytes, and absence of token/path-sensitive values.
- [x] Add `GET /api/diagnostics` and a compact status list with Ready/Unavailable/Action needed text.
- [x] Verify and commit `Add local diagnostics`.

### Task 4: Course Learning Dashboard

**Files:** create `app/services/dashboard.py`, modify `app/db.py`, `app/main.py`, `app/templates/index.html`, `app/static/app.js`, `app/static/styles.css`, test `tests/test_dashboard.py`, `tests/test_api.py`.

- [x] Test course counts, unresolved imports, candidate/active/due cards, weak cards, and seven-day review load.
- [x] Add `GET /api/courses/{course_id}/dashboard` and a course selector dashboard with metrics, weak prompts, errors, and daily review load bars.
- [x] Verify desktop/mobile layout and commit `Add course learning dashboard`.

### Task 5: Release Verification And Publish

**Files:** `README.md`, `project-review.md`, this plan.

- [x] Run all tests, compileall, JavaScript syntax, diff checks, backup round trip, and browser QA at `1280x800` and `390x900`.
- [x] Update verified progress and residual limitations only.
- [ ] Push `codex/stage-5d-reliability-dashboard` to `khalilpong/Local-AI-learning-Manager` without merging `main`.
