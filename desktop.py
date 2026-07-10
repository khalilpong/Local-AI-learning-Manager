"""Local Memory desktop shell.

Runs the FastAPI backend in a background thread and opens the UI in a
native window (WKWebView on macOS) instead of a browser tab:

    python3 desktop.py

Data stays in the same local SQLite database as the web version. Set
MEMORY_DB_PATH before launching to use a different location, e.g. an OS
app-data directory:

    MEMORY_DB_PATH="$HOME/Library/Application Support/Local Memory/memory.db" \
        python3 desktop.py
"""
from __future__ import annotations

import socket
import threading
import time

import uvicorn
import webview

from app.main import create_app
from app.settings import load_settings


def wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> None:
    settings = load_settings()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host=settings.host,
            port=settings.port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    if not wait_for_port(settings.host, settings.port):
        raise SystemExit("Local Memory backend did not start in time")

    webview.create_window(
        "Local Memory",
        f"http://{settings.host}:{settings.port}",
        width=1280,
        height=860,
        min_size=(760, 560),
    )
    try:
        webview.start()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
