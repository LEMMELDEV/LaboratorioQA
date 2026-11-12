"""Settings for the QA agent (12-factor, .env aware)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="AGENT_",
        extra="ignore",
    )

    # Base URL the agent is allowed to explore. The agent NEVER receives routes.
    base_url: str = "http://127.0.0.1:8000"
    headless: bool = True
    per_action_timeout_ms: int = 10_000

    # Crawler policies
    max_pages: int = 30
    max_depth: int = 2
    # Paths the UI crawler must never visit (lab panel would leak ground truth).
    exclude_prefixes: str = "/api,/lab,/static"

    # Budgets / guardrails (used by M4+)
    max_steps: int = 60
    max_minutes: int = 10

    artifacts_dir: Path = REPO_ROOT / "artifacts"
    app_dir: Path = REPO_ROOT / "apps" / "dummy"


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()


agent_settings = get_agent_settings()
