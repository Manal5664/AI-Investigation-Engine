import os
from dataclasses import replace
from pathlib import Path

from pytest import MonkeyPatch

from app.core.config import _load_env_file, settings


def test_env_file_loads_missing_values(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# Test configuration",
                "export LLM_PROVIDER=gemini",
                'LLM_MODEL="test-gemini-model"',
                "GEMINI_API_KEY=test-key",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    _load_env_file(env_file)

    assert os.environ["LLM_PROVIDER"] == "gemini"
    assert os.environ["LLM_MODEL"] == "test-gemini-model"
    assert os.environ["GEMINI_API_KEY"] == "test-key"


def test_env_file_does_not_override_process_environment(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=gemini\n", encoding="utf-8")
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    _load_env_file(env_file)

    assert os.environ["LLM_PROVIDER"] == "mock"


def test_settings_repr_does_not_expose_gemini_api_key() -> None:
    configured_settings = replace(
        settings,
        GEMINI_API_KEY="test-secret-that-must-not-appear",
    )

    assert "test-secret-that-must-not-appear" not in repr(
        configured_settings
    )
