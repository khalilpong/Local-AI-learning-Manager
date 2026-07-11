from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    db_path: Path
    library_dir: Path
    max_upload_bytes: int
    ai_mode: str
    ollama_base_url: str
    ollama_model: str
    embedding_backend: str
    embedding_model: str


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default
    return Path(value).expanduser()


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    data_dir = _path_from_env("MEMORY_DATA_DIR", root / "data")
    db_path = _path_from_env("MEMORY_DB_PATH", data_dir / "memory.db")
    library_dir = _path_from_env("MEMORY_LIBRARY_DIR", data_dir / "library")
    max_upload_mb = int(os.getenv("MEMORY_MAX_UPLOAD_MB", "100"))
    return Settings(
        host=os.getenv("MEMORY_HOST", "127.0.0.1"),
        port=int(os.getenv("MEMORY_PORT", "8000")),
        data_dir=data_dir,
        db_path=db_path,
        library_dir=library_dir,
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        ai_mode=os.getenv("MEMORY_AI_MODE", "auto").strip().lower(),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5"),
        embedding_backend=os.getenv("MEMORY_EMBEDDING_BACKEND", "auto").strip().lower(),
        embedding_model=os.getenv(
            "MEMORY_EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
    )
