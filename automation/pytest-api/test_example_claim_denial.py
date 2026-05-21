"""Demo example: pytest test consuming an ATDM-emitted fixture module.

`make demo` orchestrates the full flow:
  1. atdm request claim_denial_active_member --pytest
     This writes a .py module to ATDM_FIXTURE_DIR.
  2. ATDM_FIXTURE_FILE=<that path> pdm run pytest this_file.py
  3. atdm reset <run_id>

The test below is what "step 2" runs. It imports the generated fixture
module dynamically (the file path is in the env var) and asserts on its
content. This is the canonical demo for the portfolio audience:
"the agent gave me a fixture; my test consumed it; the cleanup worked."
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import pytest


def _load_fixture() -> dict[str, Any]:
    fixture_file = os.environ.get("ATDM_FIXTURE_FILE")
    if not fixture_file:
        pytest.skip(
            "ATDM_FIXTURE_FILE not set — this test is driven by `make demo`. "
            "Run `make demo` instead of pytest directly."
        )
    path = Path(fixture_file)
    if not path.exists():
        pytest.skip(f"fixture file {path} does not exist")

    spec = importlib.util.spec_from_file_location("atdm_demo_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload: dict[str, Any] = module.scenario_data()
    return payload


def test_claim_denial_fixture_is_well_formed() -> None:
    fixture = _load_fixture()
    assert fixture["scenario_id"] == "claim_denial_active_member"
    assert fixture["test_run_id"].startswith("01")  # ULID
    data = fixture["data"]
    assert data["claim_id"].startswith("claim-")
    assert data["member_id"].startswith("m-")
    assert data["provider_id"].startswith("prov-")
    assert data["plan_id"].startswith("plan-")
    assert data["eligibility_id"].startswith("elig-")


def test_claim_denial_fixture_carries_cleanup_contract() -> None:
    fixture = _load_fixture()
    cleanup = fixture["cleanup"]
    assert isinstance(cleanup["cleanup_token"], str)
    assert len(cleanup["cleanup_token"]) > 20  # nontrivial token
    assert cleanup["endpoint"].endswith(f"/test-data/runs/{fixture['test_run_id']}/reset")
