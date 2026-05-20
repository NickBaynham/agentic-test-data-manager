"""Unit tests for the ATDM agent stub.

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
    assert body["service"] == "test-data-agent"
    assert body["planner_mode"] == "rule"


def test_metrics_returns_prometheus_text() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text
    assert "# HELP atdm_up" in text
    assert "# TYPE atdm_up gauge" in text
    assert "atdm_up 1" in text


def test_unknown_route_returns_404() -> None:
    response = client.get("/scenarios/list")
    assert response.status_code == 404
