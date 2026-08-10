import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path | None = None) -> None:
    """Load local settings without overriding explicit environment values."""
    env_file = path
    if env_file is None:
        configured_path = os.getenv("APP_ENV_FILE")
        if configured_path is not None:
            if not configured_path.strip():
                return
            configured_file = Path(configured_path).expanduser()
            env_file = (
                configured_file
                if configured_file.is_absolute()
                else PROJECT_ROOT / configured_file
            )
        else:
            env_file = PROJECT_ROOT / ".env"

    load_dotenv(dotenv_path=env_file, override=False)


_load_env_file()


def _read_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().casefold() in {"1", "true", "yes", "on"}


def _read_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _read_non_negative_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = int(raw_value)
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def _read_optional_secret(name: str) -> str | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value or None


@dataclass(frozen=True, slots=True)
class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "AI Investigation Engine")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.6.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = _read_bool("DEBUG")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "mock-investigator")
    LLM_TIMEOUT_SECONDS: int = _read_positive_int(
        "LLM_TIMEOUT_SECONDS",
        60,
    )
    GEMINI_API_KEY: str | None = field(
        default_factory=lambda: _read_optional_secret("GEMINI_API_KEY"),
        repr=False,
    )
    EVIDENCE_PROVIDER: str = os.getenv("EVIDENCE_PROVIDER", "mock")
    EVIDENCE_MODEL: str = os.getenv(
        "EVIDENCE_MODEL",
        "gemini-3.6-flash",
    )
    SEARCH_PROVIDER: str = os.getenv("SEARCH_PROVIDER", "mock")
    SEARCH_MODEL: str = os.getenv("SEARCH_MODEL", "gemini-3.6-flash")
    SEARCH_MAX_RESULTS: int = _read_positive_int("SEARCH_MAX_RESULTS", 5)
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "mock")
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL",
        "mock-embedding-v1",
    )
    VECTOR_STORE_PROVIDER: str = os.getenv(
        "VECTOR_STORE_PROVIDER",
        "in_memory",
    )
    RAG_CHUNK_SIZE: int = _read_positive_int("RAG_CHUNK_SIZE", 1000)
    RAG_CHUNK_OVERLAP: int = _read_non_negative_int(
        "RAG_CHUNK_OVERLAP",
        200,
    )
    GRAPH_STORE_PROVIDER: str = os.getenv(
        "GRAPH_STORE_PROVIDER",
        "in_memory",
    )
    GRAPH_EXTRACTION_PROVIDER: str = os.getenv(
        "GRAPH_EXTRACTION_PROVIDER",
        "mock",
    )
    GRAPH_EXTRACTION_MODEL: str = os.getenv(
        "GRAPH_EXTRACTION_MODEL",
        "mock-graph-extractor",
    )

    def __post_init__(self) -> None:
        if self.RAG_CHUNK_OVERLAP >= self.RAG_CHUNK_SIZE:
            raise ValueError(
                "RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE"
            )


settings = Settings()
