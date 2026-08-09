import os
from dataclasses import dataclass


def _read_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().casefold() in {"1", "true", "yes", "on"}


def _read_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "AI Investigation Engine")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.4.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = _read_bool("DEBUG")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "mock-investigator")
    LLM_TIMEOUT_SECONDS: int = _read_positive_int(
        "LLM_TIMEOUT_SECONDS",
        60,
    )


settings = Settings()
