"""Optional screenshot / image OCR through a pluggable provider interface.

The importer marks images `ocr_required` until a provider can extract text.
Providers are optional: when none is available the original image is preserved
and the document stays `ocr_required` rather than being reported as empty text.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class OcrProvider(Protocol):
    name: str

    def is_available(self) -> bool:
        ...

    def extract_text(self, path: Path) -> str:
        ...


class NullOcrProvider:
    """Used when no OCR backend is installed. Always unavailable."""

    name = "none"

    def is_available(self) -> bool:
        return False

    def extract_text(self, path: Path) -> str:
        raise RuntimeError("No OCR provider is available")


class MacVisionOcrProvider:
    """Uses the macOS Vision framework via pyobjc. No network, fully local."""

    name = "macos-vision"

    def is_available(self) -> bool:
        try:
            import Vision  # noqa: F401
            import Quartz  # noqa: F401
        except Exception:
            return False
        return True

    def extract_text(self, path: Path) -> str:
        import Quartz
        import Vision
        from Foundation import NSURL

        url = NSURL.fileURLWithPath_(str(path))
        source = Quartz.CGImageSourceCreateWithURL(url, None)
        if source is None:
            raise RuntimeError(f"Could not read image: {path.name}")
        image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
        if image is None:
            raise RuntimeError(f"Could not decode image: {path.name}")

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)
        # Chinese + English cover the primary study languages; extras are ignored
        # gracefully if the OS build lacks a model.
        request.setRecognitionLanguages_(["zh-Hans", "zh-Hant", "en-US"])

        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
            image, None
        )
        success = handler.performRequests_error_([request], None)
        if not success:
            raise RuntimeError("OCR request failed")

        lines: list[str] = []
        for observation in request.results() or []:
            candidate = observation.topCandidates_(1)
            if candidate:
                lines.append(str(candidate[0].string()))
        return "\n".join(line for line in lines if line.strip()).strip()


def create_ocr_provider(backend: str = "auto") -> OcrProvider:
    backend = (backend or "auto").strip().lower()
    if backend in {"none", "off", "disabled"}:
        return NullOcrProvider()
    if backend in {"auto", "macos-vision", "vision"}:
        vision = MacVisionOcrProvider()
        if vision.is_available():
            return vision
        if backend != "auto":
            # Explicit request for an unavailable backend should be visible.
            return vision
    return NullOcrProvider()
