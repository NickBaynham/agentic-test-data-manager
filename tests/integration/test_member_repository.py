"""Phase 2 integration tests for the Member repository and internal routes.

Tests run against the live docker compose stack. Each test uses a unique
test_run_id so it can clean up its own rows without interfering with sibling
tests.

Maps to PLAN.md Phase 2 exit criteria:
  - schema present (verified via psql via docker exec)
  - insert/count/delete round-trip works
  - FAKE_ CHECK fails on a non-prefixed name
  - ZZ CHECK fails on a non-ZZ state
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
import uuid

import pytest

from tests.integration.conftest import COMPOSE_BASE, REPO_ROOT

TARGET_SUT = "http://localhost:18000"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _post_json(path: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
    req = urllib.request.Request(
        f"{TARGET_SUT}{path}",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _delete(path: str) -> tuple[int, dict[str, object]]:
    req = urllib.request.Request(f"{TARGET_SUT}{path}", method="DELETE")
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        return resp.status, json.loads(resp.read())


def _psql(sql: str) -> str:
    """Run a SQL statement inside the Postgres container and return stdout."""
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


def _new_run_id() -> str:
    return f"itest-{uuid.uuid4().hex[:12]}"


def _insert_plan_for_run(run_id: str) -> str:
    """Insert a Plan row tagged with run_id and return the plan_id."""
    plan_id = f"plan-{run_id}"
    _psql(
        "INSERT INTO plan (plan_id, name, coverage_type, effective_date, test_run_id) "
        f"VALUES ('{plan_id}', 'Test Plan', 'hmo', '2026-01-01', '{run_id}');"
    )
    return plan_id


def _cleanup_run(run_id: str) -> None:
    _psql(f"DELETE FROM member WHERE test_run_id = '{run_id}';")
    _psql(f"DELETE FROM plan   WHERE test_run_id = '{run_id}';")


def _valid_member(member_id: str, plan_id: str, run_id: str) -> dict[str, object]:
    return {
        "member_id": member_id,
        "status": "active",
        "first_name": "FAKE_Alice",
        "last_name": "FAKE_Smith",
        "date_of_birth": "1990-04-12",
        "address": {
            "line1": "1 FAKE_Way",
            "city": "FAKE_Town",
            "state": "ZZ",
            "zip": "00000",
        },
        "plan_id": plan_id,
        "test_run_id": run_id,
    }


# -----------------------------------------------------------------------------
# Schema sanity
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_schema_has_seven_tables(compose_stack: None) -> None:
    """All seven entities from BRD §9 exist as tables."""
    out = _psql("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;")
    tables = set(out.splitlines())
    expected = {
        "claim",
        "diagnosis_code",
        "eligibility",
        "member",
        "plan",
        "procedure_code",
        "provider",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


@pytest.mark.integration
def test_baseline_reference_data_seeded(compose_stack: None) -> None:
    """Shared procedure_code / diagnosis_code rows exist (test_run_id IS NULL)."""
    pc_count = int(_psql("SELECT COUNT(*) FROM procedure_code WHERE test_run_id IS NULL;"))
    dc_count = int(_psql("SELECT COUNT(*) FROM diagnosis_code WHERE test_run_id IS NULL;"))
    assert pc_count >= 4, f"procedure_code baseline count: {pc_count}"
    assert dc_count >= 4, f"diagnosis_code baseline count: {dc_count}"


# -----------------------------------------------------------------------------
# Happy path
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_insert_count_delete_round_trip(compose_stack: None) -> None:
    """PLAN.md Phase 2 headline exit criterion: insert → count=1 → delete → count=0."""
    run_id = _new_run_id()
    try:
        plan_id = _insert_plan_for_run(run_id)
        member = _valid_member(f"m-{run_id}", plan_id, run_id)

        status_code, body = _post_json("/internal/members", member)
        assert status_code == 201, body
        assert body == {"member_id": member["member_id"], "status": "created"}

        count_before = int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_id}';"))
        assert count_before == 1

        status_code, body = _delete(f"/internal/members?run_id={run_id}")
        assert status_code == 200
        assert body == {"run_id": run_id, "deleted_count": 1}

        count_after = int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_id}';"))
        assert count_after == 0
    finally:
        _cleanup_run(run_id)


@pytest.mark.integration
def test_run_id_scoping_isolates_records(compose_stack: None) -> None:
    """Deleting by run_id A leaves run_id B intact (DR-001)."""
    run_a = _new_run_id()
    run_b = _new_run_id()
    try:
        plan_a = _insert_plan_for_run(run_a)
        plan_b = _insert_plan_for_run(run_b)

        _post_json("/internal/members", _valid_member(f"m-a-{run_a}", plan_a, run_a))
        _post_json("/internal/members", _valid_member(f"m-b-{run_b}", plan_b, run_b))

        _delete(f"/internal/members?run_id={run_a}")

        assert int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_a}';")) == 0
        assert int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_b}';")) == 1
    finally:
        _cleanup_run(run_a)
        _cleanup_run(run_b)


# -----------------------------------------------------------------------------
# Validation paths — pydantic-level (422 before DB)
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_first_name_without_fake_prefix_rejected_by_pydantic(compose_stack: None) -> None:
    """Pydantic catches NFR-010 marker before SQL fires — fast feedback."""
    run_id = _new_run_id()
    try:
        plan_id = _insert_plan_for_run(run_id)
        member = _valid_member(f"m-{run_id}", plan_id, run_id)
        member["first_name"] = "Bob"  # no FAKE_ prefix

        status_code, body = _post_json("/internal/members", member)
        assert status_code == 422
        # FastAPI emits a list of validation errors; just confirm our message bubbles up.
        assert "FAKE_" in json.dumps(body)
    finally:
        _cleanup_run(run_id)


@pytest.mark.integration
def test_address_state_not_zz_rejected_by_pydantic(compose_stack: None) -> None:
    run_id = _new_run_id()
    try:
        plan_id = _insert_plan_for_run(run_id)
        member = _valid_member(f"m-{run_id}", plan_id, run_id)
        member["address"] = {**member["address"], "state": "CA"}  # type: ignore[dict-item]

        status_code, body = _post_json("/internal/members", member)
        assert status_code == 422
        assert "ZZ" in json.dumps(body)
    finally:
        _cleanup_run(run_id)


# -----------------------------------------------------------------------------
# Validation paths — DB-level (CHECK enforcement as a second wall)
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_fake_prefix_check_enforced_at_db(compose_stack: None) -> None:
    """Bypass Pydantic by inserting directly via psql. DB CHECK must reject 'Bob'."""
    run_id = _new_run_id()
    plan_id = _insert_plan_for_run(run_id)
    try:
        # Direct SQL insert with 'Bob' as first_name. Should fail with check violation.
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
                "-c",
                f"""
                INSERT INTO member (member_id, status, first_name, last_name,
                    date_of_birth, address_line1, address_city, address_state,
                    address_zip, plan_id, test_run_id)
                VALUES ('m-{run_id}', 'active', 'Bob', 'FAKE_Smith',
                    '1990-04-12', '1 FAKE_Way', 'FAKE_Town', 'ZZ', '00000',
                    '{plan_id}', '{run_id}');
                """,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, "INSERT should have failed but succeeded"
        assert "check constraint" in (result.stdout + result.stderr).lower()
    finally:
        _cleanup_run(run_id)


@pytest.mark.integration
def test_zz_state_check_enforced_at_db(compose_stack: None) -> None:
    """Bypass Pydantic by inserting directly via psql. DB CHECK must reject state='CA'."""
    run_id = _new_run_id()
    plan_id = _insert_plan_for_run(run_id)
    try:
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
                "-c",
                f"""
                INSERT INTO member (member_id, status, first_name, last_name,
                    date_of_birth, address_line1, address_city, address_state,
                    address_zip, plan_id, test_run_id)
                VALUES ('m-{run_id}', 'active', 'FAKE_Alice', 'FAKE_Smith',
                    '1990-04-12', '1 FAKE_Way', 'FAKE_Town', 'CA', '00000',
                    '{plan_id}', '{run_id}');
                """,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, "INSERT should have failed but succeeded"
        assert "check constraint" in (result.stdout + result.stderr).lower()
    finally:
        _cleanup_run(run_id)


# -----------------------------------------------------------------------------
# FK violation surfaces as 422 (not 500)
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_member_with_unknown_plan_id_returns_422(compose_stack: None) -> None:
    run_id = _new_run_id()
    try:
        member = _valid_member(f"m-{run_id}", "plan-does-not-exist", run_id)
        status_code, body = _post_json("/internal/members", member)
        assert status_code == 422
        details = json.dumps(body)
        assert "FK_VIOLATION" in details or "plan" in details.lower()
    finally:
        _cleanup_run(run_id)


# -----------------------------------------------------------------------------
# Duplicate primary key returns 409
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_duplicate_member_id_returns_409(compose_stack: None) -> None:
    run_id = _new_run_id()
    try:
        plan_id = _insert_plan_for_run(run_id)
        member = _valid_member(f"m-{run_id}", plan_id, run_id)

        status_code, _ = _post_json("/internal/members", member)
        assert status_code == 201

        status_code_again, body = _post_json("/internal/members", member)
        assert status_code_again == 409
        assert "MEMBER_ALREADY_EXISTS" in json.dumps(body)
    finally:
        _cleanup_run(run_id)
