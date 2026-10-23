from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import api.dependencies as deps
from api.app import app
from infrastructure.cache.redis_cache import RedisCache


@pytest.fixture(autouse=True)
def disable_redis_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """API-тесты без Redis: кэш отключён, данные всегда из БД."""
    deps.get_redis_cache.cache_clear()
    monkeypatch.setattr(
        deps,
        "get_redis_cache",
        lambda: RedisCache("redis://localhost:6379/0", enabled=False),
    )


@pytest.fixture(autouse=True)
def stub_image_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = MagicMock()
    storage.upload_bytes.return_value = "cards/test-upload.png"
    storage.get_presigned_url.return_value = "http://test.local/cards/default.png"
    storage.get_download_url.return_value = "http://test.local/cards/test-upload.png"
    deps.get_image_storage.cache_clear()
    monkeypatch.setattr(deps, "get_image_storage", lambda: storage)


@pytest.fixture()
def api_client(session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def client(api_client: TestClient) -> TestClient:
    return api_client
