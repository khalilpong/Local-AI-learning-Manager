from pathlib import Path

from app.db import Database
from app.services.library import LibraryService
from app.services.ocr import NullOcrProvider, create_ocr_provider


class FakeEmbedder:
    version = "test-v1"

    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]


class FakeOcrProvider:
    name = "fake"

    def __init__(self, text: str, available: bool = True):
        self._text = text
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def extract_text(self, path: Path) -> str:
        return self._text


def make_service(tmp_path, ocr_provider=None):
    db = Database(tmp_path / "memory.db")
    db.init()
    return LibraryService(
        db=db,
        embedder=FakeEmbedder(),
        library_dir=tmp_path / "library",
        max_upload_bytes=1024 * 1024,
        ocr_provider=ocr_provider,
    )


def _import_png(service, course_id):
    # Minimal 1x1 PNG bytes; parsing never decodes it because OCR is faked.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f1b0000000049454e44ae426082"
    )
    import io

    return service.import_file(
        course_id=course_id,
        filename="screenshot.png",
        mime_type="image/png",
        stream=io.BytesIO(png),
    )


def test_image_without_provider_is_marked_ocr_required(tmp_path):
    service = make_service(tmp_path, ocr_provider=NullOcrProvider())
    course = service.create_course(name="Screens")

    document = _import_png(service, course["id"])

    assert document["status"] == "ocr_required"
    assert document["chunks"] == []
    assert Path(document["managed_path"]).exists()  # original preserved for retry


def test_image_with_provider_is_ocr_indexed(tmp_path):
    provider = FakeOcrProvider("梯度下降 minimizes the loss function")
    service = make_service(tmp_path, ocr_provider=provider)
    course = service.create_course(name="Screens")

    document = _import_png(service, course["id"])

    assert document["status"] == "ready"
    assert len(document["chunks"]) == 1
    assert document["chunks"][0]["location_label"] == "image OCR"
    assert "梯度下降" in document["chunks"][0]["content"]


def test_retry_runs_ocr_after_provider_becomes_available(tmp_path):
    provider = FakeOcrProvider("recovered text", available=False)
    service = make_service(tmp_path, ocr_provider=provider)
    course = service.create_course(name="Screens")

    document = _import_png(service, course["id"])
    assert document["status"] == "ocr_required"

    provider._available = True
    retried = service.retry_document(document["id"])

    assert retried["status"] == "ready"
    assert "recovered text" in retried["chunks"][0]["content"]


def test_empty_ocr_result_stays_ocr_required(tmp_path):
    service = make_service(tmp_path, ocr_provider=FakeOcrProvider("   "))
    course = service.create_course(name="Screens")

    document = _import_png(service, course["id"])

    assert document["status"] == "ocr_required"


def test_null_provider_is_default_and_unavailable():
    provider = create_ocr_provider("none")
    assert isinstance(provider, NullOcrProvider)
    assert provider.is_available() is False
