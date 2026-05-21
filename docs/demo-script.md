# Demo Script

The single-command demo for a reviewer to see what ATDM actually does.

## TL;DR

```bash
make setup     # one-time: pdm install (~5s on a warm cache)
make up        # one-time: bring the stack up (~18s p95)
make demo      # the demo proper (~3s on a warm stack)
```

The third command prints a clickable URL to the audit trail UI:

```
Open this URL in a browser to inspect the run as a reviewer would:
  http://localhost:18001/ui/audit/01KS3J3H4D4AFCQD98SEPJCPBP
```

## What `make demo` does, step by step

The Make target runs [`scripts/demo.sh`](../scripts/demo.sh), which prints
each phase as it runs. From a reviewer's terminal:

### 0. stack health

```
agent is up
```

The script pings `GET /health` until the agent answers 200. If `make up`
wasn't run beforehand, the wrapper Make rule runs it for you.

### 1. atdm request claim_denial_active_member

```
{
  "request_id": "tdr_7f4cca861c93",
  "test_run_id": "01KS3XYWYZ2JAMAKPY3VY5N225",
  "status": "ready",
  "data": {
    "plan_id": "plan-01KS3XYWYZ2JAMAKPY3VY5N225",
    "provider_id": "prov-01KS3XYWYZ2JAMAKPY3VY5N225",
    "member_id": "m-01KS3XYWYZ2JAMAKPY3VY5N225",
    "eligibility_id": "elig-01KS3XYWYZ2JAMAKPY3VY5N225",
    "claim_id": "claim-01KS3XYWYZ2JAMAKPY3VY5N225"
  },
  "fixtures": {
    "playwright": "/fixtures/claim_denial_active_member_01KS3XYWYZ2JAMAKPY3VY5N225.json",
    "pytest":     "/fixtures/claim_denial_active_member_01KS3XYWYZ2JAMAKPY3VY5N225.py"
  },
  "cleanup": {
    "cleanup_token": "<one-time-secret>",
    "endpoint": "/test-data/runs/01KS3XYWYZ2JAMAKPY3VY5N225/reset"
  }
}
```

What just happened:

- The agent resolved the named scenario from its YAML registry.
- The rule-based planner emitted an ordered list of generator calls.
- Deterministic generators produced records (Plan, Provider, Member,
  Eligibility, Claim) — all carrying the `test_run_id` and the `FAKE_` /
  `ZZ` markers from NFR-010.
- The validators ran (relational consistency, denial requires invalid code,
  temporal window). All passed.
- The bundle went to the Target SUT in **one Postgres transaction**.
- The audit trail and catalog were written to MinIO Parquet.
- Two fixture files were written to the host's `automation/fixtures/`.

### 2. pytest automation/pytest-api/test_example_claim_denial.py

```
test_claim_denial_fixture_is_well_formed PASSED
test_claim_denial_fixture_carries_cleanup_contract PASSED
```

What just happened:

- The pytest test loaded the just-emitted `.py` fixture module.
- It called `scenario_data()` and asserted on the returned dict.
- Two test functions, both green.

### 3. atdm reset <run_id>

```
{
  "deleted_counts": {
    "claim": 1, "eligibility": 1, "member": 1, "plan": 1, "provider": 1,
    "procedure_codes": 0, "diagnosis_codes": 0
  },
  "run_id": "01KS3XYWYZ2JAMAKPY3VY5N225",
  "status": "cleaned"
}
```

What just happened:

- The agent verified the `cleanup_token` against the sha256 stored in the catalog.
- The agent called the Target SUT's atomic bundle DELETE.
- Every row tagged with this `test_run_id` was removed in one transaction.
- The baseline reference rows (procedure_code / diagnosis_code with
  `test_run_id IS NULL`) were preserved.

### 4. atdm audit <run_id>

```
{
  "run_id": "01KS3XYWYZ2JAMAKPY3VY5N225",
  "scenario_id": "claim_denial_active_member",
  "reset_status": "cleaned",
  "events": [
    {"action": "request_received",  "status": "ok",      "timestamp": "..."},
    {"action": "plan_resolved",     "status": "ok",      "timestamp": "..."},
    {"action": "seed_started",      "status": "ok",      "timestamp": "..."},
    {"action": "validators_passed", "status": "ok",      "timestamp": "..."},
    {"action": "seed_completed",    "status": "ok",      "timestamp": "..."},
    {"action": "catalog_recorded",  "status": "ok",      "timestamp": "..."},
    {"action": "fixtures_emitted",  "status": "ok",      "timestamp": "..."},
    {"action": "reset_started",     "status": "ok",      "timestamp": "..."},
    {"action": "reset_completed",   "status": "cleaned", "timestamp": "..."}
  ]
}
```

What this proves:

- Every meaningful action is captured in the audit trail.
- The chronological order is preserved.
- The trail terminates with `reset_completed: cleaned` — the cleanup
  contract was honoured.

### 5. The HTML page

The demo finishes by printing:

```
Open this URL in a browser to inspect the run as a reviewer would:
  http://localhost:18001/ui/audit/01KS3XYWYZ2JAMAKPY3VY5N225
```

That page renders the same audit trail as a styled, clickable HTML view
(no JavaScript build). The full timeline, with expandable per-event details,
is in the screenshot at [docs/assets/audit-trail.png](assets/audit-trail.png).

## After the demo

Useful follow-up URLs:

| What | URL |
|---|---|
| Agent Swagger | `http://localhost:18001/docs` |
| SUT Swagger | `http://localhost:18000/docs` |
| MinIO console | `http://localhost:19001` (creds in `.env.example`) |
| Prometheus metrics | `http://localhost:18001/metrics` |
| Audit JSON | `http://localhost:18001/audit/runs/<run_id>` |
| Audit HTML | `http://localhost:18001/ui/audit/<run_id>` |

Tear down with `make down` (preserves volumes) or `make down-clean` (wipes
volumes — destructive).

## What the demo deliberately doesn't do

- **LLM planner.** `ATDM_PLANNER=llm` returns HTTP 501 in MVP. Phase 2
  enables it with prompt logging and reviewer UI. See
  [design-decisions.md](design-decisions.md#d1-rule-based-planner-is-the-default-llm-planner-is-phase-2).
- **MCP server.** Phase 2.
- **Real PHI / production data.** All data is synthetic. See `NFR-010`
  in [BRD §8](../requirements/BRD.md#8-non-functional-requirements).
- **Multi-tenant auth.** MVP uses a single shared `ATDM_API_TOKEN`. See
  README "Security model".

The demo's value isn't comprehensiveness — it's the **vertical slice that
proves the architecture**: tool-bounded planning, atomic seeding,
auditable invocation, reversible cleanup.
