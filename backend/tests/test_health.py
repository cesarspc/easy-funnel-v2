"""Smoke tests for the FastAPI app factory and its health route.

`TestClient` only runs the app's lifespan (startup/shutdown) when used as a
context manager. The two tests below are split accordingly:

- `test_health_route_returns_expected_shape` never enters the context
  manager, so it exercises route logic only and needs no database.
- `test_app_boots_connects_to_the_database_and_health_responds` enters the
  context manager, so it exercises the real startup path added in task 2.1
  (`connect_db()`/`disconnect_db()` via the app lifespan) and requires
  `DATABASE_URL` to point at a reachable database.
"""

from app.main import create_app
from fastapi.testclient import TestClient

from tests.db.conftest import requires_database


def test_health_route_returns_expected_shape() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "version" in body


@requires_database
def test_app_boots_connects_to_the_database_and_health_responds() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
