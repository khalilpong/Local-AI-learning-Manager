from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from app.settings import Settings


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class EmbeddingProvider(Protocol):
    version: str

    def embed(self, text: str) -> list[float]:
        ...


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    prev_cjk: str | None = None
    prev_end = -1
    for match in TOKEN_RE.finditer(text.lower()):
        token = match.group(0).strip("_")
        if len(token) > 4 and token.endswith("s"):
            token = token[:-1]
        if not token:
            prev_cjk = None
            continue
        is_cjk = len(token) == 1 and "一" <= token <= "鿿"
        tokens.append(token)
        # Adjacent CJK characters also emit a bigram so multi-character
        # Chinese words match as units, not just as loose characters.
        if is_cjk and prev_cjk and match.start() == prev_end:
            tokens.append(prev_cjk + token)
        prev_cjk = token if is_cjk else None
        prev_end = match.end()
    return tokens


class HashEmbeddingProvider:
    """Deterministic local embeddings with no model download."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions
        self.version = f"hash-v2-{dimensions}"

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.version = f"st:{model_name}"

    def embed(self, text: str) -> list[float]:
        values = self.model.encode(text, normalize_embeddings=True)
        return [float(value) for value in values]


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    backend = settings.embedding_backend
    if backend == "hash":
        return HashEmbeddingProvider()
    if backend in {"sentence-transformers", "auto"}:
        try:
            return SentenceTransformerEmbeddingProvider(settings.embedding_model)
        except Exception:
            if backend == "sentence-transformers":
                raise
            return HashEmbeddingProvider()
    return HashEmbeddingProvider()


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    dot = sum(left[i] * right[i] for i in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size]))
    right_norm = math.sqrt(sum(value * value for value in right[:size]))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
