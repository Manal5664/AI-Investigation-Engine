"""Async adapter that exposes sync repositories to async application code.

SQLAlchemy is synchronous, so calls are marshalled onto a worker thread via
``asyncio.to_thread``. In-memory calls run inline (they do no I/O). Every
call opens its own transaction, committing on success and rolling back on
failure, so service code never manages sessions directly.
"""

import asyncio

from app.database.provider import PersistenceProvider
from app.documents.models import StoredDocument


class DocumentPersistenceGateway:
    """Document-repository access for async callers (ingestion routes)."""

    def __init__(self, provider: PersistenceProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def find_by_hash(self, content_hash: str) -> StoredDocument | None:
        return await self._run(
            lambda uow: uow.repositories.documents.find_by_hash(content_hash)
        )

    async def get(self, document_id: str) -> StoredDocument | None:
        return await self._run(
            lambda uow: uow.repositories.documents.get(document_id)
        )

    async def save(self, stored: StoredDocument) -> None:
        await self._run(lambda uow: uow.repositories.documents.save(stored))

    async def delete(self, document_id: str) -> bool:
        return await self._run(
            lambda uow: uow.repositories.documents.delete(document_id)
        )

    async def _run(self, fn):
        if self._provider.requires_transaction:
            def run() -> object:
                uow = self._provider.unit_of_work()
                try:
                    result = fn(uow)
                    uow.commit()
                    return result
                except Exception:
                    uow.rollback()
                    raise
                finally:
                    uow.close()

            return await asyncio.to_thread(run)
        uow = self._provider.unit_of_work()
        try:
            return fn(uow)
        finally:
            uow.close()


__all__ = ["DocumentPersistenceGateway"]
