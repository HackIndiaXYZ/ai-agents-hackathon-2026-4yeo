from functools import lru_cache
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
import yaml


CONFIG_PATH = Path(os.getenv("ARGUS_CONFIG_PATH", "config/app.yaml"))


class AppSettings(BaseModel):
    name: str
    version: str
    description: str
    api_prefix: str = "/api"
    environment_env: str = "APP_ENVIRONMENT"
    default_environment: str = "development"

    @property
    def environment(self) -> str:
        return os.getenv(self.environment_env, self.default_environment)


class DatabaseSettings(BaseModel):
    url_env: str
    default_url: str

    @property
    def url(self) -> str:
        return os.getenv(self.url_env, self.default_url)


class LiveKitSettings(BaseModel):
    url_env: str
    api_key_env: str
    api_secret_env: str
    default_url: str
    room_prefix: str
    session_timeout_seconds: int = 900

    @property
    def url(self) -> str:
        return os.getenv(self.url_env, self.default_url)

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "")

    @property
    def api_secret(self) -> str:
        return os.getenv(self.api_secret_env, "")


class AdaptionSettings(BaseModel):
    api_key_env: str
    base_url_env: str
    default_base_url: str = ""
    export_dir: str = "artifacts/datasets"

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "")

    @property
    def base_url(self) -> str:
        return os.getenv(self.base_url_env, self.default_base_url)


class WorkflowSettings(BaseModel):
    supported_languages: list[str] = Field(default_factory=list)
    supported_domains: list[str] = Field(default_factory=list)
    violation_labels: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    app: AppSettings
    database: DatabaseSettings
    livekit: LiveKitSettings
    adaption: AdaptionSettings
    workflow: WorkflowSettings


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("Configuration file must contain a mapping at the root")
    return raw


@lru_cache
def get_settings() -> Settings:
    return Settings.model_validate(_read_yaml(CONFIG_PATH))
