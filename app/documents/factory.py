"""Resolve the document store from application settings."""

from app.core.config import Settings, settings
from app.core.exceptions import ApplicationConfigurationError
from app.documents.base import DocumentStore
from app.documents.store import InMemoryDocumentStore

_shared_stores: dict[str, DocumentStore] = {}


def create_document_store(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> DocumentStore:
    active_config = config or settings
    requested_provider = (
        provider_name or active_config.DOCUMENT_STORE_PROVIDER
    )
    normalized_name = requested_provider.strip().casefold()
    if normalized_name == "in_memory":
        return InMemoryDocumentStore()
    raise ApplicationConfigurationError(
        "Unsupported document store "
        f"'{requested_provider}'. Supported stores: in_memory."
    )


def get_document_store(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> DocumentStore:
    active_config = config or settings
    requested_provider = (
        provider_name or active_config.DOCUMENT_STORE_PROVIDER
    )
    normalized_name = requested_provider.strip().casefold()
    if normalized_name not in _shared_stores:
        _shared_stores[normalized_name] = create_document_store(
            normalized_name,
            active_config,
        )
    return _shared_stores[normalized_name]


async def reset_document_stores() -> None:
    for store in _shared_stores.values():
        await store.clear()
    _shared_stores.clear()


__all__ = [
    "create_document_store",
    "get_document_store",
    "reset_document_stores",
]
