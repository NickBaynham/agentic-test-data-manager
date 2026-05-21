"""Phase 8 integration tests — audit HTML UI + Prometheus metrics.

Covers:
  - E3: HTML page renders for a known run with all required sections.
  - E3: 404 page renders for an unknown run_id.
  - E3: page size stays under 100 KB.
  - Observability: /metrics emits the new audit counters.
"""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

ATDM = "http://localhost:18001"
SUT = "http://localhost:18000"
AUTH = "Bearer dev-token-change-me"


def _request(
    method: str,
    base: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    auth: bool = True,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {}
    if body is not None:
        headers["content-type"] = "application/json"
    if auth:
        headers["authorization"] = AUTH
    req = urllib.request.Request(  # noqa: S310
        f"{base}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _get_html(path: str) -> tuple[int, str]:
    req = urllib.request.Request(f"{ATDM}{path}")  # noqa: S310
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _get_text(path: str) -> str:
    with urllib.request.urlopen(f"{ATDM}{path}") as resp:  # noqa: S310
        body: str = resp.read().decode("utf-8")
        return body


def _force_cleanup(run_id: str) -> None:
    with contextlib.suppress(urllib.error.URLError):
        urllib.request.urlopen(  # noqa: S310
            urllib.request.Request(
                f"{SUT}/internal/scenarios?run_id={run_id}",
                method="DELETE",
            )
        )


# -----------------------------------------------------------------------------
# E3 — UI renders for known run
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_audit_ui_renders_for_known_run(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={
            "scenario": "claim_denial_active_member",
            "delivery": {
                "seed_target": True,
                "return_playwright_fixture": True,
                "return_pytest_fixture": True,
            },
        },
    )
    assert code == 200
    run_id = body["test_run_id"]

    try:
        status_code, html = _get_html(f"/ui/audit/{run_id}")
        assert status_code == 200
        # All required sections show up in the rendered HTML.
        for needle in (
            "Audit trail",
            run_id,
            "Scenario",
            "Plan",
            "Validator decisions",
            "Records created",
            "Fixtures emitted",
            "Timeline",
        ):
            assert needle in html, f"missing section: {needle!r}"

        # The PicoCSS CDN link should be present.
        assert "picocss" in html.lower() or "pico.min.css" in html.lower()
    finally:
        _force_cleanup(run_id)


@pytest.mark.integration
def test_audit_ui_returns_404_for_unknown_run(compose_stack: None) -> None:
    status_code, html = _get_html("/ui/audit/totally-not-a-real-run-id-01KS")
    assert status_code == 404
    assert "Run not found" in html


@pytest.mark.integration
def test_audit_ui_page_under_100_kb(compose_stack: None) -> None:
    """E3 page-weight budget."""
    code, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={"scenario": "claim_denial_active_member"},
    )
    assert code == 200
    run_id = body["test_run_id"]
    try:
        _, html = _get_html(f"/ui/audit/{run_id}")
        # 100 KB hard ceiling. PicoCSS is loaded from CDN so the page itself
        # is just the rendered HTML; should be a few KB.
        size_bytes = len(html.encode("utf-8"))
        assert size_bytes < 100_000, f"audit page is {size_bytes} bytes (budget 100 KB)"
    finally:
        _force_cleanup(run_id)


@pytest.mark.integration
def test_audit_ui_does_not_require_auth(compose_stack: None) -> None:
    """NFR-004: read endpoints are open on the local network."""
    code, body = _request(
        "POST", ATDM, "/test-data/requests", body={"scenario": "active_member_clean"}
    )
    assert code == 200
    run_id = body["test_run_id"]
    try:
        # No auth header here.
        req = urllib.request.Request(f"{ATDM}/ui/audit/{run_id}")  # noqa: S310
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            assert resp.status == 200
            assert "html" in resp.headers.get("content-type", "").lower()
    finally:
        _force_cleanup(run_id)


# -----------------------------------------------------------------------------
# Validator-rejected runs render correctly
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_audit_ui_shows_rejected_validator(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={
            "scenario": "active_member_clean",
            "constraints": {
                "member_status": "inactive",
                "eligibility_status": "active",
            },
        },
    )
    assert code == 422
    run_id = body["detail"]["error"]["test_run_id"]

    try:
        status_code, html = _get_html(f"/ui/audit/{run_id}")
        assert status_code == 200
        # Failed validator name appears in the page.
        assert "relational.eligibility_status_matches_member" in html
        # And it's marked failed.
        assert "failed" in html.lower()
    finally:
        _force_cleanup(run_id)


# -----------------------------------------------------------------------------
# /metrics emits audit counters
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_metrics_includes_audit_counters(compose_stack: None) -> None:
    # Trigger at least one event so the counters appear.
    code, body = _request(
        "POST", ATDM, "/test-data/requests", body={"scenario": "active_member_clean"}
    )
    assert code == 200
    run_id = body["test_run_id"]

    try:
        metrics = _get_text("/metrics")
        # The Phase 1 heartbeat.
        assert "atdm_up 1" in metrics
        # The Phase 8 audit counters.
        assert "atdm_audit_events_total" in metrics
        assert "atdm_audit_write_latency_seconds" in metrics
        assert "atdm_audit_dropped_events_total" in metrics

        # Dropped count must be 0 — anything else fails Phase 8 acceptance.
        for line in metrics.splitlines():
            if line.startswith("atdm_audit_dropped_events_total ") and not line.startswith("#"):
                value = float(line.split()[-1])
                assert value == 0.0, f"audit dropped events > 0: {line}"
    finally:
        _force_cleanup(run_id)
