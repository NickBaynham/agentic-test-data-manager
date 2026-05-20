"""Phase 1 integration / e2e tests.

These tests verify that the local stack (Postgres, MinIO, Target SUT stub,
ATDM agent stub) comes up healthy and that the health endpoints are reachable
from the host on the canonical remapped ports (see planning/PLAN.md Phase 1
host port mapping table).

Maps to PLAN.md Phase 1 exit criteria.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request

import pytest

from tests.integration.conftest import COMPOSE_BASE, REPO_ROOT, wait_for_healthy

TARGET_SUT_HEALTH_URL = "http://localhost:18000/health"
ATDM_AGENT_HEALTH_URL = "http://localhost:18001/health"
ATDM_AGENT_METRICS_URL = "http://localhost:18001/metrics"


@pytest.mark.integration
def test_all_services_healthy(compose_stack: None) -> None:
    """All four long-running services report healthy via docker compose ps."""
    result = subprocess.run(  # noqa: S603
        [*COMPOSE_BASE, "ps", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    # Compose v2 emits one JSON object per line.
    services = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]

    long_running = {"postgres", "minio", "target-healthcare-api", "test-data-agent"}
    healthy_services = {svc["Service"] for svc in services if svc.get("Health") == "healthy"}
    missing = long_running - healthy_services
    assert not missing, (
        f"these services are not healthy: {missing}; "
        f"full state: {[(s['Service'], s.get('State'), s.get('Health')) for s in services]}"
    )


@pytest.mark.integration
def test_target_sut_health_endpoint_responds_200(compose_stack: None) -> None:
    elapsed = wait_for_healthy(TARGET_SUT_HEALTH_URL, timeout=30.0)
    assert elapsed < 30.0
    with urllib.request.urlopen(TARGET_SUT_HEALTH_URL) as resp:  # noqa: S310
        assert resp.status == 200
        body = json.loads(resp.read())
        assert body == {"status": "ok", "service": "target-healthcare-api"}


@pytest.mark.integration
def test_atdm_agent_health_endpoint_responds_200(compose_stack: None) -> None:
    elapsed = wait_for_healthy(ATDM_AGENT_HEALTH_URL, timeout=30.0)
    assert elapsed < 30.0
    with urllib.request.urlopen(ATDM_AGENT_HEALTH_URL) as resp:  # noqa: S310
        assert resp.status == 200
        body = json.loads(resp.read())
        assert body["status"] == "ok"
        assert body["service"] == "test-data-agent"
        # Phase 1: planner is in rule mode by default (LLM_MODE_NOT_ENABLED).
        assert body["planner_mode"] == "rule"


@pytest.mark.integration
def test_atdm_agent_metrics_endpoint_emits_prometheus(compose_stack: None) -> None:
    with urllib.request.urlopen(ATDM_AGENT_METRICS_URL) as resp:  # noqa: S310
        assert resp.status == 200
        body = resp.read().decode()
    assert "# HELP atdm_up" in body
    assert "# TYPE atdm_up gauge" in body
    assert "atdm_up 1" in body


@pytest.mark.integration
def test_minio_buckets_exist(compose_stack: None) -> None:
    """The bootstrap init container creates atdm-catalog, atdm-audit, atdm-fixtures."""
    result = subprocess.run(  # noqa: S603
        [
            *COMPOSE_BASE,
            "exec",
            "-T",
            "minio",
            "mc",
            "ls",
            "local/",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # mc may fail on `exec -T` env; fall back to running mc inside a one-shot
    # container that joins the compose network.
    if result.returncode != 0:
        result = subprocess.run(  # noqa: S603
            [
                *COMPOSE_BASE,
                "run",
                "--rm",
                "-T",
                "minio-buckets",
                "mc",
                "ls",
                "local/",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    output = result.stdout + result.stderr
    assert "atdm-catalog" in output, f"missing atdm-catalog bucket: {output}"
    assert "atdm-audit" in output, f"missing atdm-audit bucket: {output}"
    assert "atdm-fixtures" in output, f"missing atdm-fixtures bucket: {output}"


@pytest.mark.e2e
def test_stack_warm_start_within_60_seconds() -> None:
    """E2E: tear the stack down (volumes preserved) and time the next make up.

    Caches (pip, image layers) are kept so this is a *warm* start. NFR-001
    budget is 60s p95. We measure once here; the 5-run p95 sweep is in
    scripts/measure_cold_start.sh.

    Skipped if the stack is being kept up (ATDM_KEEP_STACK_UP=1) — tearing
    it down would defeat the purpose.
    """
    import os
    import time

    if os.environ.get("ATDM_KEEP_STACK_UP", "") == "1":
        pytest.skip("ATDM_KEEP_STACK_UP=1; not tearing down stack")

    # Bring down without removing volumes.
    subprocess.run(  # noqa: S603
        [*COMPOSE_BASE, "down"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    start = time.monotonic()
    subprocess.run(  # noqa: S603
        [*COMPOSE_BASE, "up", "-d", "--wait"],
        cwd=REPO_ROOT,
        timeout=120,
        capture_output=True,
        text=True,
        check=True,
    )
    elapsed = time.monotonic() - start
    assert elapsed < 60.0, f"warm start took {elapsed:.1f}s (budget 60s)"

    # Bring it back down for cleanup; the session fixture won't re-bring it up.
    subprocess.run(  # noqa: S603
        [*COMPOSE_BASE, "down"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
