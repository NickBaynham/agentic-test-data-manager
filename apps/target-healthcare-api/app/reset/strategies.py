"""Server-side reset strategies for the Target SUT.

Phase 5 adds three server-side strategies on top of Phase 4's atomic bundle
DELETE (which powers `reset_run`):

  - reset_all_tagged   — DELETE WHERE test_run_id IS NOT NULL on every table.
                          Baseline reference rows (NULL) survive.
  - snapshot_baseline  — Write every table to Parquet in MinIO and a manifest.json.
  - restore_baseline   — TRUNCATE all 7 tables, re-insert from Parquet.

snapshot/restore is implemented server-side (not in the agent) because the
SUT owns the schema and the data. The agent orchestrates via thin HTTP
wrappers and writes audit events.
"""

from __future__ import annotations

# Table order matters for FK-safe restore.
# Inserts go child-before-parent? No — Postgres FK requires parent FIRST.
# Restore inserts in FK_INSERT_ORDER; truncate uses CASCADE.
FK_INSERT_ORDER: list[str] = [
    "procedure_code",
    "diagnosis_code",
    "plan",
    "provider",
    "member",
    "eligibility",
    "claim",
]

# Tables that get cleared by reset_all_tagged (mutable; have test_run_id NOT NULL
# OR test_run_id NULL for shared reference rows we preserve).
MUTABLE_TABLES: list[str] = ["claim", "eligibility", "member", "plan", "provider"]

# Reference tables: baseline rows (test_run_id IS NULL) preserved, per-run cleared.
REFERENCE_TABLES: list[str] = ["procedure_code", "diagnosis_code"]
