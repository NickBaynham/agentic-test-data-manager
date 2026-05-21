"""Example: pytest-API test using `@atdm_scenario`.

This file is the canonical demo for the `atdm.pytest` plugin. It is what an
end-user would write in their own test suite. Two flows shown:

  1. Happy path — `@atdm_scenario` decorator + `atdm_data` fixture.
     The plugin seeds data before the test, passes it as `atdm_data`, and
     calls /reset after the test finishes.

  2. Direct client usage — for users who want explicit control.

These tests require the local stack to be up. Run with:

    make up
    PYTHONPATH=. ATDM_API_URL=http://localhost:18001 \
        ATDM_API_TOKEN=dev-token-change-me \
        pdm run pytest automation/pytest-api -v
"""

from __future__ import annotations

from atdm.client import AtdmClient
from atdm.pytest import atdm_scenario


@atdm_scenario("active_member_clean")
def test_active_member_clean_via_decorator(atdm_data: dict[str, object]) -> None:
    """The decorator + fixture seeds before, resets after."""
    assert atdm_data["status"] == "ready"
    data = atdm_data["data"]
    assert isinstance(data, dict)
    assert isinstance(data["member_id"], str) and data["member_id"].startswith("m-")
    assert isinstance(data["plan_id"], str) and data["plan_id"].startswith("plan-")


@atdm_scenario(
    "claim_denial_active_member",
    constraints={"provider_network": "out_of_network"},
)
def test_claim_denial_with_constraint_override(atdm_data: dict[str, object]) -> None:
    """Constraints can override the scenario's default_constraints."""
    assert atdm_data["status"] == "ready"
    data = atdm_data["data"]
    assert isinstance(data, dict)
    assert isinstance(data["claim_id"], str) and data["claim_id"].startswith("claim-")


def test_direct_client_usage() -> None:
    """For users who want to manage the lifecycle themselves."""
    client = AtdmClient()
    response = client.request_scenario("active_member_clean")
    try:
        assert response["status"] == "ready"
        assert isinstance(response["data"]["member_id"], str)
    finally:
        client.reset_run(response["test_run_id"], response["cleanup"]["cleanup_token"])
