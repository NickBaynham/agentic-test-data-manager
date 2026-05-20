"""Healthcare seeder (Phase 4).

New flow:
  1. Generate all records by invoking the scenario's generators in order.
  2. Run the scenario's validators against the generated bundle. If any
     validator fails, raise ValidatorRejected — no DB writes occur.
  3. POST the bundle to Target SUT's /internal/scenarios/seed in one atomic
     transaction. FK / CHECK / unique violations roll back the whole bundle
     server-side.

Saga compensation was removed in Phase 4 — the server-side transaction makes
the agent-side compensating-delete pattern from Phase 3 unnecessary.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx

from app.agents.planner import Plan
from app.generators import claim as claim_gen
from app.generators import codes as codes_gen
from app.generators import eligibility as eligibility_gen
from app.generators import member as member_gen
from app.generators import plan as plan_gen
from app.generators import provider as provider_gen
from app.validators import ValidationResult
from app.validators.registry import get_validator


class SeedError(Exception):
    """Bundle insert failed at the Target SUT (network or server error)."""

    def __init__(self, message: str, *, step: str, downstream_status: int | None = None) -> None:
        super().__init__(message)
        self.step = step
        self.downstream_status = downstream_status


class ValidatorRejected(Exception):
    """A scenario's validator(s) rejected the generated bundle."""

    def __init__(self, results: list[ValidationResult]) -> None:
        super().__init__("validators rejected the plan")
        self.results = results


GeneratorFn = Callable[[int, str, dict[str, Any] | None], dict[str, Any]]

# Generator name -> (callable, bundle key). Codes have list bundle keys.
_GENERATORS: dict[str, tuple[GeneratorFn, str]] = {
    "generate_plan": (plan_gen.generate_plan, "plan"),
    "generate_provider": (provider_gen.generate_provider, "provider"),
    "generate_member": (member_gen.generate_member, "member"),
    "generate_eligibility": (eligibility_gen.generate_eligibility, "eligibility"),
    "generate_claim": (claim_gen.generate_claim, "claim"),
    "generate_procedure_code": (codes_gen.generate_procedure_code, "_proc_code"),
    "generate_diagnosis_code": (codes_gen.generate_diagnosis_code, "_diag_code"),
}


def target_sut_base_url() -> str:
    return os.environ.get("TARGET_SUT_URL", "http://target-healthcare-api:8000")


def _seed_for_step(idx: int, run_id: str) -> int:
    return (abs(hash(run_id)) + idx) % (2**31)


def generate_bundle(
    generator_names: list[str],
    test_run_id: str,
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """Run each named generator in order; collect into a bundle dict."""
    bundle: dict[str, Any] = {"procedure_codes": [], "diagnosis_codes": []}
    for idx, name in enumerate(generator_names):
        entry = _GENERATORS.get(name)
        if entry is None:
            raise SeedError(f"unknown generator {name!r}", step=name)
        gen_fn, bundle_key = entry
        record = gen_fn(_seed_for_step(idx, test_run_id), test_run_id, constraints)
        if bundle_key == "_proc_code":
            bundle["procedure_codes"].append(record)
        elif bundle_key == "_diag_code":
            bundle["diagnosis_codes"].append(record)
        else:
            bundle[bundle_key] = record
    return bundle


def run_validators(
    validator_names: list[str],
    bundle: dict[str, Any],
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for name in validator_names:
        validator = get_validator(name)
        if validator is None:
            results.append(
                ValidationResult(
                    ok=False,
                    validator=name,
                    message=f"unknown validator {name!r}",
                )
            )
            continue
        results.append(validator(bundle))
    return results


async def execute_plan(
    plan: Plan,
    scenario_validators: list[str],
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, Any], list[ValidationResult]]:
    """Generate → validate → bundle insert.

    Returns (bundle_actually_seeded, all_validator_results).
    Raises ValidatorRejected on validation failure.
    Raises SeedError on Target SUT failure.
    """
    generator_names = [step.generator for step in plan.steps]
    bundle = generate_bundle(generator_names, plan.test_run_id, plan.constraints)

    results = run_validators(scenario_validators, bundle)
    failed = [r for r in results if not r.ok]
    if failed:
        raise ValidatorRejected(failed)

    own_client = False
    if client is None:
        client = httpx.AsyncClient(base_url=target_sut_base_url(), timeout=10.0)
        own_client = True
    try:
        try:
            resp = await client.post("/internal/scenarios/seed", json=bundle)
        except httpx.HTTPError as e:
            raise SeedError(
                f"network failure posting bundle: {e}",
                step="scenarios/seed",
            ) from e

        if resp.status_code not in (200, 201):
            raise SeedError(
                f"/internal/scenarios/seed returned {resp.status_code}: {resp.text}",
                step="scenarios/seed",
                downstream_status=resp.status_code,
            )

        return bundle, results
    finally:
        if own_client:
            await client.aclose()


async def reset_run(
    run_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, int]:
    """Delete every entity for a run via the atomic bundle DELETE.

    Phase 5 will extend this to support the full reset_run / reset_all
    strategy surface.
    """
    own_client = False
    if client is None:
        client = httpx.AsyncClient(base_url=target_sut_base_url(), timeout=10.0)
        own_client = True
    try:
        resp = await client.delete("/internal/scenarios", params={"run_id": run_id})
        if resp.status_code != 200:
            raise SeedError(
                f"/internal/scenarios DELETE returned {resp.status_code}: {resp.text}",
                step="reset_scenario",
                downstream_status=resp.status_code,
            )
        body = resp.json()
        counts = body.get("deleted_counts", {})
        return {k: int(v) for k, v in counts.items()}
    finally:
        if own_client:
            await client.aclose()
