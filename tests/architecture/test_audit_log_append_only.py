"""NFR-011 architecture fitness test: audit log is append-only at the API layer.

There must be NO public mutation surface for past audit events. Specifically:

  - No FastAPI route under /audit/* may have a DELETE, PUT, or PATCH method.
  - No function under apps/test-data-agent/app/audit/ may be named like
    `delete_event`, `update_event`, `mutate_event`, `set_event`.

Bypassing this test means breaking the auditable-AI-output claim (FR-051).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_SOURCES = [
    REPO_ROOT / "apps" / "test-data-agent" / "app" / "audit",
    REPO_ROOT / "apps" / "test-data-agent" / "app" / "api" / "audit.py",
]

# Match e.g.  @router.delete("/audit/...")  or  @router.patch("...")
FORBIDDEN_AUDIT_ROUTE = re.compile(
    r"@router\.(?:delete|put|patch)\(\s*['\"]([^'\"]*audit[^'\"]*)['\"]",
    re.IGNORECASE,
)

# Function names that imply mutation of past events.
FORBIDDEN_FN_NAMES = (
    "delete_event",
    "update_event",
    "mutate_event",
    "set_event",
    "edit_event",
    "modify_event",
)


def _iter_audit_files() -> list[Path]:
    files: list[Path] = []
    for src in AUDIT_SOURCES:
        if src.is_file():
            files.append(src)
        elif src.is_dir():
            files.extend(sorted(p for p in src.rglob("*.py") if "/templates/" not in p.as_posix()))
    return files


def test_no_mutating_route_under_audit() -> None:
    violations: list[tuple[Path, int, str]] = []
    for file_path in _iter_audit_files():
        source = file_path.read_text()
        for match in FORBIDDEN_AUDIT_ROUTE.finditer(source):
            line_no = source[: match.start()].count("\n") + 1
            rel = file_path.relative_to(REPO_ROOT)
            violations.append((rel, line_no, match.group(0)))
    if violations:
        msg = ["NFR-011 violation: audit endpoints must be read-only."]
        for rel, line_no, m in violations:
            msg.append(f"  {rel}:{line_no}  {m}")
        pytest.fail("\n".join(msg))


def test_no_function_named_like_an_event_mutator() -> None:
    violations: list[tuple[Path, str]] = []
    for file_path in _iter_audit_files():
        source = file_path.read_text()
        for name in FORBIDDEN_FN_NAMES:
            if re.search(rf"\bdef\s+{name}\s*\(", source):
                rel = file_path.relative_to(REPO_ROOT)
                violations.append((rel, name))
    if violations:
        msg = ["NFR-011 violation: audit functions implying mutation of past events."]
        for rel, name in violations:
            msg.append(f"  {rel}  defines `{name}`")
        pytest.fail("\n".join(msg))
