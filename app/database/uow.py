"""Unit of work: clean transaction boundaries around repository access."""

from app.database.repositories import (
    DocumentRepository,
    EvidenceRepository,
    InvestigationRepository,
    SourceRepository,
    UserRepository,
)


class Repositories:
    """Bundled repository set exposed by a unit of work."""

    def __init__(
        self,
        *,
        users: UserRepository,
        investigations: InvestigationRepository,
        documents: DocumentRepository,
        sources: SourceRepository,
        evidence: EvidenceRepository,
    ) -> None:
        self.users = users
        self.investigations = investigations
        self.documents = documents
        self.sources = sources
        self.evidence = evidence

    def clear(self) -> None:
        for repository in (
            self.users,
            self.investigations,
            self.documents,
            self.sources,
            self.evidence,
        ):
            repository.clear()


class SqlAlchemyUnitOfWork:
    """SQLAlchemy transaction scope.

    Constructing the unit of work opens a session and binds the repository
    set, so it can be used either as a context manager::

        with SqlAlchemyUnitOfWork(session_factory) as uow:
            uow.repositories.users.create(record)
            uow.commit()

    or with explicit boundaries (the async route helpers marshall the work
    onto a worker thread and manage the scope themselves)::

        uow = SqlAlchemyUnitOfWork(session_factory)
        try:
            uow.repositories.users.create(record)
            uow.commit()
        except Exception:
            uow.rollback()
            raise
        finally:
            uow.close()

    Commits on clean context exit, rolls back when an exception escapes, and
    always closes the session.
    """

    def __init__(self, session_factory) -> None:
        from app.database.repositories.sqlalchemy import (
            SqlAlchemyDocumentRepository,
            SqlAlchemyEvidenceRepository,
            SqlAlchemyInvestigationRepository,
            SqlAlchemySourceRepository,
            SqlAlchemyUserRepository,
        )

        self.session = session_factory()
        self.repositories = Repositories(
            users=SqlAlchemyUserRepository(self.session),
            investigations=SqlAlchemyInvestigationRepository(self.session),
            documents=SqlAlchemyDocumentRepository(self.session),
            sources=SqlAlchemySourceRepository(self.session),
            evidence=SqlAlchemyEvidenceRepository(self.session),
        )

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None


class InMemoryUnitOfWork:
    """No-op transaction scope around the shared in-memory repositories."""

    def __init__(self, repositories: Repositories) -> None:
        self.repositories = repositories

    def __enter__(self) -> "InMemoryUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


__all__ = [
    "InMemoryUnitOfWork",
    "Repositories",
    "SqlAlchemyUnitOfWork",
]
