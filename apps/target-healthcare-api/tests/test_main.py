"""Unit tests for the Target Healthcare API stub.

These use fastapi.testclient.TestClient — no docker required.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "target-healthcare-api"


def test_health_is_json() -> None:
    response = client.get("/health")
    assert response.headers["content-type"].startswith("application/json")


def test_unknown_route_returns_404() -> None:
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
