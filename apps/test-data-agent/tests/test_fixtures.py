"""Unit tests for the fixture writer modules.

Tests use a tmp_path fixture so they don't touch the real ATDM_FIXTURE_DIR.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.fixtures.playwright import write_playwright_fixture
from app.fixtures.pytest_module import write_pytest_fixture

SCENARIO = "claim_denial_active_member"
RUN_ID = "01TESTRUN"
DATA = {
    "plan_id": "plan-01TESTRUN",
    "provider_id": "prov-01TESTRUN",
    "member_id": "m-01TESTRUN",
    "eligibility_id": "elig-01TESTRUN",
    "claim_id": "claim-01TESTRUN",
}
CLEANUP = {
    "cleanup_token": "secret-token",
    "endpoint": "/test-data/runs/01TESTRUN/reset",
}


@pytest.fixture()
def fixture_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ATDM_FIXTURE_DIR", str(tmp_path))
    return tmp_path


# -----------------------------------------------------------------------------
# Playwright JSON
# -----------------------------------------------------------------------------


def test_playwright_fixture_written_to_disk(fixture_dir: Path) -> None:
    path = write_playwright_fixture(
        scenario_id=SCENARIO,
        test_run_id=RUN_ID,
        data=DATA,
        cleanup=CLEANUP,
    )
    assert path.exists()
    assert path.name == f"{SCENARIO}_{RUN_ID}.json"


def test_playwright_fixture_is_valid_json_with_required_keys(fixture_dir: Path) -> None:
    path = write_playwright_fixture(
        scenario_id=SCENARIO,
        test_run_id=RUN_ID,
        data=DATA,
        cleanup=CLEANUP,
    )
    body = json.loads(path.read_text())
    assert set(body.keys()) == {"scenario_id", "test_run_id", "data", "cleanup"}
    assert body["scenario_id"] == SCENARIO
    assert body["test_run_id"] == RUN_ID
    assert body["data"] == DATA
    assert body["cleanup"] == CLEANUP


def test_playwright_fixture_creates_missing_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "deeper" / "subdir"
    monkeypatch.setenv("ATDM_FIXTURE_DIR", str(target))
    assert not target.exists()
    path = write_playwright_fixture(
        scenario_id=SCENARIO,
        test_run_id=RUN_ID,
        data=DATA,
        cleanup=CLEANUP,
    )
    assert path.exists()
    assert target.exists()


# -----------------------------------------------------------------------------
# pytest module
# -----------------------------------------------------------------------------


def test_pytest_fixture_written_to_disk(fixture_dir: Path) -> None:
    path = write_pytest_fixture(
        scenario_id=SCENARIO,
        test_run_id=RUN_ID,
        data=DATA,
        cleanup=CLEANUP,
    )
    assert path.exists()
    assert path.name == f"{SCENARIO}_{RUN_ID}.py"


def test_pytest_fixture_module_importable(fixture_dir: Path) -> None:
    """D2 acceptance — the emitted .py file can be imported and used."""
    path = write_pytest_fixture(
        scenario_id=SCENARIO,
        test_run_id=RUN_ID,
        data=DATA,
        cleanup=CLEANUP,
    )

    spec = importlib.util.spec_from_file_location("atdm_test_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.SCENARIO_ID == SCENARIO
    assert module.TEST_RUN_ID == RUN_ID

    payload = module.scenario_data()
    assert payload["scenario_id"] == SCENARIO
    assert payload["test_run_id"] == RUN_ID
    assert payload["data"] == DATA
    assert payload["cleanup"] == CLEANUP


def test_pytest_fixture_handles_special_chars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Embedded JSON payload must survive characters that are tricky in
    triple-quoted strings (quotes, backslashes)."""
    monkeypatch.setenv("ATDM_FIXTURE_DIR", str(tmp_path))
    tricky_data = {
        "member_name": 'FAKE_"Quoted"',
        "path": "C:\\Users\\fake",
    }
    path = write_pytest_fixture(
        scenario_id="edge_case",
        test_run_id="01EDGE",
        data=tricky_data,
        cleanup={"cleanup_token": "t", "endpoint": "/r"},
    )

    spec = importlib.util.spec_from_file_location("atdm_edge_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = module.scenario_data()
    assert payload["data"] == tricky_data
