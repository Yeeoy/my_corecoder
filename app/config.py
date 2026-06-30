from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
print(f"Loading environment from {ENV_PATH}")
if not ENV_PATH.exists():
    raise ValueError(f"{ENV_PATH} does not exist")


class Config(BaseSettings):
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str
    CORECODER_MODEL: str

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )


config = Config()
