# Learning Workflow Upgrade Design

## Goal

Upgrade Local Memory from a note-focused MVP into the local knowledge and
review layer of a practical study workflow built around Notion and ChatGPT.
The application must ingest common course materials, keep authoritative local
copies, provide cited retrieval, and let the user decide what becomes a review
card.

VPS deployment and remote backup are explicitly deferred. This upgrade remains
local-first and must not require a cloud server.

## Product Responsibilities

- Notion remains the primary place for course planning, tasks, and polished
  human-edited notes.
- ChatGPT remains the interactive tutor for explanations, guided questions,
  practice, and synthesis.
- Local Memory stores original learning materials, indexes approved knowledge,
  runs retrieval and spaced repetition, and prepares portable study packs.
- AI chat transcripts are not authoritative knowledge. Only reviewed outputs
  imported by the user become notes or cards.

## Scope Decomposition

The full upgrade is split into independently deliverable increments. The first
implementation plan will cover Increment A only. Later increments receive their
own implementation plans after A is verified.

### Increment A: Course Library And Local Import

- Add courses with name, optional code, term, and active/archived status.
- Add a managed local document library under the configured data directory.
- Import Markdown, plain text, PDF, DOCX, and PPTX. Register common image
  files in the managed library and mark them `ocr_required` until Increment B
  provides an OCR backend.
- Extract text while preserving source location metadata such as PDF page,
  PowerPoint slide, Markdown heading, or document paragraph range.
- Detect duplicates by SHA-256 content hash.
- Split extracted text into bounded chunks, embed each chunk locally, and make
  notes plus documents available to unified search and question answering.
- Add import statuses: pending, processing, ready, partial, `ocr_required`, and
  failed.
- Keep a failed import visible with an actionable error and retry command.
- Add course and source filters to the library, search, and question-answering
  views.

### Increment B: Capture Sources And Notion Sync

- Add screenshot OCR through a provider interface. Prefer macOS Vision on the
  current machine and allow Tesseract as an optional cross-platform backend.
- If no OCR provider is available, preserve the image and report `ocr_required`
  instead of silently producing empty text.
- Add public web-page capture with title, canonical URL, retrieval timestamp,
  readable text, and source attribution.
- Permit only HTTP(S) URLs and reject loopback, private-network, and local-file
  targets.
- Add one-way, read-only Notion synchronization for explicitly shared pages or
  databases.
- Store the Notion token only in `.env`; never expose it in API responses, logs,
  exports, or Git.
- Treat Notion deletions as local archive events rather than immediate local
  data deletion.
- Make synchronization idempotent using Notion page ID and last-edited time.

### Increment C: Review Candidates And ChatGPT Bridge

- Decouple study cards from notes. A card has a prompt, answer, course, source
  reference, state, and spaced-repetition schedule.
- New notes and imported documents do not automatically become active cards.
- AI or deterministic rules may create card candidates, but the user must
  approve, edit, or reject each candidate.
- Preserve the existing review history by migrating each currently reviewable
  note to one active card.
- Export selected courses, documents, notes, and weak areas as a cited
  `study-pack.md` suitable for uploading to a ChatGPT Project or Study Mode.
- Export reusable ChatGPT project instructions with the study pack.
- Import a structured Markdown study result containing reviewed notes, mistakes,
  and card candidates. Do not require the OpenAI API in this increment.

### Increment D: Study Dashboard And Reliability

- Add a course dashboard with due cards, recent imports, unresolved import
  errors, weak topics, and upcoming review load.
- Add backup and restore to a local archive file before any remote backup work.
- Add database schema versioning and transactional migrations.
- Add a diagnostics view that reports parser, OCR, embedding, Ollama, Notion,
  and storage availability without revealing secrets.

## Data Model

### `courses`

- `id`, `name`, `code`, `term`, `status`, `created_at`, `updated_at`

### `source_documents`

- `id`, `course_id`, `title`, `source_type`, `mime_type`
- `managed_path`, `origin_url`, `external_id`
- `content_hash`, `status`, `error_message`
- `imported_at`, `source_updated_at`, `updated_at`

The original file is copied into a managed local path. Database rows never
depend on a temporary upload path.

### `document_chunks`

- `id`, `source_document_id`, `position`, `location_label`
- `heading`, `content`, `embedding_json`, `embedding_model`

`location_label` stores a human-readable citation such as `page 12`, `slide 8`,
or `Heading > Subheading`.

### Existing `notes`

- Add nullable `course_id` and `source_document_id` relationships.
- Existing notes remain valid and are assigned to an uncategorized view until
  the user moves them.

### `study_cards`

- `id`, `course_id`, `note_id`, `source_document_id`
- `prompt`, `answer`, `source_label`, `state`
- `due_at`, `interval_days`, `ease`, `reps`, `last_grade`, `updated_at`

Card state is one of `candidate`, `active`, `suspended`, or `rejected`.

## Import Pipeline

1. Validate extension, size, and file name.
2. Stream the upload to a temporary file while calculating SHA-256.
3. Reject or link an existing duplicate.
4. Move the file into the managed local library.
5. Create a `source_documents` row in `processing` state.
6. Select a parser by MIME type and extract located text blocks.
7. Normalize and chunk the text without losing location labels.
8. Generate local embeddings and persist chunks transactionally.
9. Mark the document `ready`, `partial`, `ocr_required`, or `failed`.
10. Refresh search, course statistics, and diagnostics.

One failed file must not roll back other files in a batch.

## Retrieval And Citations

Search and question answering use a unified corpus of notes and document
chunks. Ranking keeps the current hybrid approach: local embedding similarity,
keyword overlap, and FTS when available.

Results must identify the course, source title, and location label. Answers must
return source references separately from generated Markdown so the UI can open
the matching local document detail.

## UI Structure

- `Library`: courses, source documents, import status, retry, and archive.
- `Notes`: existing note capture and editing, now with course assignment.
- `Search`: unified note/document search with course and source filters.
- `Ask`: cited answers over selected courses or documents.
- `Study`: candidate inbox plus active spaced-repetition queue.
- `Review`: weekly learning review and weak-topic summary.
- `Settings`: parser, OCR, embedding, Ollama, Notion, and storage diagnostics.

The UI remains a restrained desktop productivity surface. Existing workflows
continue to work while new library features are introduced.

## Error Handling And Privacy

- Imports use explicit status and error messages; empty extraction is never
  reported as success.
- Parser and OCR failures preserve the original local file for retry.
- Notion and web failures do not block local notes, search, or review.
- Notion access is read-only and limited to pages explicitly shared with the
  integration.
- Uploaded file names are sanitized and managed paths cannot escape the data
  directory.
- Configurable file-size limits prevent accidental memory exhaustion.
- No VPS, public listener, analytics, or automatic upload to ChatGPT is added.

## Testing Strategy

- Parser unit tests use small fixtures for Markdown, TXT, PDF, DOCX, and PPTX.
- Import service tests cover deduplication, chunk citations, partial extraction,
  retries, and cleanup after failures.
- Database migration tests start from the existing schema and preserve notes,
  tags, embeddings, and review history.
- Notion tests use a fake client and verify read-only, idempotent synchronization.
- Web capture tests cover unsupported schemes and private-network rejection.
- Card tests cover candidate approval, migration, grading, suspension, and
  deletion behavior.
- API tests cover upload, course filters, document detail, unified search,
  study-pack export, and structured result import.
- Browser QA covers desktop and mobile layouts, batch import status, candidate
  approval, course filtering, and primary keyboard workflows.

Tests must run without Ollama, Notion, network access, or an OCR executable.

## Acceptance Criteria

- Existing notes and all current 21 tests remain functional after migration.
- A user can create a course and import Markdown, TXT, PDF, DOCX, and PPTX.
- Imported text is searchable and answers cite source plus page, slide, or
  section when available.
- Duplicate files do not create duplicate chunks.
- Failed imports remain visible and can be retried.
- A screenshot is OCR-indexed when a provider is available and clearly marked
  when OCR is unavailable.
- Explicitly shared Notion content can be synchronized read-only without
  exposing the token.
- No imported content enters spaced repetition until the user approves a card.
- A cited ChatGPT study pack can be exported without an OpenAI API key.
- All application data remains local in this scope.

## Deferred Work

- VPS backup, remote synchronization, and public hosting.
- Direct OpenAI API calls or automatic ChatGPT uploads.
- Collaborative accounts and multi-user permissions.
- Tauri packaging.
