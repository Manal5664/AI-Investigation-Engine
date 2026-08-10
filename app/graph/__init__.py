from typing import Any

_LAZY_EXPORTS: dict[str, str] = {
    "GraphBuilder": "app.graph.builder",
    "GraphBuilderError": "app.graph.builder",
    "GraphStore": "app.graph.base",
    "create_graph_store": "app.graph.factory",
    "get_graph_store": "app.graph.factory",
    "reset_graph_stores": "app.graph.factory",
    "InMemoryGraphStore": "app.graph.in_memory",
    "GraphEdge": "app.graph.models",
    "GraphNeighbor": "app.graph.models",
    "GraphNode": "app.graph.models",
    "GraphNodeType": "app.graph.models",
    "GraphPath": "app.graph.models",
    "GraphProvenance": "app.graph.models",
    "GraphRelationType": "app.graph.models",
    "GraphStats": "app.graph.models",
    "GraphRetriever": "app.graph.retriever",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = list(_LAZY_EXPORTS)
