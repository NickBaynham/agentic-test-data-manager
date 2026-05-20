"""Unit tests for all 4 validators."""

from __future__ import annotations

from typing import Any

from app.validators.domain import denial_requires_invalid_code
from app.validators.relational import (
    claim_references_existing_member,
    eligibility_status_matches_member,
)
from app.validators.temporal import eligibility_window_contains_claim

RUN = "test-run"


def _bundle(**parts: Any) -> dict[str, Any]:
    return {"procedure_codes": [], "diagnosis_codes": [], **parts}


# -----------------------------------------------------------------------------
# eligibility_status_matches_member
# -----------------------------------------------------------------------------


def test_inactive_member_active_eligibility_rejected() -> None:
    r = eligibility_status_matches_member(
        _bundle(
            member={"status": "inactive", "member_id": "m"},
            eligibility={"status": "active", "member_id": "m"},
        )
    )
    assert r.ok is False
    assert "inactive" in r.message


def test_active_member_active_eligibility_accepted() -> None:
    r = eligibility_status_matches_member(
        _bundle(
            member={"status": "active", "member_id": "m"},
            eligibility={"status": "active", "member_id": "m"},
        )
    )
    assert r.ok is True


def test_active_member_inactive_eligibility_allowed() -> None:
    # Members can lose coverage mid-period.
    r = eligibility_status_matches_member(
        _bundle(
            member={"status": "active", "member_id": "m"},
            eligibility={"status": "inactive", "member_id": "m"},
        )
    )
    assert r.ok is True


def test_validator_skipped_when_member_or_eligibility_missing() -> None:
    assert eligibility_status_matches_member(_bundle()).ok is True


# -----------------------------------------------------------------------------
# claim_references_existing_member
# -----------------------------------------------------------------------------


def test_claim_matching_member_id_accepted() -> None:
    r = claim_references_existing_member(
        _bundle(
            member={"member_id": "m-1"},
            claim={"member_id": "m-1"},
        )
    )
    assert r.ok is True


def test_claim_with_mismatched_member_id_rejected() -> None:
    r = claim_references_existing_member(
        _bundle(
            member={"member_id": "m-1"},
            claim={"member_id": "m-WRONG"},
        )
    )
    assert r.ok is False


def test_claim_without_member_rejected() -> None:
    r = claim_references_existing_member(_bundle(claim={"member_id": "m-orphan"}))
    assert r.ok is False


# -----------------------------------------------------------------------------
# denial_requires_invalid_code
# -----------------------------------------------------------------------------


def test_denial_with_baseline_invalid_proc_accepted() -> None:
    r = denial_requires_invalid_code(
        _bundle(
            claim={
                "status": "denied",
                "procedure_code": "00000",
                "diagnosis_code": "Z00.00",
                "denial_reason": None,
            }
        )
    )
    assert r.ok is True


def test_denial_with_per_run_invalid_diag_accepted() -> None:
    r = denial_requires_invalid_code(
        {
            "procedure_codes": [],
            "diagnosis_codes": [{"code": "DC-X", "is_valid": False}],
            "claim": {
                "status": "denied",
                "procedure_code": "99213",
                "diagnosis_code": "DC-X",
                "denial_reason": None,
            },
        }
    )
    assert r.ok is True


def test_denial_with_only_denial_reason_accepted() -> None:
    r = denial_requires_invalid_code(
        _bundle(
            claim={
                "status": "denied",
                "procedure_code": "99213",
                "diagnosis_code": "Z00.00",
                "denial_reason": "out_of_pocket_max_reached",
            }
        )
    )
    assert r.ok is True


def test_denial_with_no_justification_rejected() -> None:
    r = denial_requires_invalid_code(
        _bundle(
            claim={
                "status": "denied",
                "procedure_code": "99213",
                "diagnosis_code": "Z00.00",
                "denial_reason": None,
            }
        )
    )
    assert r.ok is False


def test_non_denied_claim_skipped() -> None:
    r = denial_requires_invalid_code(
        _bundle(
            claim={
                "status": "paid",
                "procedure_code": "99213",
                "diagnosis_code": "Z00.00",
                "denial_reason": None,
            }
        )
    )
    assert r.ok is True


# -----------------------------------------------------------------------------
# eligibility_window_contains_claim
# -----------------------------------------------------------------------------


def test_pending_claim_within_window_accepted() -> None:
    r = eligibility_window_contains_claim(
        _bundle(
            claim={"status": "pending", "submitted_at": "2026-06-01T12:00:00+00:00"},
            eligibility={
                "status": "active",
                "effective_from": "2026-01-01",
                "effective_to": "2026-12-31",
            },
        )
    )
    assert r.ok is True


def test_denied_claim_outside_window_with_expired_eligibility_permitted() -> None:
    # expired_eligibility scenario is allowed even with submitted_at out of window.
    r = eligibility_window_contains_claim(
        _bundle(
            claim={"status": "denied", "submitted_at": "2026-06-01T12:00:00+00:00"},
            eligibility={
                "status": "expired",
                "effective_from": "2024-01-01",
                "effective_to": "2024-12-31",
            },
        )
    )
    assert r.ok is True


def test_denied_claim_outside_window_with_active_eligibility_rejected() -> None:
    r = eligibility_window_contains_claim(
        _bundle(
            claim={"status": "denied", "submitted_at": "2030-06-01T12:00:00+00:00"},
            eligibility={
                "status": "active",
                "effective_from": "2026-01-01",
                "effective_to": "2026-12-31",
            },
        )
    )
    assert r.ok is False


def test_paid_claim_outside_window_not_flagged() -> None:
    # Paid claims out of window are a different problem domain.
    r = eligibility_window_contains_claim(
        _bundle(
            claim={"status": "paid", "submitted_at": "2030-06-01T12:00:00+00:00"},
            eligibility={
                "status": "active",
                "effective_from": "2026-01-01",
                "effective_to": "2026-12-31",
            },
        )
    )
    assert r.ok is True


def test_unparseable_dates_rejected() -> None:
    r = eligibility_window_contains_claim(
        _bundle(
            claim={"status": "denied", "submitted_at": "garbage"},
            eligibility={
                "status": "active",
                "effective_from": "2026-01-01",
                "effective_to": "2026-12-31",
            },
        )
    )
    assert r.ok is False
