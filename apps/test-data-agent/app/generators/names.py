"""Fixed pools of FAKE_ names used by deterministic generators.

All entries carry the FAKE_ prefix required by NFR-010. Lists are stable across
versions — adding new names is fine, removing or reordering breaks
reproducibility for runs seeded with prior pool indexes.
"""

FAKE_FIRST_NAMES: tuple[str, ...] = (
    "FAKE_Alice",
    "FAKE_Bob",
    "FAKE_Carol",
    "FAKE_David",
    "FAKE_Eve",
    "FAKE_Frank",
    "FAKE_Grace",
    "FAKE_Hank",
    "FAKE_Iris",
    "FAKE_Jack",
)

FAKE_LAST_NAMES: tuple[str, ...] = (
    "FAKE_Smith",
    "FAKE_Jones",
    "FAKE_Brown",
    "FAKE_Davis",
    "FAKE_Wilson",
    "FAKE_Taylor",
    "FAKE_Anderson",
    "FAKE_Thomas",
    "FAKE_Moore",
    "FAKE_Martin",
)

FAKE_CITY_NAMES: tuple[str, ...] = (
    "FAKE_Springfield",
    "FAKE_Riverside",
    "FAKE_Lakewood",
    "FAKE_Centerville",
)

PLAN_NAMES: tuple[str, ...] = (
    "Bronze Health Plan",
    "Silver Health Plan",
    "Gold Health Plan",
    "Platinum Health Plan",
)
