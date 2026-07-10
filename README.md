# Local Memory

Local Memory is a local-first AI personal knowledge base. It stores notes in
SQLite, creates local embeddings for retrieval, and uses Ollama on your own
machine for summaries, tags, question answering, and weekly reviews.

## What It Does

- Create, edit, and delete notes for ideas, projects, English sentences, and technical notes.
- Automatically summarize and tag notes (regenerated on every edit).
- Review notes with a spaced-repetition study queue (simplified SM-2, like Anki).
- Track learning stats: day streak, notes per week, due reviews, 14-day activity.
- Search with local semantic embeddings plus keyword matching, with matched terms highlighted.
- Filter notes and search results by tag.
- View a note's full detail alongside its most similar notes, with Markdown rendering.
- Ask questions over your notes with source citations.
- Generate weekly reviews from local notes.
- Export all notes as a single Markdown file for backup.
- Keyboard shortcuts: `/` search, `n` new note, `Esc` close dialog.
- Keep all note data, embeddings, summaries, and reviews on your computer.

## Screenshots

![Dashboard on desktop](docs/screenshots/dashboard-desktop.png)

Responsive layout on a phone-sized window: [dashboard-mobile.png](docs/screenshots/dashboard-mobile.png)

## Demo Walkthrough

1. **Capture** — press `n`, type a thought (Markdown supported), hit
   *Save note*. A one-sentence summary and topic tags are generated
   automatically (Ollama when available, local fallback otherwise).
2. **Study** — the note joins the spaced-repetition queue. Recall it from
   the title, click *Show answer*, then grade yourself *Again / Good /
   Easy*. Intervals grow like Anki (simplified SM-2).
3. **Track** — the stats panel shows your day streak, due reviews, and a
   14-day activity chart.
4. **Retrieve** — press `/` and search in English or Chinese (CJK bigram
   matching), filter by tag chips, or open a note to see its most similar
   neighbours.
5. **Ask** — question your own notes in natural language and get a cited,
   Markdown-formatted answer.
6. **Reflect** — generate a weekly review with themes, ideas to revisit,
   and next actions; export everything to Markdown any time.

## Architecture

- `FastAPI` backend, bound to `127.0.0.1` by default.
- `SQLite` database under `./data/memory.db` by default.
- Local embedding provider with deterministic hashing by default.
- Optional stronger local embeddings through `sentence-transformers`.
- `Ollama` local LLM integration at `http://127.0.0.1:11434`.
- Plain HTML/CSS/JS web UI that can later be wrapped by Tauri or Electron.

No cloud server is required. The app is designed to run as a local backend
process today and be packaged as a desktop app later.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://127.0.0.1:8000
```

On macOS you can also double-click `Local Memory.command` in Finder to
start the server and open the app in one step.

## Ollama Setup

Install Ollama and pull a local model:

```bash
ollama pull qwen2.5
ollama serve
```

The app defaults to:

```text
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5
```

If Ollama is not running, notes still save and search still works. Summaries,
tags, and answers fall back to a simple local offline mode until Ollama is
available.

## Configuration

Copy `.env.example` to `.env` or export variables in your shell:

```bash
export MEMORY_DB_PATH=./data/memory.db
export MEMORY_AI_MODE=auto
export OLLAMA_MODEL=qwen2.5
```

`MEMORY_AI_MODE` values:

- `auto`: try Ollama, fall back locally if it is unavailable.
- `offline`: never call Ollama.
- `ollama`: prefer Ollama; still fails gracefully if the service is down.

`MEMORY_EMBEDDING_BACKEND` values (default `auto`):

- `auto`: use sentence-transformers when installed, otherwise hash.
- `hash`: deterministic local embeddings with CJK bigrams, no model download.
- `sentence-transformers`: require a local sentence-transformers model.

For stronger semantic search, just install the package and restart —
stored vectors are versioned and rebuilt automatically on startup:

```bash
pip install sentence-transformers
```

You can also switch the Ollama model from the sidebar dropdown; the choice
is persisted in SQLite and survives restarts.

## Tests

```bash
python -m pytest -q
```

The service tests use fake AI clients and do not require Ollama.

## Desktop App

Two ways to run Local Memory like a desktop app today:

- **Native window** (WKWebView via pywebview, no browser chrome):

  ```bash
  pip install pywebview
  python3 desktop.py
  ```

- **One-click launcher**: double-click `Local Memory.command` in Finder to
  start the server and open the app in your browser.

The architecture also stays ready for a Tauri shell (requires the Rust
toolchain): the backend binds only to `127.0.0.1`, storage paths are
configurable (`MEMORY_DB_PATH` can point at
`~/Library/Application Support/Local Memory/memory.db`), and the UI talks
to stable local HTTP APIs.

Resume line:

```text
Built a local-first AI personal memory app with FastAPI, SQLite, semantic search, Ollama-powered summarization, and a desktop-ready architecture.
```
