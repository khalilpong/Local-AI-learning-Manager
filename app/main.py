from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

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
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import Database
from app.schemas import (
    AskRequest,
    CourseCreate,
    CourseUpdate,
    GradeRequest,
    NoteCreate,
    NoteUpdate,
    SettingsUpdate,
    WeeklyReviewRequest,
)
from app.services.embeddings import create_embedding_provider
from app.services.documents import UnsupportedDocumentError
from app.services.library import LibraryService, UploadTooLargeError
from app.services.memory import MemoryService
from app.services.ollama import create_ai_client
from app.settings import Settings, load_settings


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
    )
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
            )
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
    def search_notes(q: str, request: Request, limit: int = 10, tag: str | None = None):
        limit = min(max(limit, 1), 50)
        results = get_service(request).search_notes(q, limit=limit, tag=tag)
        return {"query": q, "results": results}

    @app.post("/api/ask")
    def ask_question(payload: AskRequest, request: Request):
        try:
            return get_service(request).ask_question(payload.question, limit=payload.limit)
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

    @app.get("/api/study/queue")
    def study_queue(request: Request, limit: int = 10):
        limit = min(max(limit, 1), 50)
        return {"notes": get_service(request).study_queue(limit=limit)}

    @app.post("/api/study/{note_id}/grade")
    def grade_note(note_id: int, payload: GradeRequest, request: Request):
        try:
            return get_service(request).grade_note(note_id, payload.grade)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Note not found") from exc
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
