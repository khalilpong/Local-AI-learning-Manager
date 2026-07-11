from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import tempfile

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import Database
from app.schemas import (
    AskRequest,
    CardApproveRequest,
    CourseCreate,
    CourseUpdate,
    GradeRequest,
    NoteCreate,
    NoteUpdate,
    NotionSyncRequest,
    SettingsUpdate,
    WeeklyReviewRequest,
    WebCaptureRequest,
)
from app.services.embeddings import create_embedding_provider
from app.services.backup import BackupError, BackupService
from app.services.dashboard import DashboardService
from app.services.diagnostics import DiagnosticsService
from app.services.documents import UnsupportedDocumentError
from app.services.library import LibraryService, UploadTooLargeError
from app.services.notion import HttpNotionClient, NotionNotConfiguredError
from app.services.ocr import create_ocr_provider
from app.services.webcapture import UnsafeUrlError, WebCaptureError
from app.services.memory import MemoryService
from app.services.ollama import create_ai_client
from app.services.study_bridge import StudyBridgeService
from app.settings import Settings, load_settings
from starlette.background import BackgroundTask


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def build_service(settings: Settings) -> MemoryService:
    db = Database(settings.db_path)
    db.init()
    model = db.get_setting("ollama_model") or settings.ollama_model
    service = MemoryService(
        db=db,
        embedder=create_embedding_provider(settings),
        ai_client=create_ai_client(
            mode=settings.ai_mode,
            base_url=settings.ollama_base_url,
            model=model,
        ),
    )
    service.ensure_embeddings()
    return service


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or load_settings()
    app = FastAPI(
        title="Local Memory",
        description="Local-first AI personal knowledge base",
        version="0.1.0",
    )
    app.state.settings = active_settings
    app.state.memory_service = build_service(active_settings)
    app.state.library_service = LibraryService(
        db=app.state.memory_service.db,
        embedder=app.state.memory_service.embedder,
        library_dir=active_settings.library_dir,
        max_upload_bytes=active_settings.max_upload_bytes,
        ocr_provider=create_ocr_provider(active_settings.ocr_backend),
    )
    app.state.notion_client = HttpNotionClient()
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        service = get_service(request)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "request": request,
                "notes": service.list_notes(limit=20),
                "reviews": service.list_weekly_reviews(),
                "health": service.health(),
            },
        )

    @app.get("/api/health")
    def health(request: Request):
        return get_service(request).health()

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/notes")
    def list_notes(request: Request, limit: int = 50, offset: int = 0, tag: str | None = None):
        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)
        notes = get_service(request).list_notes(limit, offset, tag=tag)
        return {"notes": strip_embeddings(notes)}

    @app.post("/api/notes", status_code=status.HTTP_201_CREATED)
    def create_note(payload: NoteCreate, request: Request):
        try:
            note = get_service(request).create_note(
                title=payload.title,
                content=payload.content,
                source=payload.source,
                course_id=payload.course_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Course not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return strip_embedding(note)

    @app.get("/api/tags")
    def list_tags(request: Request):
        return {"tags": get_service(request).list_tags()}

    @app.get("/api/courses")
    def list_courses(
        request: Request,
        course_status: str = Query(default="active", alias="status"),
    ):
        if course_status not in {"active", "archived", "all"}:
            raise HTTPException(status_code=400, detail="Invalid course status")
        selected_status = None if course_status == "all" else course_status
        return {
            "courses": get_library_service(request).db.list_courses(selected_status)
        }

    @app.post("/api/courses", status_code=status.HTTP_201_CREATED)
    def create_course(payload: CourseCreate, request: Request):
        try:
            return get_library_service(request).create_course(
                name=payload.name,
                code=payload.code,
                term=payload.term,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/courses/{course_id}")
    def update_course(course_id: int, payload: CourseUpdate, request: Request):
        try:
            return get_library_service(request).db.update_course(
                course_id,
                name=payload.name,
                code=payload.code,
                term=payload.term,
                status=payload.status,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Course not found") from exc

    @app.get("/api/courses/{course_id}/dashboard")
    def course_dashboard(course_id: int, request: Request):
        try:
            return DashboardService(get_service(request).db).course_dashboard(course_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Course not found") from exc

    @app.get("/api/library/documents")
    def list_library_documents(request: Request, course_id: int | None = None):
        if course_id is not None:
            try:
                get_library_service(request).db.get_course(course_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Course not found") from exc
        return {
            "documents": get_library_service(request).list_documents(course_id)
        }

    @app.post("/api/library/import")
    def import_library_document(
        request: Request,
        response: Response,
        course_id: int = Form(...),
        file: UploadFile = File(...),
    ):
        try:
            document = get_library_service(request).import_file(
                course_id=course_id,
                filename=file.filename or "document",
                mime_type=file.content_type or "application/octet-stream",
                stream=file.file,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Course not found") from exc
        except (UploadTooLargeError, UnsupportedDocumentError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        response.status_code = (
            status.HTTP_200_OK if document["duplicate"] else status.HTTP_201_CREATED
        )
        return document

    @app.post("/api/library/capture", status_code=status.HTTP_201_CREATED)
    def capture_web_page(payload: WebCaptureRequest, request: Request, response: Response):
        try:
            document = get_library_service(request).import_web_page(
                course_id=payload.course_id,
                url=str(payload.url),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Course not found") from exc
        except UnsafeUrlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except WebCaptureError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        response.status_code = (
            status.HTTP_200_OK if document["duplicate"] else status.HTTP_201_CREATED
        )
        return document

    @app.get("/api/notion/status")
    def notion_status(request: Request):
        client = request.app.state.notion_client
        return {"configured": bool(client and client.is_configured())}

    @app.post("/api/notion/sync")
    def sync_notion(payload: NotionSyncRequest, request: Request):
        client = request.app.state.notion_client
        if client is None or not client.is_configured():
            raise HTTPException(
                status_code=400,
                detail="Notion is not configured. Set NOTION_TOKEN in the environment.",
            )
        try:
            return get_library_service(request).sync_notion(payload.course_id, client)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Course not found") from exc
        except NotionNotConfiguredError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (RuntimeError, OSError) as exc:
            raise HTTPException(status_code=502, detail=f"Notion sync failed: {exc}") from exc

    @app.get("/api/diagnostics")
    def diagnostics(request: Request):
        memory = get_service(request)
        library = get_library_service(request)
        return DiagnosticsService(
            db=memory.db,
            library_dir=request.app.state.settings.library_dir,
            embedder=memory.embedder,
            ai_client=memory.ai_client,
            ocr_provider=library.ocr_provider,
        ).report()

    @app.get("/api/library/documents/{document_id}")
    def get_library_document(document_id: int, request: Request):
        try:
            return get_library_service(request).get_document(document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Document not found") from exc

    @app.post("/api/library/documents/{document_id}/retry")
    def retry_library_document(document_id: int, request: Request):
        try:
            return get_library_service(request).retry_document(document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Document not found") from exc

    @app.get("/api/notes/{note_id}")
    def get_note(note_id: int, request: Request):
        service = get_service(request)
        try:
            note = service.get_note(note_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Note not found") from exc
        return {
            "note": strip_embedding(note),
            "similar": strip_embeddings(service.similar_notes(note_id, limit=5)),
        }

    @app.put("/api/notes/{note_id}")
    def update_note(note_id: int, payload: NoteUpdate, request: Request):
        service = get_service(request)
        try:
            note = service.update_note(
                note_id,
                title=payload.title,
                content=payload.content,
                source=payload.source,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Note not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return strip_embedding(note)

    @app.delete("/api/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_note(note_id: int, request: Request):
        try:
            get_service(request).delete_note(note_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Note not found") from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/search")
    def search_notes(
        q: str,
        request: Request,
        limit: int = 10,
        tag: str | None = None,
        course_id: int | None = None,
        source_document_id: int | None = None,
    ):
        limit = min(max(limit, 1), 50)
        results = get_service(request).search_notes(
            q,
            limit=limit,
            tag=tag,
            course_id=course_id,
            source_document_id=source_document_id,
        )
        return {"query": q, "results": results}

    @app.post("/api/ask")
    def ask_question(payload: AskRequest, request: Request):
        try:
            return get_service(request).ask_question(
                payload.question,
                limit=payload.limit,
                course_id=payload.course_id,
                source_document_id=payload.source_document_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/models")
    def list_models(request: Request):
        service = get_service(request)
        client = service.ai_client
        return {
            "models": getattr(client, "list_models", list)(),
            "current": getattr(client, "current_model", ""),
            "available": bool(getattr(client, "is_available", lambda: False)()),
        }

    @app.put("/api/settings")
    def update_settings(payload: SettingsUpdate, request: Request):
        service = get_service(request)
        try:
            model = service.set_ollama_model(payload.ollama_model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ollama_model": model}

    @app.get("/api/study/candidates")
    def study_candidates(
        request: Request, limit: int = 100, course_id: int | None = None
    ):
        limit = min(max(limit, 1), 200)
        return {
            "cards": get_service(request).study.list_candidates(
                course_id=course_id, limit=limit
            )
        }

    @app.put("/api/study/cards/{card_id}/approve")
    def approve_study_card(
        card_id: int, payload: CardApproveRequest, request: Request
    ):
        try:
            return get_service(request).study.approve(
                card_id, prompt=payload.prompt, answer=payload.answer
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Study card not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/study/cards/{card_id}/reject")
    def reject_study_card(card_id: int, request: Request):
        try:
            return get_service(request).study.reject(card_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Study card not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/study/cards/{card_id}/suspend")
    def suspend_study_card(card_id: int, request: Request):
        try:
            return get_service(request).study.suspend(card_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Study card not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/study/queue")
    def study_queue(
        request: Request, limit: int = 10, course_id: int | None = None
    ):
        limit = min(max(limit, 1), 50)
        return {
            "cards": get_service(request).study.queue(
                limit=limit, course_id=course_id
            )
        }

    @app.post("/api/study/cards/{card_id}/grade")
    def grade_note(card_id: int, payload: GradeRequest, request: Request):
        try:
            return get_service(request).study.grade(card_id, payload.grade)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Study card not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/stats")
    def stats(request: Request):
        return get_service(request).stats()

    @app.get("/api/export/markdown")
    def export_markdown(request: Request):
        content = get_service(request).export_markdown()
        return PlainTextResponse(
            content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="local-memory-export.md"'
            },
        )

    @app.get("/api/backup")
    def download_backup(request: Request):
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="local-memory-", suffix="-backup.zip"
        )
        Path(temporary_name).unlink(missing_ok=True)
        try:
            Path(temporary_name).parent.mkdir(parents=True, exist_ok=True)
            BackupService(
                request.app.state.settings.db_path,
                request.app.state.settings.library_dir,
            ).create_backup(temporary_name)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        finally:
            try:
                import os

                os.close(descriptor)
            except OSError:
                pass
        return FileResponse(
            temporary_name,
            media_type="application/zip",
            filename="local-memory-backup.zip",
            background=BackgroundTask(Path(temporary_name).unlink, missing_ok=True),
        )

    @app.post("/api/backup/restore")
    def restore_backup(request: Request, file: UploadFile = File(...)):
        if not (file.filename or "").lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="Backup must be a ZIP archive")
        descriptor, temporary_name = tempfile.mkstemp(suffix="-restore.zip")
        total = 0
        limit = 2 * 1024 * 1024 * 1024
        try:
            import os

            with os.fdopen(descriptor, "wb") as target:
                while chunk := file.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise BackupError("Backup exceeds the 2 GB restore limit")
                    target.write(chunk)
            return BackupService(
                request.app.state.settings.db_path,
                request.app.state.settings.library_dir,
            ).restore_backup(temporary_name)
        except BackupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    @app.get("/api/study-pack")
    def export_study_pack(course_id: int, request: Request):
        try:
            content = StudyBridgeService(get_service(request)).export_pack(course_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Course not found") from exc
        return PlainTextResponse(
            content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="study-pack-course-{course_id}.md"'
                )
            },
        )

    @app.post("/api/study-pack/import")
    def import_study_result(
        request: Request,
        course_id: int = Form(...),
        file: UploadFile = File(...),
    ):
        filename = (file.filename or "").lower()
        if not filename.endswith((".md", ".markdown")):
            raise HTTPException(status_code=400, detail="Study result must be Markdown")
        limit = min(request.app.state.settings.max_upload_bytes, 2 * 1024 * 1024)
        raw = file.file.read(limit + 1)
        if len(raw) > limit:
            raise HTTPException(status_code=400, detail="Study result is too large")
        try:
            markdown = raw.decode("utf-8")
            return StudyBridgeService(get_service(request)).import_result(
                course_id, markdown
            )
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Markdown must use UTF-8") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Course not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/reviews/weekly")
    def list_weekly_reviews(request: Request):
        return {"reviews": get_service(request).list_weekly_reviews()}

    @app.post("/api/reviews/weekly")
    def generate_weekly_review(payload: WeeklyReviewRequest, request: Request):
        week_start, week_end = resolve_week(payload.week_start, payload.week_end)
        return get_service(request).generate_weekly_review(week_start, week_end)

    return app


def get_service(request: Request) -> MemoryService:
    return request.app.state.memory_service


def get_library_service(request: Request) -> LibraryService:
    return request.app.state.library_service


def strip_embedding(note: dict) -> dict:
    return {key: value for key, value in note.items() if key != "embedding"}


def strip_embeddings(notes: list[dict]) -> list[dict]:
    return [strip_embedding(note) for note in notes]


def resolve_week(week_start: str | None, week_end: str | None) -> tuple[str, str]:
    if week_start and week_end:
        return week_start, week_end
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


app = create_app()
