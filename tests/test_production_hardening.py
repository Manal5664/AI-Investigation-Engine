"""Tests for Phase 12 production-hardening behavior.

These tests run fully offline: providers are the mock defaults enforced by
``tests/conftest.py``, and no Gemini/search calls are made.
"""

import re
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings, validate_production_configuration
from app.core.exceptions import ApplicationConfigurationError
from app.core.middleware import (
    MAX_REQUEST_ID_LENGTH,
    REQUEST_ID_HEADER,
    SECURITY_HEADERS,
)
from app.main import app

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _production_settings(**overrides):
    base = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "PERSISTENCE_PROVIDER": "sqlalchemy",
        "DATABASE_URL": (
            "postgresql+psycopg://investigator:secret@db:5432/"
            "ai_investigation"
        ),
        "GEMINI_API_KEY": None,
    }
    base.update(overrides)
    return replace(settings, **base)


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


def test_liveness_endpoint(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_endpoint_ready_with_in_memory_provider(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["persistence_provider"] == "in_memory"
    assert any(
        check["name"] == "persistence_provider" and check["ok"]
        for check in payload["checks"]
    )


def test_legacy_health_endpoint_still_works(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["environment"] == "development"


# ---------------------------------------------------------------------------
# Request ID
# ---------------------------------------------------------------------------


def test_request_id_is_generated_when_absent(client):
    response = client.get("/")
    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id
    assert _SAFE_ID_RE.match(request_id) is not None


def test_valid_incoming_request_id_is_preserved(client):
    incoming = "case-abc_123.xyz"
    response = client.get("/", headers={REQUEST_ID_HEADER: incoming})
    assert response.headers.get(REQUEST_ID_HEADER) == incoming


def test_unsafe_incoming_request_id_is_rejected(client):
    incoming = "../etc/passwd<script>"
    response = client.get("/", headers={REQUEST_ID_HEADER: incoming})
    actual = response.headers.get(REQUEST_ID_HEADER)
    assert actual != incoming
    assert _SAFE_ID_RE.match(actual) is not None


def test_oversized_incoming_request_id_is_rejected(client):
    incoming = "x" * (MAX_REQUEST_ID_LENGTH + 1)
    response = client.get("/", headers={REQUEST_ID_HEADER: incoming})
    actual = response.headers.get(REQUEST_ID_HEADER)
    assert actual != incoming
    assert len(actual) <= MAX_REQUEST_ID_LENGTH


def test_request_id_returned_on_error_responses(client):
    response = client.get("/definitely-not-a-route")
    assert response.status_code == 404
    assert response.headers.get(REQUEST_ID_HEADER)


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


def test_security_headers_present_on_all_responses(client):
    response = client.get("/")
    headers = response.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "same-origin"
    assert "Content-Security-Policy" in headers


def test_csp_allows_cdn_frontend_resources():
    csp = SECURITY_HEADERS["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in csp
    assert "https://fonts.googleapis.com" in csp
    assert "https://fonts.gstatic.com" in csp
    assert "default-src 'self'" in csp


# ---------------------------------------------------------------------------
# Production error handling
# ---------------------------------------------------------------------------


def test_production_error_response_does_not_leak_traceback():
    from fastapi import FastAPI

    from app.main import internal_error_handler

    mini = FastAPI()
    mini.add_exception_handler(Exception, internal_error_handler)

    @mini.get("/_boom")
    def boom():
        raise ValueError("classified D:\\secrets\\config.py leak check")

    with TestClient(mini, raise_server_exceptions=False) as mini_client:
        response = mini_client.get("/_boom")

    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "internal_error"
    assert payload["message"] == "An internal server error occurred."
    assert payload["details"] == []
    body = response.text
    assert "Traceback" not in body
    assert "leak check" not in body
    assert "secrets" not in body


# ---------------------------------------------------------------------------
# Production configuration validation
# ---------------------------------------------------------------------------


def test_production_rejects_in_memory_persistence():
    invalid = _production_settings(
        PERSISTENCE_PROVIDER="in_memory",
        DATABASE_URL="",
    )
    with pytest.raises(ApplicationConfigurationError) as exc_info:
        validate_production_configuration(invalid)
    assert "in-memory persistence" in str(exc_info.value)


def test_production_rejects_missing_database_url():
    invalid = _production_settings(PERSISTENCE_PROVIDER="sqlalchemy", DATABASE_URL="")
    with pytest.raises(ApplicationConfigurationError) as exc_info:
        validate_production_configuration(invalid)
    assert "DATABASE_URL" in str(exc_info.value)


def test_production_rejects_sqlite_database_url():
    invalid = _production_settings(
        DATABASE_URL="sqlite:///./ai_investigation.db"
    )
    with pytest.raises(ApplicationConfigurationError) as exc_info:
        validate_production_configuration(invalid)
    assert "SQLite" in str(exc_info.value)


def test_production_rejects_debug_mode():
    invalid = _production_settings(DEBUG=True)
    with pytest.raises(ApplicationConfigurationError) as exc_info:
        validate_production_configuration(invalid)
    assert "DEBUG" in str(exc_info.value)


def test_production_requires_gemini_key_when_provider_selected():
    invalid = _production_settings(LLM_PROVIDER="gemini", GEMINI_API_KEY=None)
    with pytest.raises(ApplicationConfigurationError) as exc_info:
        validate_production_configuration(invalid)
    assert "GEMINI_API_KEY" in str(exc_info.value)


def test_production_accepts_valid_postgresql_configuration():
    validate_production_configuration(_production_settings())


def test_development_is_not_constrained():
    dev = replace(settings, ENVIRONMENT="development")
    validate_production_configuration(dev)


# ---------------------------------------------------------------------------
# Existing routes unaffected
# ---------------------------------------------------------------------------


def test_frontend_routes_render_with_hardening(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"EvidenceAI" in response.content


def test_api_routes_unaffected(client):
    response = client.get("/api/v1/investigations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
