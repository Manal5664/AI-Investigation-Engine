from app.core.config import Settings, settings
from app.core.exceptions import ApplicationConfigurationError
from app.rag.vectorstore.base import VectorStore
from app.rag.vectorstore.in_memory import InMemoryVectorStore


_shared_stores: dict[str, VectorStore] = {}


def create_vector_store(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> VectorStore:
    active_config = config or settings
    requested_provider = (
        provider_name or active_config.VECTOR_STORE_PROVIDER
    )
    normalized_name = requested_provider.strip().casefold()
    if normalized_name == "in_memory":
        return InMemoryVectorStore()
    raise ApplicationConfigurationError(
        "Unsupported vector store "
        f"'{requested_provider}'. Supported stores: in_memory."
    )


def get_vector_store(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> VectorStore:
    active_config = config or settings
    requested_provider = (
        provider_name or active_config.VECTOR_STORE_PROVIDER
    )
    normalized_name = requested_provider.strip().casefold()
    if normalized_name not in _shared_stores:
        _shared_stores[normalized_name] = create_vector_store(
            normalized_name,
            active_config,
        )
    return _shared_stores[normalized_name]


async def reset_vector_stores() -> None:
    for store in _shared_stores.values():
        await store.clear()
    _shared_stores.clear()
