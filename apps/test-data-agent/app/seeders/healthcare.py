"""Healthcare seeder.

Executes a resolved Plan against the Target SUT over HTTP. Order matters:
parents before children (Plan → Member → Eligibility → Claim). On any failure,
compensate by deleting in reverse order — every entity is `test_run_id`-tagged
so cleanup is deterministic.

Phase 3 only knows two generators: `generate_plan` and `generate_member`.
Phase 4 adds the remaining five.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

import httpx

from app.agents.planner import Plan
from app.generators import member as member_gen
from app.generators import plan as plan_gen


class SeedError(Exception):
    """Raised when a seeder step fails. The agent maps this to HTTP 502/500
    depending on the failure mode."""

    def __init__(self, message: str, *, step: str, downstream_status: int | None = None) -> None:
        super().__init__(message)
        self.step = step
        self.downstream_status = downstream_status


# Map a step's generator name to (which entity collection it lands in, the
# Target SUT route to POST it to, and the route to DELETE-by-run on compensation).
_GENERATOR_TO_ROUTES: dict[str, tuple[str, str]] = {
    "generate_plan": ("/internal/plans", "/internal/plans"),
    "generate_member": ("/internal/members", "/internal/members"),
}


def _seed_for_step(step_index: int, run_id: str) -> int:
    """Stable per-step seed derived from run_id + step_index."""
    return (abs(hash(run_id)) + step_index) % (2**31)


def _run_generator(name: str, seed: int, run_id: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "generate_plan":
        return plan_gen.generate_plan(seed, run_id, args)
    if name == "generate_member":
        plan_id = args.get("_plan_id")
        if not isinstance(plan_id, str):
            raise SeedError(
                "generate_member needs a _plan_id in args (seeder must inject it)",
                step=name,
            )
        return member_gen.generate_member(seed, run_id, plan_id, args)
    raise SeedError(f"unknown generator {name!r}", step=name)


def target_sut_base_url() -> str:
    return os.environ.get("TARGET_SUT_URL", "http://target-healthcare-api:8000")


async def execute_plan(plan: Plan, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Execute a resolved Plan against the Target SUT.

    Returns a dict of {entity_kind: record_dict} for the records that were
    inserted. On failure, compensates by DELETE'ing every entity inserted so
    far (in reverse order), then raises SeedError.
    """
    own_client = False
    if client is None:
        client = httpx.AsyncClient(base_url=target_sut_base_url(), timeout=10.0)
        own_client = True

    inserted: list[str] = []  # delete routes, reverse order on compensation
    results: dict[str, dict[str, Any]] = {}
    plan_id_from_step: str | None = None

    try:
        for idx, step in enumerate(plan.steps):
            args = dict(step.args)
            if step.generator == "generate_member" and plan_id_from_step is not None:
                args["_plan_id"] = plan_id_from_step

            record = _run_generator(
                step.generator,
                _seed_for_step(idx, plan.test_run_id),
                plan.test_run_id,
                args,
            )

            post_route, delete_route = _GENERATOR_TO_ROUTES[step.generator]
            try:
                resp = await client.post(post_route, json=record)
            except httpx.HTTPError as e:
                raise SeedError(
                    f"network failure posting to {post_route}: {e}",
                    step=step.generator,
                ) from e

            if resp.status_code not in (200, 201):
                raise SeedError(
                    f"{post_route} returned {resp.status_code}: {resp.text}",
                    step=step.generator,
                    downstream_status=resp.status_code,
                )

            inserted.append(delete_route)
            if step.generator == "generate_plan":
                plan_id_from_step = record["plan_id"]
                results["plan"] = record
            elif step.generator == "generate_member":
                results["member"] = record

        return results

    except SeedError:
        await _compensate(client, inserted, plan.test_run_id)
        raise
    finally:
        if own_client:
            await client.aclose()


async def _compensate(
    client: httpx.AsyncClient,
    delete_routes: Iterable[str],
    run_id: str,
) -> None:
    """Best-effort: DELETE each entity collection by run_id in REVERSE order."""
    for route in reversed(list(delete_routes)):
        try:
            await client.delete(route, params={"run_id": run_id})
        except httpx.HTTPError:
            # Compensation is best-effort; original error surfaces.
            continue


async def reset_run(
    run_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, int]:
    """Delete every entity collection by run_id in dependency-safe order:
    Member (FK to Plan) first, then Plan. Returns deleted counts.

    Phase 3 covers Plan + Member only. Phase 5 extends to all 5 mutable
    entities and the full reset_run / reset_all strategy surface.
    """
    own_client = False
    if client is None:
        client = httpx.AsyncClient(base_url=target_sut_base_url(), timeout=10.0)
        own_client = True

    counts: dict[str, int] = {}
    try:
        for route, kind in (("/internal/members", "member"), ("/internal/plans", "plan")):
            resp = await client.delete(route, params={"run_id": run_id})
            if resp.status_code != 200:
                raise SeedError(
                    f"{route} returned {resp.status_code}: {resp.text}",
                    step=f"reset_{kind}",
                    downstream_status=resp.status_code,
                )
            body = resp.json()
            counts[kind] = int(body.get("deleted_count", 0))
        return counts
    finally:
        if own_client:
            await client.aclose()
