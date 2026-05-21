# Design Decisions

This document records the architectural calls that shape ATDM. Each entry
names the decision, the alternatives considered, and the consequences.
Decisions that prove wrong are amended in place with a strikethrough and a
pointer to the replacement, so the history of the architecture is legible.

## D1. Rule-based planner is the default; LLM planner is Phase 2

**Decision.** `ATDM_PLANNER=rule` is the only working mode in MVP. Setting
`ATDM_PLANNER=llm` short-circuits to HTTP 501 (`LLM_MODE_NOT_ENABLED`).

**Alternatives considered.**

- Ship LLM planning in MVP. Rejected — non-determinism on a reviewer's
  laptop, outbound API calls on the demo critical path, prompt-engineering
  ratholes.
- Skip LLM mode entirely. Rejected — the architectural story is "tool-bounded
  LLM where the validator gates the agent's plan." Ship the flag (501-stub)
  so the surface is visible from MVP; flip on in Phase 2 with prompt logging
  + reviewer UI.

**Consequence.** All Phase 3–8 scenarios are deterministic. The differentiator
in MVP is the safety architecture (validator-gated, audited, reversible),
not the LLM.

## D2. Server-side transactions for atomicity, not application-level sagas

**Decision.** Phase 4's `POST /internal/scenarios/seed` opens a single
Postgres transaction on the Target SUT side and inserts every entity in FK
order. A FK / CHECK / unique violation rolls the entire bundle back.

**Alternatives considered.**

- Saga-with-compensation in the agent (Phase 3's pattern). Rejected for
  Phase 4+ — saga compensation is best-effort and adds ~150 lines of
  bookkeeping. Server-side transactions are atomic by construction.

**Consequence.** The agent's seeder is simpler (no `inserted: list[str]`
tracking). The SUT becomes the authority on atomicity. AR-003 still holds
because the SUT, not the agent, is the one writing SQL.

## D3. Snapshot/restore lives in the SUT, not the agent

**Decision.** `apps/target-healthcare-api/app/reset/snapshotter.py`
implements snapshot/restore via PyArrow + MinIO directly. The agent's
`POST /test-data/baseline/snapshot` is a thin HTTP wrapper that emits audit
events around the SUT call.

**Alternatives considered.**

- Snapshot/restore in the agent (PLAN.md's original placement). Rejected —
  the agent would need raw DB access (AR-003 violation) or a generic
  `dump/restore` HTTP surface on the SUT.
- pg_dump / pg_restore. Rejected — PLAN.md commits to Parquet for the
  lakehouse story.

**Consequence.** The SUT depends on MinIO (slight layering compromise), but
the agent stays SQL-free. Restore uses `TRUNCATE ... CASCADE` + replay from
Parquet — two SQL statements total.

## D4. Cleanup tokens stored as sha256, never plaintext

**Decision.** Per DR-007, the catalog records `cleanup_token_sha256` only.
Plain tokens are returned in the API response once at creation; thereafter
no surface can produce the plaintext.

**Alternatives considered.** Store plaintext in a private MinIO bucket.
Rejected — even if "private," any reader of the catalog (a Phase 9 query
tool, an audit report) could replay deletion.

**Consequence.** `reset_run` verifies by hashing the caller's submitted
token and comparing. A token leak (e.g., from a logfile) is harder to
exploit because the catalog never reveals expected tokens.

## D5. Every state mutation gets an audit `test_run_id`

**Decision.** Strategy invocations (`reset_all`, `baseline_snapshot`,
`baseline_restore`) get synthetic `strategy-{name}-{ULID}` IDs. They appear
in `GET /audit/runs/{id}` just like scenario runs.

**Consequence.** A reviewer can click from "a destructive action happened"
to "who, when, and what changed" without a separate audit subsystem.

## D6. Audit log is append-only at the API layer (NFR-011)

**Decision.** No DELETE / PUT / PATCH route exists under `/audit/*`. Enforced
by `tests/architecture/test_audit_log_append_only.py`. Phase 8 makes this a
build-time check.

**Consequence.** Filesystem-level tamper-evidence is out of scope (the
MinIO buckets are mounted via Docker volumes). The application-layer
guarantee is sufficient for the portfolio claim; production hardening is
Phase 4 territory in the roadmap.

## D7. The "no SQL from agent code" claim is a fitness test, not documentation

**Decision.** AR-003 is enforced by
`tests/architecture/test_no_sql_from_agents.py`. The test greps
`apps/test-data-agent/app/` for forbidden SQL-driver imports (psycopg,
asyncpg, sqlalchemy, sqlmodel) AND for SQL-shaped string literals. It runs
in CI; any agent-side SQL fails the build.

**Consequence.** The "safe agent" claim survives refactoring without
human review. If a future contributor proposes "let's just use asyncpg here
for performance," the test catches it before merge.

---

## Worked example: a complete audit trail (rule-based planner)

Below is an annotated transcription of the audit events for a
`claim_denial_active_member` scenario run. The events live as one row each
in `s3://atdm-audit/runs/<run_id>.parquet`. The agent's UI at
`http://localhost:18001/ui/audit/<run_id>` renders them as a timeline.

```json
[
  {
    "event_id": "1a8c...",
    "timestamp": "2026-05-20T22:48:12.322309+00:00",
    "test_run_id": "01KS3J3H4D4AFCQD98SEPJCPBP",
    "invoker": "agent:atdm-dev",
    "action": "request_received",
    "inputs": {
      "request_id": "tdr_55590ce5c511",
      "scenario": "claim_denial_active_member",
      "constraints": {},
      "effective_constraints": {
        "member_status": "active",
        "provider_network": "out_of_network",
        "eligibility_status": "active",
        "eligibility_window": "current",
        "claim_status": "denied",
        "procedure_code": "00000",
        "diagnosis_code": "Z00.00",
        "denial_reason": "invalid_procedure_code"
      },
      "delivery": {
        "seed_target": true,
        "return_playwright_fixture": false,
        "return_pytest_fixture": false
      },
      "planner_mode": "rule"
    },
    "tools_called": [],
    "outputs": {},
    "status": "ok"
  },
  {
    "action": "plan_resolved",
    "outputs": {
      "scenario_id": "claim_denial_active_member",
      "steps": [
        {"generator": "generate_plan"},
        {"generator": "generate_provider"},
        {"generator": "generate_member"},
        {"generator": "generate_eligibility"},
        {"generator": "generate_claim"}
      ],
      "validators": [
        "relational.eligibility_status_matches_member",
        "relational.claim_references_existing_member",
        "domain.denial_requires_invalid_code",
        "temporal.eligibility_window_contains_claim"
      ]
    },
    "status": "ok"
  },
  {"action": "seed_started", "outputs": {"step_count": 5}, "status": "ok"},
  {
    "action": "validators_passed",
    "outputs": {
      "validators": [
        "relational.eligibility_status_matches_member",
        "relational.claim_references_existing_member",
        "domain.denial_requires_invalid_code",
        "temporal.eligibility_window_contains_claim"
      ]
    },
    "status": "ok"
  },
  {
    "action": "seed_completed",
    "outputs": {
      "records_created": [
        {"kind": "plan", "primary_key": "plan-01KS3J3H4D4AFCQD98SEPJCPBP"},
        {"kind": "provider", "primary_key": "prov-01KS3J3H4D4AFCQD98SEPJCPBP"},
        {"kind": "member", "primary_key": "m-01KS3J3H4D4AFCQD98SEPJCPBP"},
        {"kind": "eligibility", "primary_key": "elig-01KS3J3H4D4AFCQD98SEPJCPBP"},
        {"kind": "claim", "primary_key": "claim-01KS3J3H4D4AFCQD98SEPJCPBP"}
      ]
    },
    "status": "ok"
  },
  {
    "action": "catalog_recorded",
    "outputs": {"status": "ready"},
    "status": "ok"
  }
]
```

### What this proves

- **Source-grounded recommendation.** Every claim the agent makes ("here is
  data for `claim_denial_active_member`") is reconstructable from the
  trail: the constraints, the chosen generators, the chosen validators,
  the records inserted, and the cleanup contract.
- **Auditable AI output.** Even though MVP uses a rule-based planner, the
  event shape already carries `planner_mode`, `prompt` (null for rule),
  `tools_called` (empty for rule). When Phase 2 enables `ATDM_PLANNER=llm`,
  the same event shape gains LLM prompt + response without any consumer
  changes.
- **Evidence-backed analysis.** Reset works because every row in the SUT
  carries `test_run_id`; this audit trail is keyed on the same ID.

### Worked example: validator rejection (B2 acceptance)

When a constraint contradiction is fed in (member inactive + eligibility
active), the trail terminates with `plan_rejected` and **no DB writes occur**:

```json
[
  {"action": "request_received", "status": "ok", ...},
  {"action": "plan_resolved", "status": "ok", ...},
  {"action": "seed_started", "status": "ok", ...},
  {
    "action": "plan_rejected",
    "status": "rejected",
    "outputs": {
      "failed_validators": [
        {
          "validator": "relational.eligibility_status_matches_member",
          "message": "inactive member cannot have active eligibility",
          "details": {"member_status": "inactive", "eligibility_status": "active"}
        }
      ]
    }
  }
]
```

The HTTP response is 422 with `{error.code: "VALIDATOR_REJECTED"}`. No
records exist in any mutable table for this `test_run_id`. The catalog
records the run with `status: "rejected"`.

### Worked example: LLM planner (Phase 2 placeholder)

When `ATDM_PLANNER=llm` is enabled (currently 501-stubbed), the event shape
will gain a `prompt` field on `plan_resolved` and a `tools_called` list:

```json
{
  "action": "plan_resolved",
  "inputs": {
    "planner_mode": "llm",
    "prompt": "Generate a scenario for: 'active member with denied claim'",
    "model": "claude-opus-4-7",
    "model_version": "2026-05-20"
  },
  "outputs": {
    "scenario_id": "claim_denial_active_member",
    "tools_called": [
      {"tool": "list_scenarios", "args": {}, "result_size": 5},
      {"tool": "describe_scenario", "args": {"name": "claim_denial_active_member"}}
    ],
    "validator_decision": "accepted"
  },
  "status": "ok"
}
```

The `validators` step still runs (deterministically) before any seed
happens. The LLM cannot bypass the validator — that's the whole point of
the tool-bounded planner architecture.
