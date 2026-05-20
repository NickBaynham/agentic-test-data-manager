"""Relational consistency validators.

These check cross-entity correctness — the kind of thing that wouldn't be
caught by per-entity Pydantic validators or DB CHECKs but would either
violate domain rules or break later workflows.
"""

from __future__ import annotations

from typing import Any

from app.validators import ValidationResult


def eligibility_status_matches_member(bundle: dict[str, Any]) -> ValidationResult:
    """A member with status='inactive' shall not have eligibility status='active'.

    The reverse (active member, inactive eligibility) is allowed — members
    can lose coverage mid-period.
    """
    name = "relational.eligibility_status_matches_member"
    member = bundle.get("member")
    eligibility = bundle.get("eligibility")
    if not member or not eligibility:
        return ValidationResult(ok=True, validator=name)

    if member["status"] == "inactive" and eligibility["status"] == "active":
        return ValidationResult(
            ok=False,
            validator=name,
            message="inactive member cannot have active eligibility",
            details={
                "member_status": member["status"],
                "eligibility_status": eligibility["status"],
            },
        )
    return ValidationResult(ok=True, validator=name)


def claim_references_existing_member(bundle: dict[str, Any]) -> ValidationResult:
    """Claim.member_id must refer to the Member in the same bundle.

    Cross-run member references are rejected at the agent layer (they would
    also fail at the DB FK, but catching here gives a cleaner error).
    """
    name = "relational.claim_references_existing_member"
    claim = bundle.get("claim")
    member = bundle.get("member")
    if not claim:
        return ValidationResult(ok=True, validator=name)
    if not member:
        return ValidationResult(
            ok=False,
            validator=name,
            message="claim references a member that is not in the bundle",
            details={"claim_member_id": claim["member_id"]},
        )
    if claim["member_id"] != member["member_id"]:
        return ValidationResult(
            ok=False,
            validator=name,
            message="claim.member_id does not match member.member_id in the bundle",
            details={
                "claim_member_id": claim["member_id"],
                "bundle_member_id": member["member_id"],
            },
        )
    return ValidationResult(ok=True, validator=name)
