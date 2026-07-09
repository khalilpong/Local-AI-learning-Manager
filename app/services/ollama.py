from __future__ import annotations

import json
import re
from urllib import error, request

from app.services.embeddings import tokenize


class LocalAiFallback:
    def summarize_and_tag(self, title: str, content: str) -> dict:
        words = content.strip().split()
        summary = " ".join(words[:32])
        if len(words) > 32:
            summary += "..."
        if not summary:
            summary = title
        tags = self._tags(title, content)
        return {"summary": summary, "tags": tags, "available": False}

    def answer_question(self, question: str, notes: list[dict]) -> dict:
        if not notes:
            return {
                "answer": "I could not find relevant local notes for that question.",
                "available": False,
            }
        titles = ", ".join(note["title"] for note in notes[:3])
        answer = (
            "Ollama is not available, so this is an extractive local answer. "
            f"The most relevant notes are: {titles}."
        )
        return {"answer": answer, "available": False}

    def weekly_review(self, notes: list[dict], week_start: str, week_end: str) -> dict:
        if not notes:
            content = f"No notes were created from {week_start} to {week_end}."
        else:
            lines = [f"Weekly review for {week_start} to {week_end}:"]
            for note in notes:
                summary = note.get("summary") or note["content"][:140]
                lines.append(f"- {note['title']}: {summary}")
            content = "\n".join(lines)
        return {"review": content, "available": False}

    def _tags(self, title: str, content: str) -> list[str]:
        stop = {
            "about",
            "after",
            "and",
            "are",
            "for",
            "from",
            "how",
            "into",
            "the",
            "this",
            "with",
            "your",
        }
        counts: dict[str, int] = {}
        for token in tokenize(f"{title} {content}"):
            if len(token) < 3 or token in stop:
                continue
            counts[token] = counts.get(token, 0) + 1
        tags = sorted(counts, key=lambda item: (-counts[item], item))[:5]
        return tags or ["memory"]


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            with request.urlopen(f"{self.base_url}/api/tags", timeout=1.0) as response:
                return response.status < 500
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            with request.urlopen(f"{self.base_url}/api/tags", timeout=2.0) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []
        return sorted(
            str(model.get("name", "")).strip()
            for model in body.get("models", [])
            if model.get("name")
        )

    def summarize_and_tag(self, title: str, content: str) -> dict:
        prompt = f"""
You organize a private local knowledge base.
Return strict JSON with exactly two keys: "summary" and "tags".

Rules:
- "summary": exactly one concise sentence capturing the core point.
  Write it in the same language as the note content (Chinese notes get a
  Chinese summary, English notes get an English summary).
- "tags": an array of 3 to 6 short lowercase topic tags. Prefer concrete
  topics (e.g. "fastapi", "语法") over generic words (e.g. "note", "idea").
- No text outside the JSON object.

Title: {title}
Content:
{content}
"""
        data = self._json_generate(prompt)
        tags = data.get("tags", [])
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",")]
        return {
            "summary": str(data.get("summary", "")).strip(),
            "tags": tags,
            "available": True,
        }

    def answer_question(self, question: str, notes: list[dict]) -> dict:
        context = "\n\n".join(
            f"[{index + 1}] {note['title']}\n{note.get('summary') or note['content']}\n{note['content']}"
            for index, note in enumerate(notes)
        )
        prompt = f"""
Answer the user's question using only the local notes below.

Rules:
- Answer in the same language as the question.
- If the notes do not contain the answer, say so plainly instead of guessing.
- Format the answer as short Markdown. Use a list when comparing several notes.
- Reference note titles in **bold** when you draw on them.

Question: {question}

Local notes:
{context}
"""
        return {
            "answer": self._generate(prompt, temperature=0.3).strip(),
            "available": True,
        }

    def weekly_review(self, notes: list[dict], week_start: str, week_end: str) -> dict:
        context = "\n\n".join(
            f"- {note['title']} (tags: {', '.join(note.get('tags', []))}): "
            f"{note.get('summary') or note['content'][:300]}"
            for note in notes
        )
        prompt = f"""
Create a weekly review for a private local knowledge base.
Date range: {week_start} to {week_end}

Rules:
- Write in the dominant language of the notes.
- Output Markdown with exactly these three sections:
  ### Main themes
  ### Ideas to revisit
  ### Next actions
- Keep each section to 2-4 bullet points grounded in the notes below.
  Do not invent notes that are not listed.

Notes:
{context}
"""
        return {
            "review": self._generate(prompt, temperature=0.3).strip(),
            "available": True,
        }

    def _json_generate(self, prompt: str) -> dict:
        text = self._generate(prompt, temperature=0.2, json_format=True)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("Ollama response did not include JSON")
        return json.loads(match.group(0))

    def _generate(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        json_format: bool = False,
    ) -> str:
        body: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if temperature is not None:
            body["options"] = {"temperature": temperature}
        if json_format:
            body["format"] = "json"
        payload = json.dumps(body).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data.get("response", ""))


class HybridAiClient:
    def __init__(self, mode: str, ollama: OllamaClient, fallback: LocalAiFallback | None = None):
        self.mode = mode
        self.ollama = ollama
        self.fallback = fallback or LocalAiFallback()

    @property
    def current_model(self) -> str:
        return self.ollama.model

    def set_model(self, model: str) -> None:
        self.ollama.model = model

    def list_models(self) -> list[str]:
        if self.mode == "offline":
            return []
        return self.ollama.list_models()

    def is_available(self) -> bool:
        if self.mode == "offline":
            return False
        return self.ollama.is_available()

    def summarize_and_tag(self, title: str, content: str) -> dict:
        if self.mode == "offline":
            return self.fallback.summarize_and_tag(title, content)
        try:
            result = self.ollama.summarize_and_tag(title, content)
            if result["summary"] and result["tags"]:
                return result
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
        return self.fallback.summarize_and_tag(title, content)

    def answer_question(self, question: str, notes: list[dict]) -> dict:
        if self.mode == "offline":
            return self.fallback.answer_question(question, notes)
        try:
            return self.ollama.answer_question(question, notes)
        except (error.URLError, TimeoutError):
            return self.fallback.answer_question(question, notes)

    def weekly_review(self, notes: list[dict], week_start: str, week_end: str) -> dict:
        if self.mode == "offline":
            return self.fallback.weekly_review(notes, week_start, week_end)
        try:
            return self.ollama.weekly_review(notes, week_start, week_end)
        except (error.URLError, TimeoutError):
            return self.fallback.weekly_review(notes, week_start, week_end)


def create_ai_client(mode: str, base_url: str, model: str) -> HybridAiClient:
    return HybridAiClient(
        mode=mode,
        ollama=OllamaClient(base_url=base_url, model=model),
    )
