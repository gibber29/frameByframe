import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://framebyframe:framebyframe@localhost:5432/framebyframe_test",
)

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_health_check() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
