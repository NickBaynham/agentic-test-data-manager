"""pytest module emitter.

Writes a `.py` file per scenario request that exposes `scenario_data()`
returning the fixture dict. Importable directly from pytest tests:

    import importlib.util
    spec = importlib.util.spec_from_file_location("fix", "/path/to/fix.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fixture = mod.scenario_data()

Implementation note: the payload is embedded via `repr()` on the dict, not
as an embedded JSON string. Embedded JSON inside a triple-quoted Python
string breaks the moment the payload contains backslashes (e.g., Windows
paths) because Python interprets `\\U` etc. as escape sequences. `repr()`
on built-in types (str, int, float, bool, None, list, dict) roundtrips
cleanly through `ast.literal_eval` and through normal module loading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.fixtures.playwright import fixture_dir


def pytest_fixture_path(scenario_id: str, test_run_id: str) -> Path:
    return fixture_dir() / f"{scenario_id}_{test_run_id}.py"


def write_pytest_fixture(
    *,
    scenario_id: str,
    test_run_id: str,
    data: dict[str, Any],
    cleanup: dict[str, Any],
) -> Path:
    """Write the pytest fixture module and return its path."""
    target_dir = fixture_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = pytest_fixture_path(scenario_id, test_run_id)

    header = f"Generated fixture for scenario {scenario_id!r} (run={test_run_id!r})."
    module_src = f'''"""{header}

Emitted by the ATDM agent. Do not edit by hand.
"""

from __future__ import annotations

from typing import Any

SCENARIO_ID = {scenario_id!r}
TEST_RUN_ID = {test_run_id!r}

_DATA: dict[str, Any] = {data!r}
_CLEANUP: dict[str, Any] = {cleanup!r}


def scenario_data() -> dict[str, Any]:
    """Return the full fixture payload as a dict."""
    return {{
        "scenario_id": SCENARIO_ID,
        "test_run_id": TEST_RUN_ID,
        "data": _DATA,
        "cleanup": _CLEANUP,
    }}
'''

    path.write_text(module_src)
    return path
