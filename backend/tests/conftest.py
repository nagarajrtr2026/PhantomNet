import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        chroma_persist_directory=str(tmp_path / "chroma"),
        chroma_collection="test_context",
        event_history_size=100,
        max_websocket_clients=5,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
