import pytest
from fastapi.testclient import TestClient

from history.server.app import create_app


@pytest.fixture
def api(tmp_path):
    with TestClient(create_app(tmp_path / "history.db")) as client:
        yield client
