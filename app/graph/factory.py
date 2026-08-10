from app.core.config import Settings, settings
from app.core.exceptions import ApplicationConfigurationError
from app.graph.base import GraphStore
from app.graph.in_memory import InMemoryGraphStore


_shared_stores: dict[str, GraphStore] = {}


def create_graph_store(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> GraphStore:
    active_config = config or settings
    requested_provider = (
        provider_name or active_config.GRAPH_STORE_PROVIDER
    )
    normalized_name = requested_provider.strip().casefold()
    if normalized_name == "in_memory":
        return InMemoryGraphStore()
    raise ApplicationConfigurationError(
        "Unsupported graph store "
        f"'{requested_provider}'. Supported stores: in_memory."
    )


def get_graph_store(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> GraphStore:
    active_config = config or settings
    requested_provider = (
        provider_name or active_config.GRAPH_STORE_PROVIDER
    )
    normalized_name = requested_provider.strip().casefold()
    if normalized_name not in _shared_stores:
        _shared_stores[normalized_name] = create_graph_store(
            normalized_name,
            active_config,
        )
    return _shared_stores[normalized_name]


async def reset_graph_stores() -> None:
    for store in _shared_stores.values():
        await store.clear()
    _shared_stores.clear()
