"""pytest plugin: `@atdm_scenario` marker + `atdm_data` fixture.

Usage:

    from atdm.pytest import atdm_scenario

    @atdm_scenario("active_member_clean", constraints={"member_status": "active"})
    def test_member(atdm_data):
        assert atdm_data["data"]["member_id"].startswith("m-")
        # No cleanup needed — the fixture finalizer calls /reset for you.

Setup (per test):
  1. POST /test-data/requests with the marker's scenario name + constraints.
  2. Pass the response dict to the test as `atdm_data`.
Teardown (per test):
  3. POST /test-data/runs/{run_id}/reset with the cleanup_token from the
     response. This produces a `reset_completed` audit event with
     `status=cleaned`.

The plugin auto-loads via the pytest11 entry point declared in
apps/test-data-agent/python/pyproject.toml. No conftest configuration needed
in the consumer's repo.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from atdm.client import AtdmClient

MARKER_NAME = "atdm_scenario"


def atdm_scenario(
    scenario: str, *, constraints: dict[str, Any] | None = None
) -> pytest.MarkDecorator:
    """Decorator that marks a test with its required ATDM scenario."""
    return pytest.mark.atdm_scenario(scenario, constraints=constraints or {})


# ---------------------------------------------------------------------------
# pytest plugin hooks
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register the `atdm_scenario` marker so pytest doesn't warn on it."""
    config.addinivalue_line(
        "markers",
        f"{MARKER_NAME}(scenario, constraints): "
        "request a scenario from the ATDM agent before the test "
        "and reset it after.",
    )


@pytest.fixture()
def atdm_client() -> AtdmClient:
    """Override-able fixture providing the HTTP client. Useful for swapping
    in a mock in unit tests."""
    return AtdmClient()


@pytest.fixture()
def atdm_data(request: pytest.FixtureRequest, atdm_client: AtdmClient) -> Iterator[dict[str, Any]]:
    """Yield the scenario response payload for the marked test.

    Raises pytest.UsageError if the test isn't decorated with @atdm_scenario.
    """
    marker = request.node.get_closest_marker(MARKER_NAME)
    if marker is None:
        raise pytest.UsageError(
            "atdm_data fixture requires the @atdm_scenario(...) decorator on the test."
        )

    scenario_name: str = marker.args[0]
    constraints: dict[str, Any] = marker.kwargs.get("constraints") or {}

    response = atdm_client.request_scenario(scenario_name, constraints=constraints)
    yield response

    cleanup = response.get("cleanup") or {}
    token = cleanup.get("cleanup_token")
    run_id = response.get("test_run_id")
    if run_id and token:
        # Teardown is best-effort. The test result is already recorded;
        # a failure here shouldn't mask the test's verdict. Future enhancement:
        # emit a pytest warning instead of silently swallowing.
        import contextlib

        with contextlib.suppress(Exception):
            atdm_client.reset_run(run_id, token)
