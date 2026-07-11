from fastapi.testclient import TestClient

from app.main import create_app


def configure_library_test_app(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("MEMORY_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("MEMORY_AI_MODE", "offline")
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")


def test_health_reports_local_dependencies(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["storage"] == "sqlite"
    assert response.json()["local_only"] is True


def test_homepage_renders_app_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("MEMORY_AI_MODE", "offline")
    app = create_app()
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Personal Memory" in response.text
    assert "Local only" in response.text
    assert 'id="library"' in response.text
    assert 'id="courseForm"' in response.text
    assert 'id="courseSelect"' in response.text
    assert 'id="libraryImportForm"' in response.text
    assert 'id="documentList"' in response.text
    assert 'id="searchCourseSelect"' in response.text
    assert 'id="askCourseSelect"' in response.text


def test_favicon_does_not_log_404(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    app = create_app()
    client = TestClient(app)

    response = client.get("/favicon.ico")

    assert response.status_code == 204


def test_create_and_search_note_through_api(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("MEMORY_AI_MODE", "offline")
    app = create_app()
    client = TestClient(app)

    created = client.post(
        "/api/notes",
        json={
            "title": "English sentence",
            "content": "I am getting used to thinking in English every morning.",
            "source": "english",
        },
    )

    assert created.status_code == 201
    assert created.json()["title"] == "English sentence"

    searched = client.get("/api/search", params={"q": "English practice"})

    assert searched.status_code == 200
    assert searched.json()["results"][0]["title"] == "English sentence"


def test_update_and_delete_note_through_api(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("MEMORY_AI_MODE", "offline")
    app = create_app()
    client = TestClient(app)

    created = client.post(
        "/api/notes",
        json={"title": "Draft title", "content": "Draft content about FastAPI."},
    ).json()
    note_id = created["id"]

    updated = client.put(
        f"/api/notes/{note_id}",
        json={"title": "Updated title", "content": "Updated content about SQLite."},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated title"
    assert updated.json()["content"] == "Updated content about SQLite."

    detail = client.get(f"/api/notes/{note_id}")
    assert detail.status_code == 200
    assert detail.json()["note"]["title"] == "Updated title"

    deleted = client.delete(f"/api/notes/{note_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/notes/{note_id}")
    assert missing.status_code == 404

    missing_update = client.put(f"/api/notes/{note_id}", json={"title": "Nope"})
    assert missing_update.status_code == 404


def test_tag_filtering_through_api(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("MEMORY_AI_MODE", "offline")
    app = create_app()
    client = TestClient(app)

    client.post(
        "/api/notes",
        json={"title": "Python tips", "content": "Use context managers for files and connections."},
    )
    client.post(
        "/api/notes",
        json={"title": "Grocery list", "content": "Milk, bread, apples, and coffee."},
    )

    tags = client.get("/api/tags")
    assert tags.status_code == 200
    assert len(tags.json()["tags"]) > 0

    first_tag = tags.json()["tags"][0]["tag"]
    filtered = client.get("/api/notes", params={"tag": first_tag})
    assert filtered.status_code == 200
    assert all(first_tag in note["tags"] for note in filtered.json()["notes"])

    filtered_search = client.get("/api/search", params={"q": "tips", "tag": first_tag})
    assert filtered_search.status_code == 200


def test_model_settings_persist_across_restarts(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("MEMORY_AI_MODE", "offline")
    client = TestClient(create_app())

    models = client.get("/api/models")
    assert models.status_code == 200
    assert models.json()["current"] == "qwen2.5"
    assert models.json()["available"] is False

    updated = client.put("/api/settings", json={"ollama_model": "llama3.1"})
    assert updated.status_code == 200
    assert updated.json()["ollama_model"] == "llama3.1"

    health = client.get("/api/health")
    assert health.json()["ollama_model"] == "llama3.1"

    restarted = TestClient(create_app())
    assert restarted.get("/api/models").json()["current"] == "llama3.1"


def test_study_stats_and_export_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("MEMORY_AI_MODE", "offline")
    app = create_app()
    client = TestClient(app)

    created = client.post(
        "/api/notes",
        json={"title": "Study target", "content": "Reviewing notes builds retention."},
    ).json()

    queue = client.get("/api/study/queue")
    assert queue.status_code == 200
    assert queue.json()["notes"][0]["id"] == created["id"]

    graded = client.post(f"/api/study/{created['id']}/grade", json={"grade": "good"})
    assert graded.status_code == 200
    assert graded.json()["interval_days"] >= 1.0

    empty_queue = client.get("/api/study/queue")
    assert empty_queue.json()["notes"] == []

    bad_grade = client.post(f"/api/study/{created['id']}/grade", json={"grade": "meh"})
    assert bad_grade.status_code == 400

    missing = client.post("/api/study/99999/grade", json={"grade": "good"})
    assert missing.status_code == 404

    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.json()["total_notes"] == 1
    assert stats.json()["reviewed_today"] == 1

    export = client.get("/api/export/markdown")
    assert export.status_code == 200
    assert "## Study target" in export.text


def test_question_answer_endpoint_returns_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("MEMORY_AI_MODE", "offline")
    app = create_app()
    client = TestClient(app)
    client.post(
        "/api/notes",
        json={
            "title": "Local privacy",
            "content": "The app stores notes, embeddings, and summaries in local SQLite.",
        },
    )

    response = client.post("/api/ask", json={"question": "Where is my data stored?"})

    assert response.status_code == 200
    assert response.json()["sources"][0]["title"] == "Local privacy"


def test_create_update_and_list_courses_through_api(tmp_path, monkeypatch):
    configure_library_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())

    created = client.post(
        "/api/courses",
        json={"name": "Computer Networks", "code": "CN", "term": "2026"},
    )

    assert created.status_code == 201
    assert created.json()["code"] == "CN"
    assert client.get("/api/courses").json()["courses"][0]["status"] == "active"

    archived = client.put(
        f"/api/courses/{created.json()['id']}", json={"status": "archived"}
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert client.get("/api/courses").json()["courses"] == []
    assert len(client.get("/api/courses", params={"status": "all"}).json()["courses"]) == 1


def test_create_course_and_import_markdown_through_api(tmp_path, monkeypatch):
    configure_library_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())
    course = client.post(
        "/api/courses", json={"name": "Networks", "code": "CN"}
    )
    assert course.status_code == 201

    imported = client.post(
        "/api/library/import",
        data={"course_id": str(course.json()["id"])},
        files={
            "file": (
                "lecture.md",
                b"# Routing\nDistance vector routing uses relaxation.",
                "text/markdown",
            )
        },
    )

    assert imported.status_code == 201
    assert imported.json()["status"] == "ready"
    assert imported.json()["chunks"][0]["location_label"] == "Routing"

    documents = client.get(
        "/api/library/documents", params={"course_id": course.json()["id"]}
    )
    assert documents.status_code == 200
    assert documents.json()["documents"][0]["id"] == imported.json()["id"]

    detail = client.get(f"/api/library/documents/{imported.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["stored_filename"].endswith("lecture.md")


def test_web_capture_endpoint_rejects_unsafe_targets(tmp_path, monkeypatch):
    configure_library_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())
    course = client.post("/api/courses", json={"name": "Reading"}).json()

    # Loopback / private / non-http targets are refused before any request.
    for url in [
        "http://127.0.0.1:8000/api/health",
        "http://localhost/admin",
        "file:///etc/passwd",
        "http://169.254.169.254/latest/meta-data",
    ]:
        blocked = client.post(
            "/api/library/capture", json={"course_id": course["id"], "url": url}
        )
        assert blocked.status_code == 400, url

    # Missing course is a 404 regardless of URL.
    missing = client.post(
        "/api/library/capture",
        json={"course_id": 999, "url": "https://example.com"},
    )
    assert missing.status_code in (400, 404)


def test_notion_endpoints_require_configuration_without_leaking_token(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    configure_library_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())
    course = client.post("/api/courses", json={"name": "Notion"}).json()

    status_response = client.get("/api/notion/status")
    assert status_response.status_code == 200
    assert status_response.json() == {"configured": False}

    sync = client.post("/api/notion/sync", json={"course_id": course["id"]})
    assert sync.status_code == 400
    # The error explains configuration is missing but never echoes a token value.
    assert "token" not in sync.json()["detail"].lower() or "NOTION_TOKEN" in sync.json()["detail"]


def test_notion_status_reports_configured_when_token_present(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token-value")
    configure_library_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())

    status_response = client.get("/api/notion/status")
    assert status_response.json() == {"configured": True}
    # The token itself must never appear in any response body.
    assert "secret-token-value" not in status_response.text


def test_created_note_can_be_assigned_to_course(tmp_path, monkeypatch):
    configure_library_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())
    course = client.post("/api/courses", json={"name": "Algorithms"}).json()

    created = client.post(
        "/api/notes",
        json={
            "title": "Dynamic programming",
            "content": "Optimal substructure supports recurrence relations.",
            "course_id": course["id"],
        },
    )

    assert created.status_code == 201
    assert created.json()["course_id"] == course["id"]


def test_library_api_reports_duplicate_and_missing_resources(tmp_path, monkeypatch):
    configure_library_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())
    course = client.post("/api/courses", json={"name": "Systems"}).json()

    first = client.post(
        "/api/library/import",
        data={"course_id": str(course["id"])},
        files={"file": ("a.txt", b"same text", "text/plain")},
    )
    duplicate = client.post(
        "/api/library/import",
        data={"course_id": str(course["id"])},
        files={"file": ("b.txt", b"same text", "text/plain")},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["id"] == first.json()["id"]

    missing_course = client.post(
        "/api/library/import",
        data={"course_id": "999"},
        files={"file": ("a.txt", b"text", "text/plain")},
    )
    assert missing_course.status_code == 404
    assert client.get("/api/library/documents/999").status_code == 404
    assert client.put("/api/courses/999", json={"name": "Missing"}).status_code == 404


def test_failed_document_can_be_retried_through_api(tmp_path, monkeypatch):
    configure_library_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())
    course = client.post("/api/courses", json={"name": "PDF"}).json()
    imported = client.post(
        "/api/library/import",
        data={"course_id": str(course["id"])},
        files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
    ).json()

    assert imported["status"] == "failed"
    retried = client.post(f"/api/library/documents/{imported['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "failed"
    assert retried.json()["error_message"]


def test_search_and_ask_filter_document_sources_by_course(tmp_path, monkeypatch):
    configure_library_test_app(tmp_path, monkeypatch)
    client = TestClient(create_app())
    target = client.post("/api/courses", json={"name": "Target"}).json()
    other = client.post("/api/courses", json={"name": "Other"}).json()
    for course, filename in ((target, "target.md"), (other, "other.md")):
        client.post(
            "/api/library/import",
            data={"course_id": str(course["id"])},
            files={
                "file": (
                    filename,
                    f"# Citation\nRouting uses repeated relaxation. Source: {filename}".encode(),
                    "text/markdown",
                )
            },
        )

    searched = client.get(
        "/api/search", params={"q": "routing relaxation", "course_id": target["id"]}
    )
    asked = client.post(
        "/api/ask",
        json={"question": "How does routing work?", "course_id": target["id"]},
    )

    assert searched.status_code == 200
    assert {item["course_id"] for item in searched.json()["results"]} == {target["id"]}
    assert asked.status_code == 200
    assert {item["course_id"] for item in asked.json()["sources"]} == {target["id"]}
