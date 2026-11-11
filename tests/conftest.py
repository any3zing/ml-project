"""Общие фикстуры тестов API: тестовый токен и фабрика клиентов."""

import secrets

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.settings import Settings


@pytest.fixture(scope="session")
def api_token():
    # случайный на каждый запуск: в коде нет «зашитого» секрета
    return secrets.token_urlsafe(32)

@pytest.fixture(scope="session")
def metrics_token():
    return secrets.token_urlsafe(32)


@pytest.fixture(scope="session")
def make_settings(api_token, metrics_token):
    def factory(**overrides):
        overrides.setdefault("api_token", api_token)
        overrides.setdefault("metrics_token", metrics_token)
        # большой лимит частоты: общие тесты не должны упираться в 429
        overrides.setdefault("rate_limit", 10_000)
        return Settings(**overrides)

    return factory


@pytest.fixture(scope="session")
def make_client(make_settings, api_token):
    def factory(**overrides):
        app = create_app(make_settings(**overrides))
        return TestClient(app, headers={"Authorization": f"Bearer {api_token}"})

    return factory
