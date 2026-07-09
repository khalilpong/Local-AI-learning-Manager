# Personal Memory App Design

## Goal

Build a local-first AI personal knowledge base where users can save notes,
search semantically, ask questions over their notes, and generate weekly
reviews without sending note data to a cloud server.

## Architecture

The MVP runs as a local FastAPI service bound to `127.0.0.1`. SQLite stores
notes, tags, embeddings, and weekly reviews. A plain server-rendered web UI
uses stable API routes so the same backend can later be launched by a Tauri
or Electron desktop shell.

## Components

- FastAPI app: API routes plus server-rendered HTML pages.
- SQLite database: local durable storage with FTS support when available.
- Embedding provider: deterministic local hash embeddings by default, with an
  optional sentence-transformers provider.
- AI client: Ollama for local LLM summarization, tagging, QA, and weekly
  reviews, with a local fallback when Ollama is unavailable.
- Web UI: note creation, search, question answering, similar notes, and weekly
  review generation.

## Local-Only Constraints

- Bind the web service to `127.0.0.1` by default.
- Store data under configurable local paths.
- Do not require accounts, cloud sync, external analytics, or remote APIs.
- Keep Ollama optional at runtime so note creation and search remain usable.

## Desktop Migration

The backend and UI remain decoupled through local HTTP routes. A future
desktop shell can launch the FastAPI process, wait for `/api/health`, and load
the local URL in a webview. The database location can be switched to the OS
application data directory through `MEMORY_DB_PATH`.
