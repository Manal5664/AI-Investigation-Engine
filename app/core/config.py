import os
from dataclasses import dataclass


def _read_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "AI Investigation Engine")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.2.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = _read_bool("DEBUG")


settings = Settings()
