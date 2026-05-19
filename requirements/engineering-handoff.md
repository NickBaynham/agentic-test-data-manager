# Engineering Handoff: Agentic Test Data Manager (ATDM)

> **Document type:** Implementation Handoff — engineering-ready breakdown
> **Reads with:** [BRD.md](./BRD.md), [concept.md](./concept.md)
> **Audience:** the engineer or coding agent who will scaffold ATDM v0.1
> **Date:** 2026-05-19

This document converts the BRD into work that can be pasted into Jira / GitHub Issues / a coding-agent prompt without an analyst-to-engineer translation pass. Every story maps to one or more FR/NFR/DR/AR/IR IDs from the BRD. Every test traces back to a requirement.

Five epics, one MVP, no Phase 2.

---

## Epic A — Local stack and developer experience

**One-line scope:** A `docker compose up` brings up Postgres, MinIO, Target SUT, and ATDM agent; `make demo` runs the end-to-end flow.

### Stories

**A1.** *As Alex, I want a one-command stack startup, so that the demo is reproducible on any reviewer's laptop.*
Maps to: FR-070, FR-071, NFR-001, NFR-013, NFR-015.

**A2.** *As Alex, I want a single `make demo` command, so that a reviewer can see the full intent-to-data → seed → test → reset → audit loop without reading the code.*
Maps to: FR-072.

**A3.** *As the maintainer, I want `make setup`, `make lint`, `make test`, `make build`, `make up`, `make down`, so that the project follows the CLAUDE.md convention.*
Maps to: FR-070, FR-073, NFR-007.

### Acceptance criteria

```
A1
Given a clean Docker state on a 16 GB reference laptop
When  the developer runs `make up`
Then  all 4 services report healthy within 60 seconds (p95 over 5 runs)
And   `docker compose ps` shows postgres, minio, target-healthcare-api, test-data-agent all healthy
```

```
A2
Given `make up` has completed
When  the developer runs `make demo`
Then  the command exits 0 within 90 seconds
And   stdout shows, in order: scenario request → seed confirmation → playwright test PASSED → reset confirmation → audit log summary
And   after demo completes, `atdm catalog runs` lists exactly one new run
And   no orphan rows remain in the Target SUT for that run
```

```
A3
Given a fresh clone
When  the developer runs `make setup && make lint && make test`
Then  setup completes via `pdm install` only (no manual pip/poetry/conda steps)
And   lint reports zero errors under ruff
And   mypy --strict reports zero errors (per-file ignores explicitly justified)
And   tests pass with ≥ 80 % line coverage on apps/test-data-agent/app/{generators,validators,seeders,reset}
```

### Suggested data model changes

None for this epic. Stack-only.

### Suggested backend services

- `infra/docker-compose.yml` — Postgres 16, MinIO latest, ATDM agent, Target SUT. Pinned by digest. Per NFR-017, each service carries `deploy.resources.limits.memory: 512m`.
- `infra/postgres/init.sql` — schema bootstrap for Target SUT.
- `infra/minio/buckets.sh` — creates `atdm-catalog`, `atdm-audit`, `atdm-fixtures` buckets at startup.

### Suggested UI components

- None.

### Suggested test cases

- Happy: `tests/integration/test_stack_up.py::test_all_services_healthy_within_60s`
- Failure: `tests/integration/test_stack_up.py::test_minio_unreachable_returns_503` (kill MinIO, request scenario, expect 503).
- Regression: `tests/integration/test_stack_up.py::test_demo_make_target_exits_zero`.

### Observability requirements

- `atdm_up_seconds` histogram emitted on agent startup recording time-to-ready.
- Structured JSON logs from each container, prefixed with `service=`.

### Security considerations

- Compose file does not commit secrets. `ATDM_API_TOKEN` and `MINIO_ROOT_PASSWORD` come from `.env.local` (gitignored) with `.env.example` checked in.
- No host network mode; explicit `ports:` only for what reviewers must reach.

### Definition of Done (Epic A)

- [ ] `make demo` passes in CI on a Linux runner.
- [ ] README "Quickstart" section verified by a fresh clone test.
- [ ] `.env.example` checked in; `.env.local` gitignored.
- [ ] CHANGELOG entry, FEATURES entry, TODO updated.

---

## Epic B — Generator / validator / seeder core

**One-line scope:** Deterministic, seedable generation of 7 healthcare entities with relational integrity, validator-gated, written via repository methods only.

### Stories

**B1.** *As Alex, I want to request scenario data and have it written into the Target SUT, so that downstream tests can simply use it.*
Maps to: FR-001, FR-005, FR-010, FR-011, FR-012, FR-014, FR-015, FR-016, DR-001, DR-004.

**B2.** *As Quinn (reviewer), I want every agent-initiated write to pass through a validator before it touches the database, so that the safety claim is credible.*
Maps to: AR-003, FR-004, FR-012.

**B3.** *As Alex, I want generators to be seedable from `test_run_id`, so that re-running the same scenario produces the same data values and tests are stable.*
Maps to: FR-010.

**B4.** *As Alex, I want a failed scenario to leave zero rows behind, so that I never debug an orphan record.*
Maps to: FR-014.

### Acceptance criteria

```
B1
Given a registered scenario "claim_denial_active_member"
When  POST /test-data/requests is invoked with valid constraints
Then  the response includes data.member_id, data.provider_id, data.claim_id
And   SELECT count(*) FROM member  WHERE test_run_id = <run_id> = 1
And   SELECT count(*) FROM claim   WHERE test_run_id = <run_id> = 1
And   the claim row's status = 'denied' and member_id matches data.member_id
```

```
B2
Given a constraints object that violates a registered validator
      (e.g. member_status="inactive" AND eligibility_status="active")
When  POST /test-data/requests is invoked
Then  the response is HTTP 422
And   the response body names the failing validator
And   no rows are written to ANY Target SUT table
And   the audit log records action="plan_rejected"
```

```
B3
Given a scenario request with constraints C and assigned test_run_id=R
When  the request is fulfilled
And   a separate request with the same constraints C and forced test_run_id=R is fulfilled
      in a clean Target SUT
Then  the generated record values for non-PK columns are identical
```

```
B4
Given a scenario whose third generator step is patched to raise RuntimeError
When  POST /test-data/requests is invoked
Then  the response is HTTP 500 with a body containing the failed step name
And   SELECT count(*) FROM member, plan, provider, eligibility, claim
      WHERE test_run_id = <run_id> = 0 across all tables
And   the audit log records action="seed_failed" status="rolled_back"
```

### Suggested API endpoints

```
POST /test-data/requests
  purpose: fulfill a scenario request end-to-end (plan → validate → generate → seed → fixtures → catalog → audit)
  request: { domain, scenario, constraints, delivery }
  response: { request_id, test_run_id, status, data, fixtures, cleanup }
  auth:    Bearer ATDM_API_TOKEN
  errors:  400 (schema), 401 (no token), 422 (validator), 500 (seed failure), 502 (SUT), 503 (deps down)
```

### Suggested data model changes

Target SUT tables (`member`, `plan`, `provider`, `eligibility`, `claim`):

- Add column `test_run_id TEXT NOT NULL` to every mutable table.
- Add index `idx_<table>_test_run_id` on each.
- For `procedure_code` and `diagnosis_code`: `test_run_id TEXT NULL` (reference rows shared across runs; invalid-test variants are per-run).
- DB-level CHECK: `member.first_name LIKE 'FAKE\_%'` (enforces NFR-010 at DDL layer).

Initial migration: `apps/target-healthcare-api/migrations/0001_init.sql`.

### Suggested backend services

- `apps/test-data-agent/app/scenarios/` — YAML scenario registry loaded at startup; one file per scenario. Every YAML file shall declare `linked_requirement_ids: list[str]` (FR-044); empty list is permitted in MVP. The field is surfaced unchanged in `GET /catalog/scenarios` responses.
- `apps/test-data-agent/app/generators/{member,plan,provider,eligibility,claim,codes}.py` — pure functions; signature `(seed: int, constraints: Constraints) -> dict`.
- `apps/test-data-agent/app/validators/{relational,domain,temporal}.py` — pure functions; signature `(plan: Plan) -> ValidationResult`.
- `apps/test-data-agent/app/seeders/healthcare.py` — orchestrates calls to Target SUT repositories; single transaction wrapper.
- `apps/target-healthcare-api/app/repositories/` — only place that issues SQL. Hard architectural rule.

### Suggested UI components

None (Epic E owns the audit HTML page).

### Suggested test cases

- Happy: `test_request_claim_denial_seeds_correctly` (B1).
- Validator: `test_inactive_member_active_eligibility_rejected` (B2).
- Determinism: `test_same_run_id_produces_identical_values` (B3).
- Atomicity: `test_seed_failure_leaves_zero_rows` (B4).
- Permission: `test_request_without_token_returns_401`.
- Architecture fitness: `tests/architecture/test_no_sql_from_agents.py` — greps `apps/test-data-agent/app/` for forbidden imports (`psycopg`, `asyncpg`, `sqlalchemy.engine`, `sqlmodel.Session.exec`) and fails CI on any match.

### Observability requirements

- `atdm_requests_total{scenario, status}` counter.
- `atdm_request_latency_seconds{scenario}` histogram.
- `atdm_seed_records_total{table}` counter.
- `atdm_validator_rejections_total{validator}` counter.
- Structured log line per request: `{ event, request_id, test_run_id, scenario, status, duration_ms }`.

### Security considerations

- Bearer token required on `POST /test-data/requests`. 401 on missing/invalid.
- Schema validation runs **before** any DB connection is opened.
- All Target SUT writes use parameterized queries via repository methods. No string-formatted SQL anywhere in the agent module.
- AR-003 architectural fitness test runs in CI.

### Definition of Done (Epic B)

- [ ] All four acceptance blocks pass in CI.
- [ ] Architecture fitness test passes.
- [ ] ≥ 80 % line coverage on `generators/`, `validators/`, `seeders/`.
- [ ] CHANGELOG entry, FEATURES entry.
- [ ] One scenario worked example in `docs/design-decisions.md`.

---

## Epic C — Reset and cleanup

**One-line scope:** Five reset strategies — `reset_all`, `reset_run`, `snapshot_restore`, `idempotent_seed`, `cleanup_token` — each demoable from API and CLI.

### Stories

**C1.** *As Alex, I want each test run to clean up by token, so that parallel test runs don't trample each other.*
Maps to: FR-030, FR-035, FR-034, DR-007.

**C2.** *As CI, I want to restore a known baseline before a suite, so that suite runs are independent.*
Maps to: FR-031, FR-033, FR-034.

**C3.** *As Alex, I want a heavy-handed `reset_all` for when things go wrong during a demo, so that I can get back to a clean state in one command.*
Maps to: FR-032, FR-034.

**C4.** *As Alex, I want to re-run the same seed without producing duplicates, so that the system is idempotent.*
Maps to: FR-034 (`idempotent_seed`).

### Acceptance criteria

```
C1
Given a fulfilled scenario request with test_run_id=R, cleanup_token=T
When  POST /test-data/runs/R/reset with body { cleanup_token: T }
Then  HTTP 200, status="cleaned"
And   no rows with test_run_id=R remain in any mutable table
And   a second identical POST returns HTTP 200 status="already_cleaned"
And   POST with body { cleanup_token: "wrong" } returns HTTP 403, no DB change
```

```
C2 (per NFR-016 — logically-equivalent state, sequences NOT reset)
Given a baseline snapshot B0 captured via POST /test-data/baseline/snapshot
And   arbitrary subsequent scenario requests
When  POST /test-data/baseline/restore
Then  HTTP 200
And   for every mutable table T: multiset(SELECT <non_pk_cols> FROM T) == same multiset in B0
And   auto-increment sequence values are NOT required to equal baseline values
And   a second POST /test-data/baseline/restore yields the same logically-equivalent state
```

```
C3
Given any state with N run-tagged rows
When  POST /test-data/reset/all
Then  HTTP 200
And   SELECT count(*) WHERE test_run_id IS NOT NULL = 0 across all mutable tables
And   shared reference rows (procedure_code, diagnosis_code with test_run_id IS NULL) are unaffected
```

```
C4
Given the baseline seed script
When  POST /test-data/baseline/restore is invoked twice in succession
Then  the second invocation completes in HTTP 200 with no errors
And   row counts and hashes are identical to the first post-restore state
```

### Suggested API endpoints

```
POST /test-data/runs/{run_id}/reset
  request: { cleanup_token }
  response: { status: "cleaned" | "already_cleaned" }
  errors:  401, 403 (token mismatch), 404 (unknown run_id)

POST /test-data/baseline/snapshot
  request: {}
  response: { baseline_id, captured_at, table_row_counts: {...} }
  errors:  401, 500

POST /test-data/baseline/restore
  request: { baseline_id (optional, defaults to latest) }
  response: { restored_at, table_row_counts: {...} }
  errors:  401, 404 (no baseline), 500

POST /test-data/reset/all
  request: {}
  response: { cleared_run_count, cleared_record_count }
  errors:  401, 500
```

### Suggested data model changes

- New ATDM-side table (or Parquet file in MinIO): `baseline_snapshots` with `baseline_id`, `captured_at`, `table_row_counts`, `snapshot_path`.
- Baseline data itself stored as Parquet under `s3://atdm-catalog/baselines/{baseline_id}/<table>.parquet`.

### Suggested backend services

- `apps/test-data-agent/app/reset/strategies.py` — one function per strategy.
- `apps/test-data-agent/app/reset/snapshotter.py` — capture/restore via Parquet round-trip.

### Suggested test cases

- C1 happy: `test_reset_run_clears_only_tagged_rows`.
- C1 idempotency: `test_reset_run_second_call_returns_already_cleaned`.
- C1 security: `test_reset_run_with_wrong_token_returns_403_and_no_delete`.
- C2: `test_baseline_restore_round_trip_hash_match`.
- C2 idempotency: `test_baseline_restore_twice_identical`.
- C3: `test_reset_all_clears_run_tagged_only`.
- C4: `test_idempotent_seed_no_duplicates`.

### Observability requirements

- `atdm_resets_total{strategy, status}` counter.
- `atdm_reset_latency_seconds{strategy}` histogram.
- Log line per reset including `strategy`, `run_id` (if applicable), `cleared_record_count`.

### Security considerations

- Cleanup tokens logged only as SHA-256 hash (DR-007).
- `POST /test-data/reset/all` requires the API token; consider an additional `X-Confirm: yes` header to discourage accidental invocation (Should-have).
- Baseline snapshots stored unencrypted (local MinIO); not in scope for MVP.

### Definition of Done (Epic C)

- [ ] All four acceptance blocks pass in CI.
- [ ] Cleanup-token-hash logging verified by inspecting an audit record.
- [ ] CLI `atdm reset`, `atdm baseline-snapshot`, `atdm baseline-restore` wired and tested.
- [ ] Demo flow (Epic A) exercises at least `reset_run` end-to-end.

---

## Epic D — Catalog and fixture delivery

**One-line scope:** DuckDB-over-Parquet-in-MinIO catalog; Playwright JSON and pytest Python fixtures written to disk; Python fixture library for direct pytest use.

### Stories

**D1.** *As Alex, I want a Playwright JSON fixture written to disk for every scenario request, so that my test can `import` it without an extra round trip.*
Maps to: FR-020, FR-022, FR-023.

**D2.** *As Alex, I want a pytest Python fixture module for the same scenario, so that my pytest tests can `import` it.*
Maps to: FR-021, FR-022, FR-023.

**D3.** *As Alex, I want a Python library `atdm.pytest` exposing an `atdm_scenario` fixture decorator, so that I don't write boilerplate HTTP calls in every test.*
Maps to: FR-024.

**D4.** *As Quinn, I want `GET /catalog/scenarios` and `GET /catalog/runs`, so that I can browse what's available and what's been requested.*
Maps to: FR-040, FR-041, FR-042.

### Acceptance criteria

```
D1
Given a scenario request with delivery.return_playwright_fixture=true
When  the request is fulfilled
Then  a file exists at ATDM_FIXTURE_DIR/<scenario>_<test_run_id>.json
And   the file is valid JSON and contains keys: scenario_id, test_run_id, data, cleanup
And   the response body's fixtures.playwright matches that path
```

```
D2
Given a scenario request with delivery.return_pytest_fixture=true
When  the request is fulfilled
Then  a file exists at ATDM_FIXTURE_DIR/<scenario>_<test_run_id>.py
And   `python -c "import importlib.util; ..."` can import the module
And   the module exposes a callable `scenario_data()` returning the dict
```

```
D3
Given a pytest test annotated with @atdm_scenario("claim_denial_active_member")
When  the test runs
Then  the test receives a `scenario` fixture with .data, .test_run_id, .cleanup
And   after the test, the fixture's teardown calls /test-data/runs/{run_id}/reset
And   the audit log shows status="cleaned" for that run
```

```
D4
Given any number of past runs in the catalog
When  GET /catalog/runs?scenario=claim_denial_active_member is called
Then  HTTP 200 with a JSON array of runs in descending test_run_id order
And   each run includes test_run_id, scenario_id, created_at, status
```

### Suggested API endpoints

```
GET /catalog/scenarios
  response: [ { scenario_id, name, description, constraints_schema, tags[] } ]

GET /catalog/runs?scenario=...&since=...&limit=...
  response: [ { test_run_id, scenario_id, status, created_at } ]
```

### Suggested data model changes

- MinIO buckets `atdm-catalog` (Parquet: `runs.parquet`, partitioned by `dt=...`) and `atdm-fixtures` (raw JSON/PY files).
- Scenario YAML registry under `apps/test-data-agent/app/scenarios/*.yaml`.

### Suggested backend services

- `apps/test-data-agent/app/catalog/parquet_store.py` — append-on-write Parquet via DuckDB or PyArrow.
- `apps/test-data-agent/app/fixtures/playwright.py` — emits JSON.
- `apps/test-data-agent/app/fixtures/pytest_module.py` — emits Python module.
- `apps/test-data-agent/python/atdm/pytest.py` — installable client library with the `@atdm_scenario` decorator.

### Suggested test cases

- D1: `test_playwright_fixture_written_and_valid_json`.
- D2: `test_pytest_fixture_module_importable_and_returns_data`.
- D3: `test_atdm_scenario_decorator_auto_cleans_up`.
- D4: `test_catalog_runs_endpoint_sorts_descending`.

### Observability requirements

- `atdm_fixtures_emitted_total{kind}` counter (kind = `playwright` | `pytest`).
- `atdm_catalog_writes_total` counter.

### Security considerations

- Fixture files contain only the data needed by tests. Cleanup tokens are written to fixture files (so tests can clean up) — but the fixture directory must not be exposed over HTTP. Document that `ATDM_FIXTURE_DIR` is for local use only.
- `GET /catalog/*` endpoints are read-only and open on the local network (per NFR-004); no auth.

### Definition of Done (Epic D)

- [ ] All four acceptance blocks pass.
- [ ] `pip install -e ./apps/test-data-agent/python` works and exposes `atdm.pytest`.
- [ ] One Playwright test and one pytest test in `automation/` consume the respective fixtures and pass against the live demo stack.
- [ ] CHANGELOG, FEATURES updated.

---

## Epic E — Audit log and reviewer trail (the differentiator)

**One-line scope:** Append-only Parquet audit log; JSON endpoint; single HTML page that makes the agent-safety story click-through-able.

> **Strategic note (Product Strategy Mode):** This is the highest-leverage epic. Reviewers will spend more time on the audit trail than on the generator. Invest the time.

### Stories

**E1.** *As the ATDM agent, I want to append an audit record for every meaningful action, so that the run is reconstructable from the log.*
Maps to: FR-050, FR-051, NFR-011, DR-005.

**E2.** *As Quinn, I want `GET /audit/runs/{run_id}`, so that I can see the full trail of one run as JSON.*
Maps to: FR-052.

**E3.** *As Quinn, I want `GET /ui/audit/{run_id}`, so that I can read the trail in a browser without writing curl.*
Maps to: FR-053.

**E4.** *As Alex, I want `atdm audit {run_id}`, so that I can dump the trail to my terminal.*
Maps to: FR-060.

### Acceptance criteria

```
E1
Given a scenario request from start to finish (request → plan → validate → seed → fixtures → catalog)
When  the request completes (success or failure)
Then  at minimum these audit events exist for that test_run_id:
      action="request_received"
      action="plan_resolved"  with planner_mode in {"rule","llm"}
      action="validators_passed" or "plan_rejected"
      action="seed_started", action="seed_completed" or "seed_failed"
      action="fixtures_emitted"
      action="catalog_recorded"
And   every event has: event_id, timestamp, test_run_id, invoker, action, inputs, tools_called, outputs, status
And   no event is mutable after write (no API surface permits update/delete)
```

```
E2
Given a known test_run_id with completed events
When  GET /audit/runs/{run_id} is called
Then  HTTP 200 with body
      { run_id, scenario_id, invoker, planner_mode, prompt (nullable),
        plan, validator_decisions[], records_created[],
        fixtures_emitted[], reset_status, started_at, finished_at, duration_ms,
        events[] }
And   events[] is in chronological order
And   the response includes a header X-Audit-Source pointing to the Parquet file path
```

```
E3
Given the same test_run_id
When  GET /ui/audit/{run_id} is opened in a browser
Then  the page renders without JavaScript build steps (server-rendered HTML)
And   the page shows: a banner with run_id and invoker; a plan section; a validators section
      (each pass/fail clearly marked); a records-created table; a fixtures list with file links;
      a reset-status badge; a timeline of events with timestamps
And   the page weighs ≤ 100 KB
```

```
E4
Given the same test_run_id
When  `atdm audit <run_id>` is run from the shell
Then  exit code 0
And   stdout contains a human-readable summary (default) or JSON (with --output json)
```

### Suggested API endpoints

```
GET /audit/runs/{run_id}
  response: see E2
  errors:  404 (unknown run)

GET /ui/audit/{run_id}
  response: text/html, server-rendered
  errors:  404
```

### Suggested data model changes

- MinIO bucket `atdm-audit`, Parquet partitioned `dt=YYYY-MM-DD/`.
- Schema: `event_id, timestamp, test_run_id, invoker, action, inputs (json), tools_called (json), outputs (json), status, reviewer_decision (nullable json), schema_version`.

### Suggested backend services

- `apps/test-data-agent/app/audit/writer.py` — append-only Parquet writer with daily rollover.
- `apps/test-data-agent/app/audit/query.py` — DuckDB query of audit Parquet.
- `apps/test-data-agent/app/audit/ui.py` — Jinja-rendered HTML page.

### Suggested UI components

- One template: `templates/audit_run.html`. Pico.css via CDN (or hand-rolled CSS — see open question 7). States: success, failure, partial (some events missing), unknown run (404 page).

### Suggested test cases

- E1: `test_audit_events_emitted_in_order_for_happy_path`.
- E1: `test_audit_events_for_validator_rejection_include_plan_rejected`.
- E1: `test_audit_events_for_seed_failure_include_rolled_back_status`.
- E1: `test_audit_log_is_append_only_no_mutation_api`.
- E2: `test_audit_runs_endpoint_returns_full_trail`.
- E3: `test_audit_ui_renders_for_known_run`.
- E3: `test_audit_ui_returns_404_for_unknown_run`.
- E4: `test_atdm_audit_cli_default_and_json_output`.

### Observability requirements

- `atdm_audit_events_total{action, status}` counter.
- `atdm_audit_write_latency_seconds` histogram.
- Self-monitoring: a counter `atdm_audit_dropped_events_total` that **must remain 0**. If non-zero in CI, the build fails.

### Security considerations

- No PII in audit records (since data itself is synthetic, this is mostly automatic).
- Cleanup tokens stored as `sha256:<hex>` only.
- LLM prompts (Phase 2) logged in full at MVP scale; redaction policy deferred.
- Audit endpoints are read-only and unauthenticated on the local network per NFR-004; this is acceptable for MVP because no real data is involved. **Document this explicitly in the README "Security model" section** so a reviewer understands the boundary.

### Definition of Done (Epic E)

- [ ] All four acceptance blocks pass in CI.
- [ ] One screenshot of `/ui/audit/{run_id}` committed under `docs/assets/audit-trail.png`.
- [ ] README "What this proves" section links to that screenshot.
- [ ] `docs/design-decisions.md` includes one worked-example audit record for the rule-based path (and a placeholder for the LLM path, marked Phase 2).

---

## Cross-cutting requirements

These do not belong to a single epic but must hold across all of them.

### Logging contract

Every HTTP request emits exactly one structured log line at completion:

```
{"ts":"...","event":"http_request","request_id":"...","test_run_id":"... or null",
 "method":"POST","path":"/test-data/requests","status":200,"latency_ms":347,"invoker":"agent:..."}
```

### Error response contract

```
{ "error": { "code": "VALIDATOR_REJECTED",
             "message": "Member is inactive but eligibility is active.",
             "details": { "validator": "relational.eligibility_status_matches_member",
                          "constraint_a": "member_status=inactive",
                          "constraint_b": "eligibility_status=active" } } }
```

All 4xx and 5xx responses use this shape. Tests assert against `error.code`, not the human message.

### Versioning

- Catalog Parquet `schema_version=1`.
- Audit Parquet `schema_version=1`.
- API URLs are unversioned in MVP; if a breaking change is needed before Phase 2 ships, prefix with `/v1/`. Document this in `docs/design-decisions.md`.

### CI

GitHub Actions matrix:

- Lint job: `make lint`.
- Test job: `make up && make test && make down`.
- Architecture-fitness job: `tests/architecture/*`.
- Demo smoke job: `make demo` against a fresh stack.

A PR cannot merge if any job fails. Fitness test for AR-003 is gating.

### Documentation contract

Every merged change updates at least one of: `CHANGELOG.md`, `FEATURES.md`, `TODO.md`. The PR template enforces this.

---

## Definition of Done (project-wide MVP)

The project is "MVP done" when **all** the following are true:

- [ ] All five reset strategies demonstrable from CLI and API (Epic C).
- [ ] All seven entities generated, validated, seeded, and reset correctly (Epic B).
- [ ] `make demo` runs the full intent → seed → test → reset → audit flow in ≤ 90 s (Epic A, A2).
- [ ] Architecture fitness test (AR-003: no agent SQL) is enforced in CI.
- [ ] `GET /ui/audit/{run_id}` renders for a real run and screenshot is in `docs/assets/` (Epic E).
- [ ] `atdm` CLI exposes `request`, `reset`, `baseline-snapshot`, `baseline-restore`, `audit`, `catalog`.
- [ ] Playwright JSON fixture and pytest Python fixture both written to disk and consumable (Epic D).
- [ ] `atdm.pytest` library is `pdm`-installable and exercised by at least one example test.
- [ ] README ≤ 400 lines, opens with portfolio bullets, includes architecture diagram, demo steps.
- [ ] `docs/architecture.md`, `docs/demo-script.md`, `docs/design-decisions.md`, `docs/healthcare-domain-model.md`, `docs/recruiter-summary.md` exist and are current.
- [ ] CHANGELOG, FEATURES, TODO maintained.
- [ ] Ruff + mypy --strict clean. Coverage ≥ 80 % on core modules.
- [ ] CI green on `main`.
- [ ] No PHI; all NFR-010 markers (`FAKE_`, `ZZ`) present in generated data and verified by test.
- [ ] LLM mode is **off** by default and clearly marked Phase 2 in README and Makefile.

---

## Implementation sequence (suggested)

A small-step, validated-as-you-go order. Each step ends in something running and tested.

1. **Repo scaffold** — `pdm init`, Makefile skeleton, ruff/mypy config, GitHub Actions skeleton. *Verify:* `make setup && make lint` passes on an empty project.
2. **Docker Compose stack** — Postgres + MinIO + Target SUT stub + ATDM agent stub. *Verify:* `make up` → all 4 healthy.
3. **Target SUT schema + repositories** — 7 tables with `test_run_id` columns; repository methods only. *Verify:* unit tests on each repo.
4. **One generator + one validator + one seeder** — Member only. *Verify:* `POST /test-data/requests` with `scenario="active_member_clean"` writes a row.
5. **Reset by run_id + cleanup token** — *Verify:* C1 acceptance block.
6. **Audit log append + JSON endpoint** — *Verify:* E1, E2 acceptance blocks.
7. **Remaining 6 entities** plus their validators. *Verify:* B1 acceptance block on `claim_denial_active_member`.
8. **Baseline snapshot + restore + reset_all** — *Verify:* C2, C3, C4 acceptance blocks.
9. **Playwright + pytest fixture emitters** — *Verify:* D1, D2 acceptance blocks.
10. **`atdm` CLI** with all subcommands. *Verify:* shell smoke tests.
11. **`atdm.pytest` library** with `@atdm_scenario` decorator. *Verify:* D3 acceptance block.
12. **HTML audit page** — *Verify:* E3 acceptance block; commit screenshot.
13. **Architecture fitness test** — *Verify:* AR-003 enforced.
14. **README + docs** — *Verify:* fresh-clone reviewer can run `make demo` from the README alone.
15. **CI green on `main`** — *Verify:* badge in README.

Steps 1–6 alone deliver a working subset that proves the architecture; steps 7–13 deliver the demoable headline; steps 14–15 deliver the portfolio.
