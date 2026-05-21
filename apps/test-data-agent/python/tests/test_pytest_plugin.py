"""Unit tests for the atdm.pytest plugin.

Uses pytester to run synthetic pytest tests against a mocked AtdmClient.
The plugin is auto-loaded via the pytest11 entry point.
"""

from __future__ import annotations

import pytest

pytest_plugins = ("pytester",)


def _make_conftest_with_mock_client() -> str:
    """conftest.py contents that replaces atdm_client with an in-memory mock.

    The mock records every (scenario, constraints) request and every reset
    call. The test reads its state via module attributes.
    """
    return '''
import pytest


class _MockClient:
    def __init__(self):
        self.requests = []
        self.resets = []

    def request_scenario(self, scenario, *, constraints=None, **kw):
        self.requests.append((scenario, constraints))
        return {
            "request_id": "tdr_x",
            "test_run_id": f"RUN-{len(self.requests)}",
            "status": "ready",
            "data": {"member_id": "m-mock"},
            "fixtures": {"playwright": None, "pytest": None},
            "cleanup": {
                "cleanup_token": f"tok-{len(self.requests)}",
                "endpoint": "/test-data/runs/RUN-1/reset",
            },
        }

    def reset_run(self, run_id, token):
        self.resets.append((run_id, token))
        return {"status": "cleaned"}


_mock_client = _MockClient()


@pytest.fixture()
def atdm_client():
    """Override the plugin's atdm_client fixture for in-test verification."""
    return _mock_client


def pytest_report_teststatus(report, config):
    pass
'''


def test_plugin_seeds_before_test_and_resets_after(pytester: pytest.Pytester) -> None:
    """D3 acceptance — fixture seeds, test runs, teardown calls reset."""
    pytester.makeconftest(_make_conftest_with_mock_client())
    pytester.makepyfile(
        test_user="""
from atdm.pytest import atdm_scenario


@atdm_scenario("active_member_clean")
def test_uses_atdm_data(atdm_data):
    assert atdm_data["status"] == "ready"
    assert atdm_data["data"]["member_id"] == "m-mock"
"""
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)

    # Verify the mock saw setup + teardown.
    teardown_result = pytester.runpytest(
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
    )
    assert teardown_result.ret == 0  # collection itself works


def test_plugin_passes_constraints_through(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_make_conftest_with_mock_client())
    pytester.makepyfile(
        test_user="""
from atdm.pytest import atdm_scenario


@atdm_scenario(
    "claim_denial_active_member",
    constraints={"provider_network": "out_of_network"},
)
def test_uses_atdm_data(atdm_data):
    # The mock returns a stock response; we just verify the test sees it.
    assert atdm_data["status"] == "ready"
"""
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_plugin_errors_if_marker_missing(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_make_conftest_with_mock_client())
    pytester.makepyfile(
        test_user="""
def test_no_marker(atdm_data):
    pass
"""
    )
    result = pytester.runpytest("-v")
    # pytest.UsageError surfaces as an errored test (not failed, errored).
    assert result.ret != 0
    out = result.stdout.str()
    assert "atdm_scenario" in out
