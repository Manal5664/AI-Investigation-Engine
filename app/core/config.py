import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.core.exceptions import ApplicationConfigurationError


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


def _read_origins(name: str) -> tuple[str, ...]:
    """Read a comma-separated list of allowed CORS origins."""
    raw_value = os.getenv(name)
    if not raw_value:
        return ()
    return tuple(
        origin.strip()
        for origin in raw_value.split(",")
        if origin.strip()
    )


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
    VISION_PROVIDER: str = os.getenv("VISION_PROVIDER", "mock")
    VISION_MODEL: str = os.getenv("VISION_MODEL", "gemini-3.6-flash")
    DOCUMENT_MAX_UPLOAD_BYTES: int = _read_positive_int(
        "DOCUMENT_MAX_UPLOAD_BYTES",
        10 * 1024 * 1024,
    )
    DOCUMENT_MAX_PAGES: int = _read_positive_int(
        "DOCUMENT_MAX_PAGES",
        50,
    )
    DOCUMENT_MAX_PER_REQUEST: int = _read_positive_int(
        "DOCUMENT_MAX_PER_REQUEST",
        10,
    )
    DOCUMENT_STORE_PROVIDER: str = os.getenv(
        "DOCUMENT_STORE_PROVIDER",
        "in_memory",
    )
    EVIDENCE_INCLUDE_DOCUMENTS: bool = _read_bool(
        "EVIDENCE_INCLUDE_DOCUMENTS",
    )
    PERSISTENCE_PROVIDER: str = os.getenv(
        "PERSISTENCE_PROVIDER",
        "in_memory",
    )
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
    DATABASE_ECHO: bool = _read_bool("DATABASE_ECHO")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = _read_positive_int("PORT", 8000)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_JSON: bool = _read_bool("LOG_JSON")
    CORS_ALLOWED_ORIGINS: tuple[str, ...] = field(
        default_factory=lambda: _read_origins("CORS_ALLOWED_ORIGINS"),
    )

    def __post_init__(self) -> None:
        if self.RAG_CHUNK_OVERLAP >= self.RAG_CHUNK_SIZE:
            raise ValueError(
                "RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE"
            )

    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().casefold() == "production"


settings = Settings()


def validate_production_configuration(
    active: Settings | None = None,
) -> None:
    """Fail fast when production configuration is missing or unsafe.

    Development and testing environments are intentionally unconstrained so
    the in-memory providers and mock AI providers remain available. Production
    must use SQLAlchemy-backed persistence (PostgreSQL), disable DEBUG, and
    supply an API key whenever a Gemini-backed provider is selected.
    """
    cfg = active or settings
    if not cfg.is_production():
        return

    problems: list[str] = []
    persistence_provider = cfg.PERSISTENCE_PROVIDER.strip().casefold()
    database_url = cfg.DATABASE_URL.strip()
    if persistence_provider == "sqlalchemy":
        if not database_url:
            problems.append(
                "PERSISTENCE_PROVIDER=sqlalchemy requires a non-empty "
                "DATABASE_URL."
            )
        elif database_url.casefold().startswith("sqlite"):
            problems.append(
                "Production requires PostgreSQL; DATABASE_URL must not be a "
                "SQLite URL."
            )
    else:
        problems.append(
            "Production requires PERSISTENCE_PROVIDER=sqlalchemy backed by "
            "PostgreSQL. The in-memory persistence provider is process-local "
            "and is cleared on restart."
        )

    if cfg.DEBUG:
        problems.append("DEBUG must be false in production.")

    gemini_providers: dict[str, str] = {
        "LLM_PROVIDER": cfg.LLM_PROVIDER,
        "EVIDENCE_PROVIDER": cfg.EVIDENCE_PROVIDER,
        "SEARCH_PROVIDER": cfg.SEARCH_PROVIDER,
        "EMBEDDING_PROVIDER": cfg.EMBEDDING_PROVIDER,
        "VISION_PROVIDER": cfg.VISION_PROVIDER,
        "GRAPH_EXTRACTION_PROVIDER": cfg.GRAPH_EXTRACTION_PROVIDER,
    }
    gemini_provider_names = {"gemini", "gemini_grounded"}
    for name, value in gemini_providers.items():
        if (
            value.strip().casefold() in gemini_provider_names
            and not cfg.GEMINI_API_KEY
        ):
            problems.append(
                f"{name} selects a Gemini provider but GEMINI_API_KEY is not "
                "set."
            )

    if problems:
        raise ApplicationConfigurationError(
            "Production configuration is invalid: " + "; ".join(problems)
        )
