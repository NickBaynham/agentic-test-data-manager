"""NFR-012 architecture fitness test: no emoji in source, docs, or UI.

Per the project CLAUDE.md "no emojis in any text we produce." Phase 8 makes
this enforceable: every committed source / Markdown / YAML / TOML / template
file is scanned for emoji code points and the build fails on a hit.

Scans these directories (extensions filtered below):
  - apps/
  - tests/
  - planning/
  - requirements/
  - docs/
  - automation/playwright/tests/
  - top-level Markdown files

Skipped:
  - .venv/, __pypackages__/, .git/, node_modules/ (vendored)
  - data/, infra/ (binary or pinned vendor configs)
  - automation/fixtures/ (generator output — gitignored anyway)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_ROOTS = [
    REPO_ROOT / "apps",
    REPO_ROOT / "tests",
    REPO_ROOT / "planning",
    REPO_ROOT / "requirements",
    REPO_ROOT / "docs",
    REPO_ROOT / "automation" / "playwright" / "tests",
    REPO_ROOT / "automation" / "pytest-api",
]

TOP_LEVEL_FILES = [
    "README.md",
    "CHANGELOG.md",
    "FEATURES.md",
    "TODO.md",
    "Makefile",
    "LICENSE",
    "pyproject.toml",
    "mypy.ini",
]

INCLUDE_SUFFIXES = {
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".sql",
    ".html",
    ".css",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
}

# Emoji Unicode ranges. Conservative — covers most modern emoji blocks.
# Source: Unicode Emoji 16.0 ranges. We don't try to catch every grapheme
# cluster; the goal is "obvious emoji slip", not "linguistic emoji analysis".
EMOJI_PATTERN = re.compile(
    "["
    "\U0001f300-\U0001faff"  # Misc Symbols / Pictographs, Supplemental
    "\U0001f600-\U0001f64f"  # Emoticons
    "\U0001f680-\U0001f6ff"  # Transport
    "\U0001f900-\U0001f9ff"  # Supplemental Symbols
    "\U00002600-\U000026ff"  # Misc Symbols
    "\U00002700-\U000027bf"  # Dingbats
    "\U0001f1e6-\U0001f1ff"  # Regional indicators (flags)
    "]"
)


def _iter_scanned_files() -> list[Path]:
    files: list[Path] = []
    # Skip these directories anywhere in the path.
    SKIP_PARTS = {
        ".venv",
        "__pypackages__",
        ".git",
        "node_modules",
        "playwright-report",
        "test-results",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
    }

    def _skip(path: Path) -> bool:
        return any(part in SKIP_PARTS for part in path.parts)

    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in INCLUDE_SUFFIXES and not _skip(p):
                files.append(p)

    for top in TOP_LEVEL_FILES:
        p = REPO_ROOT / top
        if p.exists() and p.is_file():
            files.append(p)

    return sorted(set(files))


def test_no_emoji_in_committed_text() -> None:
    """NFR-012 — fail the build on any emoji code point in tracked text files."""
    violations: list[tuple[Path, int, str]] = []
    for file_path in _iter_scanned_files():
        try:
            source = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable — out of scope for this test
        for match in EMOJI_PATTERN.finditer(source):
            line_no = source[: match.start()].count("\n") + 1
            rel = file_path.relative_to(REPO_ROOT)
            violations.append((rel, line_no, match.group(0)))

    if violations:
        msg = ["NFR-012 violation: emoji code point(s) in committed text."]
        for rel, line_no, ch in violations:
            msg.append(f"  {rel}:{line_no}  contains {ch!r} ({hex(ord(ch))})")
        msg.append("")
        msg.append("Per project CLAUDE.md, no emojis in any text we produce.")
        pytest.fail("\n".join(msg))
