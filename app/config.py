"""Application configuration via environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VERA_",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    team_name: str = "Vera Engine"
    contact_email: str = "team@example.com"
    team_members: list[str] = ["Developer"]
    version: str = "1.0.0"
    port: int = 8080
    model_descriptor: str = "rule-based-deterministic-v1"
    approach: str = (
        "Deterministic rule engine with category-specific fact-anchored templates. "
        "No LLM calls. Same input always produces same output."
    )
    submitted_at: str = "2026-04-26T08:00:00Z"


settings = Settings()
