"""Unit tests for the seeder.

Covers the validator-rejection path (B2) and the unknown-generator path (B4
proxy — generator failure raises SeedError, no DB writes occur because the
bundle never reaches the Target SUT).
"""

from __future__ import annotations

import pytest

from app.agents.planner import Plan, PlanStep
from app.seeders.healthcare import (
    SeedError,
    ValidatorRejected,
    execute_plan,
    generate_bundle,
    run_validators,
)


def test_generate_bundle_combines_records() -> None:
    bundle = generate_bundle(
        ["generate_plan", "generate_member"],
        "RUN1",
        {"member_status": "active"},
    )
    assert bundle["plan"]["plan_id"] == "plan-RUN1"
    assert bundle["member"]["member_id"] == "m-RUN1"


def test_generate_bundle_unknown_generator_raises() -> None:
    with pytest.raises(SeedError) as exc:
        generate_bundle(["bogus_generator"], "RUN1", {})
    assert exc.value.step == "bogus_generator"


def test_run_validators_unknown_name_returns_failure() -> None:
    results = run_validators(["validators.bogus"], {})
    assert len(results) == 1
    assert results[0].ok is False
    assert "unknown" in results[0].message


async def test_execute_plan_validator_failure_skips_bundle_post() -> None:
    """Validator failure raises ValidatorRejected and never POSTs the bundle."""
    plan = Plan(
        scenario_id="test",
        test_run_id="RUN1",
        constraints={"member_status": "inactive", "eligibility_status": "active"},
        steps=[
            PlanStep(generator="generate_plan"),
            PlanStep(generator="generate_provider"),
            PlanStep(generator="generate_member"),
            PlanStep(generator="generate_eligibility"),
            PlanStep(generator="generate_claim"),
        ],
    )
    with pytest.raises(ValidatorRejected) as exc:
        await execute_plan(plan, ["relational.eligibility_status_matches_member"])
    assert any(
        r.validator == "relational.eligibility_status_matches_member" for r in exc.value.results
    )


def _happy_plan() -> Plan:
    return Plan(
        scenario_id="active_member_clean",
        test_run_id="RUN-OK",
        constraints={
            "member_status": "active",
            "eligibility_status": "active",
            "claim_status": "paid",
        },
        steps=[
            PlanStep(generator="generate_plan"),
            PlanStep(generator="generate_provider"),
            PlanStep(generator="generate_member"),
            PlanStep(generator="generate_eligibility"),
            PlanStep(generator="generate_claim"),
        ],
    )


async def test_execute_plan_success_with_mocked_sut() -> None:
    """Mock the Target SUT — execute_plan returns the bundle on 201."""
    import httpx

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/scenarios/seed"
        assert request.method == "POST"
        captured["called"] = True
        return httpx.Response(201, json={"status": "seeded", "counts": {"plan": 1}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://stub",
    )
    try:
        bundle, results = await execute_plan(_happy_plan(), [], client=client)
        assert captured["called"] is True
        assert bundle["plan"]["plan_id"] == "plan-RUN-OK"
        assert results == []
    finally:
        await client.aclose()


async def test_execute_plan_raises_seed_error_on_500() -> None:
    import httpx

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://stub",
    )
    try:
        with pytest.raises(SeedError) as exc:
            await execute_plan(_happy_plan(), [], client=client)
        assert exc.value.downstream_status == 500
    finally:
        await client.aclose()


async def test_reset_run_returns_counts() -> None:
    import httpx

    from app.seeders.healthcare import reset_run

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/internal/scenarios"
        assert request.url.params["run_id"] == "RUN-OK"
        return httpx.Response(
            200,
            json={"run_id": "RUN-OK", "deleted_counts": {"member": 1, "plan": 1}},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://stub",
    )
    try:
        counts = await reset_run("RUN-OK", client=client)
        assert counts == {"member": 1, "plan": 1}
    finally:
        await client.aclose()


async def test_reset_run_raises_on_non_200() -> None:
    import httpx

    from app.seeders.healthcare import reset_run

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://stub",
    )
    try:
        with pytest.raises(SeedError) as exc:
            await reset_run("RUN-OK", client=client)
        assert exc.value.downstream_status == 503
    finally:
        await client.aclose()
