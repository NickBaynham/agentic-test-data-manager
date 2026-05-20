"""Unit tests for all 7 generators.

Pure functions — no Docker required. Tests assert determinism (same seed +
run_id ⇒ identical output) and NFR-010 markers.
"""

from __future__ import annotations

from app.generators.claim import generate_claim
from app.generators.codes import generate_diagnosis_code, generate_procedure_code
from app.generators.eligibility import generate_eligibility
from app.generators.member import generate_member
from app.generators.plan import generate_plan
from app.generators.provider import generate_provider

RUN = "01TESTRUN"


def test_plan_is_deterministic() -> None:
    a = generate_plan(42, RUN, {})
    b = generate_plan(42, RUN, {})
    assert a == b
    assert a["plan_id"] == f"plan-{RUN}"
    assert a["coverage_type"] in ("hmo", "ppo", "epo", "pos")


def test_provider_honors_network_constraint() -> None:
    out_of = generate_provider(1, RUN, {"provider_network": "out_of_network"})
    assert out_of["network_status"] == "out_of_network"
    in_net = generate_provider(1, RUN, {"provider_network": "in_network"})
    assert in_net["network_status"] == "in_network"


def test_provider_falls_back_to_in_network_for_garbage() -> None:
    p = generate_provider(1, RUN, {"provider_network": "garbage"})
    assert p["network_status"] == "in_network"


def test_member_has_fake_markers_and_zz_state() -> None:
    m = generate_member(7, RUN, {})
    assert m["first_name"].startswith("FAKE_")
    assert m["last_name"].startswith("FAKE_")
    assert m["address"]["state"] == "ZZ"
    assert m["address"]["city"].startswith("FAKE_")
    assert m["member_id"] == f"m-{RUN}"
    assert m["plan_id"] == f"plan-{RUN}"


def test_member_honors_status_constraint() -> None:
    active = generate_member(1, RUN, {"member_status": "active"})
    inactive = generate_member(1, RUN, {"member_status": "inactive"})
    assert active["status"] == "active"
    assert inactive["status"] == "inactive"


def test_eligibility_window_variants() -> None:
    current = generate_eligibility(1, RUN, {"eligibility_window": "current"})
    expired = generate_eligibility(1, RUN, {"eligibility_window": "expired_last_year"})
    future = generate_eligibility(1, RUN, {"eligibility_window": "future"})
    assert current["effective_from"] < current["effective_to"]
    assert expired["effective_to"] < current["effective_to"]
    assert future["effective_from"] > current["effective_from"]
    assert current["member_id"] == f"m-{RUN}"


def test_claim_denial_uses_invalid_codes_by_default() -> None:
    c = generate_claim(1, RUN, {"claim_status": "denied"})
    assert c["status"] == "denied"
    assert c["procedure_code"] == "00000"
    assert c["diagnosis_code"] == "ZZZ.99"
    assert c["denial_reason"] == "invalid_procedure_code"


def test_claim_paid_has_no_denial_reason() -> None:
    c = generate_claim(1, RUN, {"claim_status": "paid"})
    assert c["status"] == "paid"
    assert c["denial_reason"] is None


def test_claim_pending_has_no_denial_reason() -> None:
    c = generate_claim(1, RUN, {"claim_status": "pending"})
    assert c["status"] == "pending"
    assert c["denial_reason"] is None


def test_claim_fallback_for_garbage_status() -> None:
    c = generate_claim(1, RUN, {"claim_status": "garbage"})
    assert c["status"] == "paid"


def test_claim_explicit_codes_override_defaults() -> None:
    c = generate_claim(
        1,
        RUN,
        {"claim_status": "denied", "procedure_code": "X1", "diagnosis_code": "X2"},
    )
    assert c["procedure_code"] == "X1"
    assert c["diagnosis_code"] == "X2"


def test_procedure_code_generator() -> None:
    pc = generate_procedure_code(
        1, RUN, {"procedure_code": "TEST", "procedure_code_is_valid": False}
    )
    assert pc["code"] == "TEST"
    assert pc["is_valid"] is False
    assert pc["test_run_id"] == RUN


def test_diagnosis_code_generator_defaults() -> None:
    dc = generate_diagnosis_code(1, RUN, {})
    assert dc["code"] == f"DC-{RUN}"
    assert dc["is_valid"] is True
