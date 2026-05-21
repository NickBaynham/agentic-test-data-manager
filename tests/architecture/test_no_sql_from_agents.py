"""AR-003 architecture fitness test.

The agent module shall never write SQL directly. The only path to the
Target SUT is via its HTTP API. This test grep-walks the agent source for
forbidden imports and fails the build on any match.

If a future refactor adds an SQL driver to the agent layer, this test
catches it before it merges — that's the whole point. Don't suppress this
test. If you genuinely need DB access from the agent (you almost certainly
don't), open a Phase 9 architecture decision record first.

Locked in by AR-003 in [BRD §10] and the "tool-bounded agent" architectural
claim in [planning/PLAN.md].
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_SOURCE = REPO_ROOT / "apps" / "test-data-agent" / "app"

# Forbidden imports. Match `import X`, `import X.Y`, `from X import ...`, and
# `from X.Y import ...`. Substring `X` in a comment or docstring is fine —
# the regex requires the import keyword.
FORBIDDEN_TOP_LEVEL_MODULES = (
    "psycopg",
    "psycopg2",
    "psycopg3",
    "asyncpg",
    "sqlalchemy",
    "sqlmodel",
    "aiopg",
    "databases",
)

# Match `import <mod>(.<sub>)?` or `from <mod>(.<sub>)? import ...`. We allow
# whitespace + leading dots (relative imports). We use \b so we don't match
# `asyncpg_helpers` etc. as a substring of a legitimate first-party module.
_PATTERN = re.compile(
    r"^\s*(?:from|import)\s+(?P<mod>[A-Za-z_][\w.]*)",
    re.MULTILINE,
)


def _iter_agent_python_files() -> list[Path]:
    """Every .py file in the agent module, excluding tests."""
    if not AGENT_SOURCE.exists():
        pytest.skip(f"{AGENT_SOURCE} does not exist (yet)")
    return sorted(p for p in AGENT_SOURCE.rglob("*.py") if "/tests/" not in p.as_posix())


def test_agent_never_imports_a_sql_driver() -> None:
    """AR-003 — fail the build if any file under apps/test-data-agent/app/
    imports psycopg / asyncpg / sqlalchemy / sqlmodel."""
    violations: list[tuple[Path, int, str]] = []
    for file_path in _iter_agent_python_files():
        source = file_path.read_text()
        for match in _PATTERN.finditer(source):
            mod = match.group("mod")
            root = mod.split(".", 1)[0]
            if root in FORBIDDEN_TOP_LEVEL_MODULES:
                # Find the line number for a useful error message.
                line_no = source[: match.start()].count("\n") + 1
                rel = file_path.relative_to(REPO_ROOT)
                violations.append((rel, line_no, mod))

    if violations:
        msg_lines = [
            "AR-003 violation: agent code imports a SQL driver. "
            "The agent must reach the Target SUT only via its HTTP API.",
            "",
        ]
        for rel, line_no, mod in violations:
            msg_lines.append(f"  {rel}:{line_no}  imports `{mod}`")
        msg_lines.append("")
        msg_lines.append(
            "Resolution: remove the import. If you genuinely believe agent-side "
            "SQL is required, write a Phase 9 architecture decision record "
            "first and open a discussion before deleting this test."
        )
        pytest.fail("\n".join(msg_lines))


def test_agent_never_calls_psql_or_raw_sql_via_subprocess() -> None:
    """Belt-and-suspenders: forbid `subprocess.run(['psql', ...])` or similar
    string-formatted SQL via shell calls."""
    suspect_patterns = [
        re.compile(r"\bpsql\b"),
        re.compile(r"INSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"DELETE\s+FROM\b", re.IGNORECASE),
        re.compile(r"UPDATE\s+[a-z_]+\s+SET\b", re.IGNORECASE),
        re.compile(r"TRUNCATE\s+TABLE\b", re.IGNORECASE),
    ]
    violations: list[tuple[Path, int, str]] = []
    for file_path in _iter_agent_python_files():
        source = file_path.read_text()
        for pat in suspect_patterns:
            for match in pat.finditer(source):
                line_no = source[: match.start()].count("\n") + 1
                line = source.splitlines()[line_no - 1]
                # Skip false positives: comments, docstrings that mention SQL,
                # and the validator module's documentation strings.
                stripped = line.lstrip()
                if stripped.startswith("#") or '"""' in line or "'''" in line:
                    continue
                rel = file_path.relative_to(REPO_ROOT)
                violations.append((rel, line_no, line.strip()))
    if violations:
        msg = ["AR-003 violation: agent contains SQL-like literals."]
        for rel, line_no, line in violations:
            msg.append(f"  {rel}:{line_no}  {line}")
        pytest.fail("\n".join(msg))
