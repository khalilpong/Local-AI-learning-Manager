"""Read-only Notion synchronization.

Only pages explicitly shared with the integration are pulled. The token is
read from the environment and is never returned in API responses, logs, or
exports. Synchronization is one-way (Notion -> Local Memory); local edits are
never pushed back, and a page that disappears from Notion is archived locally
rather than deleted.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib import error, request


@dataclass(frozen=True)
class NotionPage:
    id: str
    title: str
    url: str
    last_edited_time: str
    text: str


class NotionClient(Protocol):
    def list_shared_pages(self) -> list[NotionPage]:
        ...


class NotionNotConfiguredError(RuntimeError):
    pass


_NOTION_VERSION = "2022-06-28"


class HttpNotionClient:
    """Minimal read-only Notion API client.

    Uses the search endpoint to enumerate shared pages and reads each page's
    top-level text blocks. Requires ``NOTION_TOKEN`` in the environment.
    """

    def __init__(self, token: str | None = None, *, base_url: str = "https://api.notion.com"):
        self.token = token or os.getenv("NOTION_TOKEN", "")
        self.base_url = base_url.rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict) -> dict:
        req = request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with request.urlopen(req, timeout=15.0) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get(self, path: str) -> dict:
        req = request.Request(
            f"{self.base_url}{path}", headers=self._headers(), method="GET"
        )
        with request.urlopen(req, timeout=15.0) as response:
            return json.loads(response.read().decode("utf-8"))

    def list_shared_pages(self) -> list[NotionPage]:
        if not self.is_configured():
            raise NotionNotConfiguredError("NOTION_TOKEN is not set")
        pages: list[NotionPage] = []
        try:
            results = self._post(
                "/v1/search",
                {"filter": {"property": "object", "value": "page"}},
            ).get("results", [])
        except (error.URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError(f"Notion search failed: {exc}") from exc
        for item in results:
            page_id = str(item.get("id", ""))
            if not page_id:
                continue
            text = self._read_page_text(page_id)
            pages.append(
                NotionPage(
                    id=page_id,
                    title=_extract_title(item) or page_id,
                    url=str(item.get("url", "")),
                    last_edited_time=str(item.get("last_edited_time", "")),
                    text=text,
                )
            )
        return pages

    def _read_page_text(self, page_id: str) -> str:
        try:
            blocks = self._get(f"/v1/blocks/{page_id}/children?page_size=100").get(
                "results", []
            )
        except (error.URLError, TimeoutError, ValueError):
            return ""
        lines = [_block_text(block) for block in blocks]
        return "\n".join(line for line in lines if line).strip()


def _extract_title(page: dict) -> str:
    properties = page.get("properties", {})
    for value in properties.values():
        if value.get("type") == "title":
            return _rich_text_to_plain(value.get("title", []))
    return ""


def _block_text(block: dict) -> str:
    block_type = block.get("type", "")
    payload = block.get(block_type, {})
    if isinstance(payload, dict) and "rich_text" in payload:
        return _rich_text_to_plain(payload["rich_text"])
    return ""


def _rich_text_to_plain(rich_text: list) -> str:
    return "".join(part.get("plain_text", "") for part in rich_text).strip()
