"""Unit tests for planner mode and auth middleware.

Uses TestClient — no Docker required. The catalog_store and audit_writer
modules are patched so MinIO is not contacted from a unit test.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client_with_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ATDM_API_TOKEN", "test-token")
    monkeypatch.setenv("ATDM_PLANNER", "rule")
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_llm_mode_returns_501(monkeypatch: pytest.MonkeyPatch) -> None:
    """ATDM_PLANNER=llm short-circuits POST /test-data/requests to 501."""
    monkeypatch.setenv("ATDM_API_TOKEN", "test-token")
    monkeypatch.setenv("ATDM_PLANNER", "llm")
    from app.main import app

    with TestClient(app) as c:
        resp = c.post(
            "/test-data/requests",
            headers={"authorization": "Bearer test-token"},
            json={"scenario": "active_member_clean"},
        )
    assert resp.status_code == 501
    body = resp.json()
    assert body["detail"]["error"]["code"] == "LLM_MODE_NOT_ENABLED"


def test_post_without_auth_returns_401(client_with_env: TestClient) -> None:
    resp = client_with_env.post(
        "/test-data/requests",
        json={"scenario": "active_member_clean"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_post_with_wrong_token_returns_401(client_with_env: TestClient) -> None:
    resp = client_with_env.post(
        "/test-data/requests",
        headers={"authorization": "Bearer wrong-token"},
        json={"scenario": "active_member_clean"},
    )
    assert resp.status_code == 401


def test_get_health_does_not_require_auth(client_with_env: TestClient) -> None:
    resp = client_with_env.get("/health")
    assert resp.status_code == 200


def test_get_metrics_does_not_require_auth(client_with_env: TestClient) -> None:
    resp = client_with_env.get("/metrics")
    assert resp.status_code == 200
    assert "atdm_up 1" in resp.text


def test_unknown_scenario_returns_404(client_with_env: TestClient) -> None:
    """SCENARIO_NOT_FOUND fires before any MinIO call, so it works as a unit test."""

    # The endpoint writes one audit event before looking up the scenario, so we
    # patch the catalog client to a noop to keep the test offline.
    def fake_make_client() -> Any:
        class _NoOp:
            def get_object(self, *_a: Any, **_kw: Any) -> Any:
                raise FileNotFoundError

            def put_object(self, *_a: Any, **_kw: Any) -> None:
                return None

        return _NoOp()

    with (
        patch("app.catalog.store.make_minio_client", fake_make_client),
        # Audit writer also calls get_object/put_object; the no-op client above
        # handles both. NoSuchKey errors are silently treated as "no prior events".
        patch("app.audit.writer.append_event", lambda *a, **kw: None),
    ):
        resp = client_with_env.post(
            "/test-data/requests",
            headers={"authorization": "Bearer test-token"},
            json={"scenario": "definitely-not-a-real-scenario"},
        )
    assert resp.status_code == 404
    assert "SCENARIO_NOT_FOUND" in resp.text
