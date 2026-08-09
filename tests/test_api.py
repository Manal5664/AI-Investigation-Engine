import asyncio
import json
from typing import Any

from app.main import app


async def _asgi_request(
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    payload = json.dumps(body).encode() if body is not None else b""
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {
                "type": "http.request",
                "body": payload,
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    headers: list[tuple[bytes, bytes]] = []
    if body is not None:
        headers.append((b"content-type", b"application/json"))

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    await app(scope, receive, send)

    status = next(
        message["status"]
        for message in messages
        if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return status, json.loads(response_body)


def _request(
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, Any]]:
    return asyncio.run(_asgi_request(method, path, body))


def test_root_and_health_endpoints() -> None:
    root_status, root_body = _request("GET", "/")
    health_status, health_body = _request("GET", "/health")

    assert root_status == 200
    assert root_body == {
        "message": "AI Investigation Engine is running successfully"
    }
    assert health_status == 200
    assert health_body["status"] == "healthy"
    assert health_body["environment"] == "development"


def test_valid_standard_api_request() -> None:
    status, body = _request(
        "POST",
        "/api/v1/investigations/plan",
        {"query": "Research renewable energy storage"},
    )

    assert status == 200
    assert body["status"] == "investigation_planned"
    assert body["plan"]["depth"] == "standard"
    assert len(body["plan"]["sub_questions"]) == 5


def test_empty_query_returns_clear_422() -> None:
    status, body = _request(
        "POST",
        "/api/v1/investigations/plan",
        {"query": "   "},
    )

    assert status == 422
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    assert body["details"][0]["field"] == "query"


def test_invalid_depth_returns_clear_422() -> None:
    status, body = _request(
        "POST",
        "/api/v1/investigations/plan",
        {
            "query": "A valid investigation query",
            "depth": "extreme",
        },
    )

    assert status == 422
    assert body["code"] == "validation_error"
    assert body["details"][0]["field"] == "depth"
