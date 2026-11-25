"""Configuration via environment / .env, powered by pydantic-settings.

  CONTEXTBOSS_DB       store path (default ~/.contextboss/context.db)
  CONTEXTBOSS_BUDGET   default assembly budget (default 8000)
  CONTEXTBOSS_RESERVE  default output reserve (default 1000)
"""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONTEXTBOSS_", env_file=".env", extra="ignore"
    )

    db: str = os.path.join(os.path.expanduser("~"), ".contextboss", "context.db")
    budget: int = 8000
    reserve: int = 1000

    def manager_kwargs(self) -> dict:
        return {"budget": self.budget, "output_reserve": self.reserve}


def load_settings() -> Settings:
    return Settings()
