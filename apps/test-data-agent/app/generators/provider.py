"""Deterministic Provider generator."""

from __future__ import annotations

import random
from typing import Any

from app.generators.names import FAKE_LAST_NAMES


def generate_provider(
    seed: int,
    test_run_id: str,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed + 2)
    constraints = constraints or {}
    network = str(constraints.get("provider_network", "in_network"))
    if network not in ("in_network", "out_of_network"):
        network = "in_network"
    return {
        "provider_id": f"prov-{test_run_id}",
        "name": f"FAKE_Clinic_{rng.choice(FAKE_LAST_NAMES).split('_', 1)[1]}",
        "network_status": network,
        "npi_fake": f"{seed % 10_000_000_000:010d}",
        "test_run_id": test_run_id,
    }
