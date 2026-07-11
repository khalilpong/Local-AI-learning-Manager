import pytest

from app.db import Database
from app.services.library import LibraryService
from app.services.webcapture import (
    UnsafeUrlError,
    WebCaptureError,
    assert_safe_url,
    capture_page,
)


class FakeEmbedder:
    version = "test-v1"

    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]


def public_resolver(host: str, port: int) -> list[str]:
    # Pretend every hostname resolves to a public address so SSRF checks
    # pass without real DNS in offline tests.
    return ["93.184.216.34"]


def make_library_service(tmp_path):
    db = Database(tmp_path / "memory.db")
    db.init()
    return LibraryService(
        db=db,
        embedder=FakeEmbedder(),
        library_dir=tmp_path / "library",
        max_upload_bytes=1024 * 1024,
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://127.0.0.1:8000/api/health",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "https://[::1]/loopback",
        "http:///no-host",
    ],
)
def test_unsafe_urls_are_rejected(url):
    with pytest.raises(UnsafeUrlError):
        assert_safe_url(url)


def test_capture_extracts_title_and_readable_text():
    html = """
    <html><head><title>Gradient Descent</title></head>
    <body>
      <script>tracking()</script>
      <h1>Gradient Descent</h1>
      <p>Gradient descent minimizes a loss function.</p>
      <style>.x{color:red}</style>
      <p>The learning rate controls the step size.</p>
    </body></html>
    """

    def fake_fetch(url):
        return url, "text/html; charset=utf-8", html

    page = capture_page("https://example.com/post", fetcher=fake_fetch, resolver=public_resolver)

    assert page.title == "Gradient Descent"
    assert "Gradient descent minimizes a loss function." in page.text
    assert "learning rate controls the step size" in page.text
    assert "tracking()" not in page.text
    assert "color:red" not in page.text
    assert page.url == "https://example.com/post"


def test_capture_rejects_empty_text():
    def fake_fetch(url):
        return url, "text/html", "<html><body><script>x()</script></body></html>"

    with pytest.raises(WebCaptureError):
        capture_page("https://example.com/empty", fetcher=fake_fetch, resolver=public_resolver)


def test_capture_rejects_non_text_content():
    def fake_fetch(url):
        return url, "application/pdf", "%PDF-1.4 binary"

    with pytest.raises(WebCaptureError):
        capture_page("https://example.com/file.pdf", fetcher=fake_fetch, resolver=public_resolver)


def test_import_web_page_indexes_and_is_searchable(tmp_path):
    service = make_library_service(tmp_path)
    course = service.create_course(name="Web Reading")

    html = (
        "<html><head><title>SVM Notes</title></head><body>"
        "<p>Support vector machines maximize the margin between classes.</p>"
        "</body></html>"
    )

    def fake_fetch(url):
        return url, "text/html", html

    document = service.import_web_page(
        course["id"], "https://example.com/svm", fetcher=fake_fetch, resolver=public_resolver
    )

    assert document["status"] == "ready"
    assert document["source_type"] == "web"
    assert document["origin_url"] == "https://example.com/svm"
    assert document["title"] == "SVM Notes"
    assert len(document["chunks"]) == 1
    assert document["chunks"][0]["location_label"] == "web page"

    # Re-capturing identical content deduplicates by content hash.
    duplicate = service.import_web_page(
        course["id"], "https://example.com/svm", fetcher=fake_fetch, resolver=public_resolver
    )
    assert duplicate["duplicate"] is True
    assert duplicate["id"] == document["id"]
