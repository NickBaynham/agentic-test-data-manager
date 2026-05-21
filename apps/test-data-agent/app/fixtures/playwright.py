"""Playwright JSON fixture emitter.

Writes one JSON file per scenario request to ATDM_FIXTURE_DIR named
`<scenario>_<test_run_id>.json`. The shape mirrors the bundle the request
endpoint returns, so a Playwright test can `JSON.parse(fs.readFileSync(...))`
and use the keys directly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def fixture_dir() -> Path:
    """Where fixture files are written. Configurable via ATDM_FIXTURE_DIR."""
    return Path(os.environ.get("ATDM_FIXTURE_DIR", "./automation/fixtures"))


def fixture_path(scenario_id: str, test_run_id: str) -> Path:
    return fixture_dir() / f"{scenario_id}_{test_run_id}.json"


def write_playwright_fixture(
    *,
    scenario_id: str,
    test_run_id: str,
    data: dict[str, Any],
    cleanup: dict[str, Any],
) -> Path:
    """Write the fixture and return its path.

    The shape:
      {
        "scenario_id": "<id>",
        "test_run_id": "<ulid>",
        "data": {...primary keys...},
        "cleanup": {"cleanup_token": "...", "endpoint": "..."}
      }
    """
    target_dir = fixture_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = fixture_path(scenario_id, test_run_id)
    payload = {
        "scenario_id": scenario_id,
        "test_run_id": test_run_id,
        "data": data,
        "cleanup": cleanup,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path
