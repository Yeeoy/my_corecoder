from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Config(BaseSettings):
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str
    CORECODER_MODEL: str

    TAVILY_API_KEY: str | None = None

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_config() -> Config:
    return Config()
