"""Persistence provider selection.

``PERSISTENCE_PROVIDER`` decides which repository set backs the application:

- ``in_memory`` (default) keeps everything in process memory. This is the
  test/development fallback and requires no database.
- ``sqlalchemy`` persists to the database named by ``DATABASE_URL`` using
  synchronous SQLAlchemy. PostgreSQL is intended for real use; SQLite works
  for local development and automated tests.
"""

from abc import ABC, abstractmethod

from app.core.config import settings
from app.core.exceptions import ApplicationConfigurationError
from app.database.repositories import (
    InMemoryDocumentRepository,
    InMemoryEvidenceRepository,
    InMemoryInvestigationRepository,
    InMemorySourceRepository,
    InMemoryUserRepository,
)
from app.database.session import get_shared_session_factory
from app.database.uow import (
    InMemoryUnitOfWork,
    Repositories,
    SqlAlchemyUnitOfWork,
)


class PersistenceProvider(ABC):
    """Creates units of work and exposes whether transactions are required."""

    name: str

    @property
    @abstractmethod
    def requires_transaction(self) -> bool:
        """True when repository calls must run inside a DB transaction."""

    @abstractmethod
    def unit_of_work(self):
        """Return a unit of work exposing ``.repositories``."""

    @abstractmethod
    def reset(self) -> None:
        """Clear all persisted data for this provider (test helper)."""


class InMemoryPersistenceProvider(PersistenceProvider):
    name = "in_memory"

    def __init__(self) -> None:
        self._sources = InMemorySourceRepository()
        self._evidence = InMemoryEvidenceRepository()
        self._investigations = InMemoryInvestigationRepository(
            sources=self._sources,
            evidence=self._evidence,
        )
        self._repositories = Repositories(
            users=InMemoryUserRepository(),
            investigations=self._investigations,
            documents=InMemoryDocumentRepository(),
            sources=self._sources,
            evidence=self._evidence,
        )

    @property
    def requires_transaction(self) -> bool:
        return False

    def unit_of_work(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self._repositories)

    def reset(self) -> None:
        self._repositories.clear()


class SqlAlchemyPersistenceProvider(PersistenceProvider):
    name = "sqlalchemy"

    def __init__(self) -> None:
        factory = get_shared_session_factory()
        if factory is None:
            raise ApplicationConfigurationError(
                "PERSISTENCE_PROVIDER=sqlalchemy requires DATABASE_URL to be "
                "configured."
            )
        self._session_factory = factory

    @property
    def requires_transaction(self) -> bool:
        return True

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory)

    def reset(self) -> None:
        return None


_shared_provider: PersistenceProvider | None = None


def get_persistence_provider() -> PersistenceProvider:
    """Return the process-wide persistence provider for the active settings."""
    global _shared_provider
    requested = settings.PERSISTENCE_PROVIDER.strip().casefold()
    if requested == "sqlalchemy":
        if _shared_provider is None or _shared_provider.name != "sqlalchemy":
            _shared_provider = SqlAlchemyPersistenceProvider()
        return _shared_provider
    if requested in {"in_memory", "none", ""}:
        if _shared_provider is None or _shared_provider.name != "in_memory":
            _shared_provider = InMemoryPersistenceProvider()
        return _shared_provider
    raise ApplicationConfigurationError(
        "Unsupported persistence provider "
        f"'{settings.PERSISTENCE_PROVIDER}'. Supported providers: "
        "in_memory, sqlalchemy."
    )


def reset_persistence() -> None:
    """Clear in-memory persistence state (used by automated tests)."""
    global _shared_provider
    if _shared_provider is not None:
        _shared_provider.reset()


__all__ = [
    "InMemoryPersistenceProvider",
    "PersistenceProvider",
    "SqlAlchemyPersistenceProvider",
    "get_persistence_provider",
    "reset_persistence",
]
