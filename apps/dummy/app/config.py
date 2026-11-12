"""Application settings (12-factor style, loaded from .env when present)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "TiendaDemo"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    session_secret: str = "laboratorio-qa-demo-secret"

    # Seeded-defect profile: "none" (clean app) | "default" (all bugs on)
    bug_profile: str = "none"
    # Coma-separated bug ids force-disabled, e.g. "BUG-02,BUG-07"
    lab_disabled_bugs: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
