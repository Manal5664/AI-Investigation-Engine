"""Engine and session management for SQLAlchemy-backed persistence.

The repository layer is synchronous on purpose: sync SQLAlchemy works with
both PostgreSQL (psycopg) and SQLite, keeps the codebase free of two async
drivers, and is easy to run in FastAPI's thread pool and from automated
tests. Async callers must hop to a worker thread (``asyncio.to_thread``)
when talking to these repositories.

No database is configured when ``DATABASE_URL`` is empty; the in-memory
repository fallback is used instead.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.exceptions import ApplicationConfigurationError


def normalize_database_url(database_url: str) -> str:
    """Point postgres URLs at the psycopg driver and default to SQLite."""
    url = database_url.strip()
    if not url:
        raise ApplicationConfigurationError(
            "DATABASE_URL is not configured; set it to a PostgreSQL or "
            "SQLite URL to enable database-backed persistence."
        )
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        if "+" not in url.split("://", 1)[1]:
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def create_database_engine(
    database_url: str | None = None,
    *,
    echo: bool | None = None,
) -> Engine:
    """Build a SQLAlchemy engine, tolerating both PostgreSQL and SQLite."""
    active_url = normalize_database_url(
        database_url if database_url is not None else settings.DATABASE_URL
    )
    active_echo = (
        settings.DATABASE_ECHO if echo is None else echo
    )
    engine_kwargs: dict[str, object] = {"echo": active_echo}
    if active_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in active_url:
            engine_kwargs["poolclass"] = StaticPool
    return create_engine(active_url, **engine_kwargs)


def create_session_factory(
    database_url: str | None = None,
) -> sessionmaker[Session]:
    """Build a session factory bound to a database engine."""
    engine = create_database_engine(database_url)
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


_shared_engine: Engine | None = None
_shared_session_factory: sessionmaker[Session] | None = None


def get_shared_engine() -> Engine | None:
    """Return the process-wide engine, or None when no DB is configured."""
    if not settings.DATABASE_URL:
        return None
    global _shared_engine
    if _shared_engine is None:
        _shared_engine = create_database_engine()
    return _shared_engine


def get_shared_session_factory() -> sessionmaker[Session] | None:
    """Return the process-wide session factory, or None when not configured."""
    if not settings.DATABASE_URL:
        return None
    global _shared_session_factory
    if _shared_session_factory is None:
        engine = get_shared_engine()
        assert engine is not None
        _shared_session_factory = sessionmaker(
            bind=engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )
    return _shared_session_factory


def reset_shared_database() -> None:
    """Drop cached engine/session factory (used by tests)."""
    global _shared_engine, _shared_session_factory
    if _shared_engine is not None:
        _shared_engine.dispose()
    _shared_engine = None
    _shared_session_factory = None


def create_all_tables(database_url: str | None = None) -> None:
    """Create all registered tables (dev/test convenience; use Alembic in prod)."""
    from app.database.models import Base as ModelsBase

    engine = create_database_engine(database_url)
    ModelsBase.metadata.create_all(engine)
    engine.dispose()


@contextmanager
def session_scope(
    database_url: str | None = None,
) -> Iterator[Session]:
    """Yield a committed-or-rolled-back session for manual use."""
    factory = (
        get_shared_session_factory()
        if database_url is None and settings.DATABASE_URL
        else create_session_factory(database_url)
    )
    assert factory is not None
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "create_all_tables",
    "create_database_engine",
    "create_session_factory",
    "get_shared_engine",
    "get_shared_session_factory",
    "normalize_database_url",
    "reset_shared_database",
    "session_scope",
]
