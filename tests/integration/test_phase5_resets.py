"""Phase 5 integration tests — full reset strategy surface.

Covers:
  - C2 acceptance: baseline_snapshot → arbitrary requests → baseline_restore
    yields the captured state. Re-running restore is idempotent (NFR-016).
  - C3 acceptance: reset_all clears every test_run_id-tagged row but leaves
    baseline reference rows (test_run_id IS NULL) untouched.
  - C4 acceptance (idempotent_seed property): re-invoking baseline_restore
    twice in a row yields identical row counts.
  - X-Confirm gate on reset/all.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from typing import Any

import pytest

from tests.integration.conftest import COMPOSE_BASE, REPO_ROOT

ATDM = "http://localhost:18001"
SUT = "http://localhost:18000"
AUTH = "Bearer dev-token-change-me"


def _request(
    method: str,
    base: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    auth: bool = True,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    final_headers: dict[str, str] = dict(headers or {})
    if body is not None:
        final_headers.setdefault("content-type", "application/json")
    if auth:
        final_headers.setdefault("authorization", AUTH)
    req = urllib.request.Request(  # noqa: S310
        f"{base}{path}", data=data, headers=final_headers, method=method
    )
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _psql(sql: str) -> str:
    result = subprocess.run(  # noqa: S603
        [
            *COMPOSE_BASE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "atdm",
            "-d",
            "target_healthcare",
            "-tA",
            "-c",
            sql,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _row_counts() -> dict[str, int]:
    out = _psql(
        """
        SELECT 'plan',           COUNT(*) FROM plan           UNION ALL
        SELECT 'provider',       COUNT(*) FROM provider       UNION ALL
        SELECT 'member',         COUNT(*) FROM member         UNION ALL
        SELECT 'eligibility',    COUNT(*) FROM eligibility    UNION ALL
        SELECT 'claim',           COUNT(*) FROM claim          UNION ALL
        SELECT 'procedure_code', COUNT(*) FROM procedure_code UNION ALL
        SELECT 'diagnosis_code', COUNT(*) FROM diagnosis_code;
        """
    )
    counts: dict[str, int] = {}
    for line in out.splitlines():
        if "|" not in line:
            continue
        k, v = line.split("|")
        counts[k] = int(v)
    return counts


def _state_hash() -> str:
    """Hash the multiset of non-PK columns of every mutable table.

    NFR-016 says baseline_restore yields logically-equivalent state — non-PK
    columns match the baseline, auto-increment sequences (where they exist)
    are not required to match. For our schema, PKs are TEXT identifiers, so
    this hash includes them; the spirit of the requirement still holds.
    """
    hasher = hashlib.sha256()
    for table in (
        "plan",
        "provider",
        "member",
        "eligibility",
        "claim",
        "procedure_code",
        "diagnosis_code",
    ):
        # ORDER BY ensures deterministic hash regardless of insert order.
        out = _psql(f"SELECT md5(string_agg(t::text, '|' ORDER BY t::text)) FROM {table} t;")  # noqa: S608
        hasher.update(f"{table}={out}\n".encode())
    return hasher.hexdigest()


def _force_cleanup_all() -> None:
    """Best-effort: clear all test_run_id-tagged rows."""
    with contextlib.suppress(urllib.error.URLError):
        urllib.request.urlopen(  # noqa: S310
            urllib.request.Request(f"{SUT}/internal/reset/all-tagged", data=b"", method="POST")
        )


# -----------------------------------------------------------------------------
# X-Confirm gate
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_reset_all_without_x_confirm_returns_428(compose_stack: None) -> None:
    code, body = _request("POST", ATDM, "/test-data/reset/all")
    assert code == 428
    assert body["detail"]["error"]["code"] == "CONFIRM_REQUIRED"


@pytest.mark.integration
def test_reset_all_with_wrong_x_confirm_returns_428(compose_stack: None) -> None:
    code, _ = _request(
        "POST",
        ATDM,
        "/test-data/reset/all",
        headers={"X-Confirm": "no"},
    )
    assert code == 428


# -----------------------------------------------------------------------------
# C3 — reset_all clears tagged rows only
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_reset_all_clears_tagged_only_preserves_baseline(compose_stack: None) -> None:
    # Seed two scenarios so there's something to clear.
    for _ in range(2):
        _request("POST", ATDM, "/test-data/requests", body={"scenario": "active_member_clean"})

    before = _row_counts()
    assert before["plan"] >= 2
    baseline_pc = before["procedure_code"]
    baseline_dc = before["diagnosis_code"]

    code, body = _request(
        "POST",
        ATDM,
        "/test-data/reset/all",
        headers={"X-Confirm": "yes"},
    )
    assert code == 200
    assert body["strategy"] == "reset_all"

    after = _row_counts()
    for table in ("plan", "provider", "member", "eligibility", "claim"):
        assert after[table] == 0, f"{table} should be 0 after reset_all"
    # Baseline reference rows (test_run_id IS NULL) preserved.
    assert after["procedure_code"] == baseline_pc
    assert after["diagnosis_code"] == baseline_dc


# -----------------------------------------------------------------------------
# C2 — baseline snapshot → requests → restore round-trip
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_baseline_snapshot_restore_round_trip(compose_stack: None) -> None:
    """Take a snapshot of an empty state, seed scenarios, restore to the
    snapshot — non-PK content must match the snapshot."""
    _force_cleanup_all()
    state_before_snapshot = _state_hash()

    # Snapshot.
    code, snap = _request(
        "POST",
        ATDM,
        "/test-data/baseline/snapshot",
        body={"baseline_id": "test-c2-round-trip"},
    )
    assert code == 200
    bid = snap["baseline_id"]

    try:
        # Pollute the DB with arbitrary scenario requests.
        for s in ("active_member_clean", "claim_denial_active_member"):
            _request("POST", ATDM, "/test-data/requests", body={"scenario": s})
        assert _state_hash() != state_before_snapshot

        # Restore.
        code, _ = _request(
            "POST",
            ATDM,
            "/test-data/baseline/restore",
            body={"baseline_id": bid},
        )
        assert code == 200

        # State hash should match the snapshot.
        assert _state_hash() == state_before_snapshot
    finally:
        _force_cleanup_all()


# -----------------------------------------------------------------------------
# C4 — idempotent_seed: re-running restore yields identical state
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_baseline_restore_is_idempotent(compose_stack: None) -> None:
    _force_cleanup_all()
    _request("POST", ATDM, "/test-data/requests", body={"scenario": "active_member_clean"})

    # Snapshot the current state (has 1 scenario seeded).
    _, snap = _request(
        "POST",
        ATDM,
        "/test-data/baseline/snapshot",
        body={"baseline_id": "test-c4-idempotent"},
    )
    bid = snap["baseline_id"]

    try:
        # Pollute.
        _request("POST", ATDM, "/test-data/requests", body={"scenario": "expired_eligibility"})

        # Restore once.
        _request("POST", ATDM, "/test-data/baseline/restore", body={"baseline_id": bid})
        state_after_first = _state_hash()

        # Restore again — must be identical.
        _request("POST", ATDM, "/test-data/baseline/restore", body={"baseline_id": bid})
        state_after_second = _state_hash()

        assert state_after_first == state_after_second
    finally:
        _force_cleanup_all()


# -----------------------------------------------------------------------------
# Negative paths
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_baseline_restore_unknown_id_returns_404(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        ATDM,
        "/test-data/baseline/restore",
        body={"baseline_id": "does-not-exist-anywhere"},
    )
    assert code == 404
    assert "BASELINE_NOT_FOUND" in json.dumps(body)


@pytest.mark.integration
def test_baseline_list_works(compose_stack: None) -> None:
    code, body = _request("GET", ATDM, "/test-data/baseline/list", auth=False)
    assert code == 200
    assert isinstance(body["baselines"], list)


# -----------------------------------------------------------------------------
# Audit trail for strategy invocations
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_reset_all_emits_audit_events(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        ATDM,
        "/test-data/reset/all",
        headers={"X-Confirm": "yes"},
    )
    assert code == 200
    audit_run_id = body["audit_run_id"]

    acode, trail = _request("GET", ATDM, f"/audit/runs/{audit_run_id}", auth=False)
    assert acode == 200
    actions = [e["action"] for e in trail["events"]]
    assert "reset_started" in actions
    assert "reset_completed" in actions
