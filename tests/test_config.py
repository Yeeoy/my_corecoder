from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Config, get_config


@pytest.fixture(autouse=True)
def clear_config_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("CORECODER_MODEL", "test-model")

    get_config.cache_clear()
    yield
    get_config.cache_clear()


def test_lru_cache():
    a = get_config()
    b = get_config()
    assert a is b


def test_cache_clear():
    a = get_config()
    get_config.cache_clear()
    b = get_config()
    assert a is not b


def test_env_test(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("CORECODER_MODEL", "test-model")

    get_config.cache_clear()

    assert get_config().OPENAI_BASE_URL == "https://api.openai.com/v1"
    assert get_config().OPENAI_API_KEY == "test-key"
    assert get_config().CORECODER_MODEL == "test-model"


def test_validation(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("CORECODER_MODEL", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    new_config = {**Config.model_config, "env_file": Path("/nonexistent/.env")}
    monkeypatch.setattr(Config, "model_config", new_config)

    with pytest.raises(ValidationError):
        Config()


def test_optional_variables(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    new_config = {**Config.model_config, "env_file": Path("/nonexistent/.env")}
    monkeypatch.setattr(Config, "model_config", new_config)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("CORECODER_MODEL", "test-model")

    a = Config()
    assert a.TAVILY_API_KEY is None


def test_type():
    a = get_config()
    assert isinstance(a, Config)
