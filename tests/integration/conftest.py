"""Shared fixtures for integration / e2e tests.

The `compose_stack` fixture brings up the docker compose stack at the start of
the session and tears it down at the end. Tests tagged @pytest.mark.integration
or @pytest.mark.e2e require this fixture.

Honors the env var ATDM_KEEP_STACK_UP=1 — useful while developing tests so
successive runs don't pay the cold-start cost. Tear down manually with
`make down` when you're done.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "infra" / "docker-compose.yml"
COMPOSE_BASE = ["docker", "compose", "-f", str(COMPOSE_FILE)]

# Generous ceiling — NFR-001 budget is 60s p95 but cold runs that include
# image pulls can exceed that on a fresh machine. The integration test asserts
# on the steady-state warm-up budget (60s) separately.
STACK_UP_TIMEOUT_SECONDS = 180


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        cmd,
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session")
def compose_stack() -> Iterator[None]:
    keep_up = os.environ.get("ATDM_KEEP_STACK_UP", "") == "1"
    started_here = False

    # Are services already healthy? If so, just use them.
    ps = _run([*COMPOSE_BASE, "ps", "--format", "json"], check=False)
    already_running = "healthy" in ps.stdout

    if not already_running:
        print(f"[compose_stack] bringing up stack (timeout {STACK_UP_TIMEOUT_SECONDS}s)")
        result = subprocess.run(  # noqa: S603
            [*COMPOSE_BASE, "up", "-d", "--wait"],
            cwd=REPO_ROOT,
            timeout=STACK_UP_TIMEOUT_SECONDS,
            check=True,
        )
        assert result.returncode == 0
        started_here = True

    yield

    if started_here and not keep_up:
        print("[compose_stack] tearing down stack")
        _run([*COMPOSE_BASE, "down"], check=False)


def wait_for_healthy(url: str, timeout: float = 60.0) -> float:
    """Poll url until 200, return elapsed seconds. Raises on timeout."""
    import urllib.error
    import urllib.request

    start = time.monotonic()
    deadline = start + timeout
    last_err: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
                if resp.status == 200:
                    return time.monotonic() - start
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last_err = e
        time.sleep(0.5)
    raise TimeoutError(f"{url} did not return 200 within {timeout}s (last error: {last_err})")
