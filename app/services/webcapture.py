"""Public web-page capture with SSRF protection.

Fetches an HTTP(S) page, extracts a title and readable text, and records the
canonical URL and retrieval time. Loopback, private-network, link-local, and
non-HTTP targets are rejected before any network request is made so the
importer cannot be turned into a server-side request forgery primitive.
"""
from __future__ import annotations

import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib import request as urllib_request
from urllib.parse import urlparse


class WebCaptureError(ValueError):
    pass


class UnsafeUrlError(WebCaptureError):
    pass


@dataclass(frozen=True)
class CapturedPage:
    url: str
    title: str
    text: str
    retrieved_at: str


# A fetcher takes a validated URL and returns (final_url, content_type, body).
Fetcher = Callable[[str], tuple[str, str, str]]
# A resolver maps a hostname to the list of IP strings it resolves to.
Resolver = Callable[[str, int], list[str]]

_MAX_BYTES = 3 * 1024 * 1024
_USER_AGENT = "LocalMemory/1.0 (+local-first knowledge base)"


def _is_blocked_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port)
    return [info[4][0] for info in infos]


def _is_ip_literal(host: str) -> str | None:
    candidate = host.strip("[]")
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def assert_safe_url(url: str, *, resolver: Resolver | None = None) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("Only http and https URLs are allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL is missing a host")
    lowered = host.lower()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        raise UnsafeUrlError("Loopback hosts are not allowed")

    # IP literals are checked directly; no DNS needed.
    literal = _is_ip_literal(host)
    if literal is not None:
        if _is_blocked_ip(literal):
            raise UnsafeUrlError("Target is a private or loopback address")
        return url.strip()

    # Hostnames are resolved and every returned address must be public.
    resolve = resolver or _default_resolver
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        resolved = set(resolve(host, port))
    except OSError as exc:
        raise UnsafeUrlError(f"Could not resolve host: {host}") from exc
    if not resolved:
        raise UnsafeUrlError(f"Could not resolve host: {host}")
    for ip in resolved:
        if _is_blocked_ip(ip):
            raise UnsafeUrlError("Target resolves to a private or loopback address")
    return url.strip()


def _default_fetcher(url: str) -> tuple[str, str, str]:
    req = urllib_request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib_request.urlopen(req, timeout=10.0) as response:  # noqa: S310 - validated above
        final_url = response.geturl()
        # Re-validate the post-redirect URL to close redirect-based SSRF.
        assert_safe_url(final_url)
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise WebCaptureError("Page is larger than the capture limit")
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type)
    if match:
        charset = match.group(1)
    try:
        body = raw.decode(charset, errors="replace")
    except LookupError:
        body = raw.decode("utf-8", errors="replace")
    return final_url, content_type, body


def _extract_title(document: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", document, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _collapse(html.unescape(match.group(1)))


def _html_to_text(document: str) -> str:
    # Drop non-content regions entirely before stripping remaining tags.
    cleaned = re.sub(
        r"<(script|style|noscript|template|svg)[^>]*>.*?</\1>",
        " ",
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"<!--.*?-->", " ", cleaned, flags=re.DOTALL)
    # Turn block boundaries into newlines so paragraphs survive.
    cleaned = re.sub(
        r"</(p|div|section|article|h[1-6]|li|br|tr|table|header|footer)\s*>",
        "\n",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", cleaned)
    text = html.unescape(text)
    lines = [_collapse(line) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _collapse(value: str) -> str:
    return re.sub(r"[ \t ]+", " ", value).strip()


def capture_page(
    url: str,
    *,
    fetcher: Fetcher | None = None,
    resolver: Resolver | None = None,
) -> CapturedPage:
    safe_url = assert_safe_url(url, resolver=resolver)
    fetch = fetcher or _default_fetcher
    final_url, content_type, body = fetch(safe_url)
    normalized_type = content_type.lower()
    if normalized_type and "html" not in normalized_type and "text" not in normalized_type:
        raise WebCaptureError(f"Unsupported content type: {content_type}")
    text = _html_to_text(body) if "html" in normalized_type or "<" in body else _collapse(body)
    if not text:
        raise WebCaptureError("No readable text found on the page")
    title = _extract_title(body) or final_url
    return CapturedPage(
        url=final_url,
        title=title,
        text=text,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
    )
