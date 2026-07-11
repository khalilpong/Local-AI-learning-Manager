import json

from app.db import Database
from app.services.diagnostics import DiagnosticsService


class Available:
    version = "test-embedding"

    def is_available(self):
        return True


def test_diagnostics_reports_local_capabilities_without_secrets(tmp_path, monkeypatch):
    db = Database(tmp_path / "memory.db")
    db.init()
    library = tmp_path / "library"
    monkeypatch.setenv("NOTION_TOKEN", "secret-token-value")
    report = DiagnosticsService(
        db=db,
        library_dir=library,
        embedder=Available(),
        ai_client=Available(),
        ocr_provider=Available(),
    ).report()

    assert report["database"]["schema_version"] == 3
    assert report["database"]["writable"] is True
    assert report["storage"]["writable"] is True
    assert report["storage"]["free_bytes"] > 0
    assert all(report["parsers"].values())
    assert report["ocr"]["available"] is True
    assert report["ollama"]["available"] is True
    assert report["notion"]["configured"] is True
    serialized = json.dumps(report)
    assert "secret-token-value" not in serialized
    assert str(tmp_path) not in serialized
