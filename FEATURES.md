# Features

Tracks the features that ship in the Agentic Test Data Manager (ATDM) MVP. A feature appears here only when it lands in `main` with passing CI. Phase numbers refer to [planning/PLAN.md](planning/PLAN.md).

## Shipped

### Phase 0 — repo scaffold (2026-05-19)

- pdm-managed Python 3.12 project.
- `ruff` linting and `mypy --strict` type checking, invoked per source root.
- `pytest` + `pytest-cov` test harness.
- `Makefile` with `setup`, `lint`, `test` targets.
- GitHub Actions CI: `lint`, `test`, `architecture` jobs.
- Directory skeleton for both apps, automation, infra, data, docs.
- MIT license.

### Phase 8 — Audit HTML page and architecture fitness tests (2026-05-20)

- `GET /ui/audit/{run_id}` — server-rendered HTML page with Pico.css. Reviewer can click through any run's trail in a browser. ~11 KB; 100 KB ceiling.
- 3 architecture fitness tests gate CI: AR-003 (no SQL from agent code), NFR-011 (audit append-only), NFR-012 (no emoji in committed text).
- Prometheus metrics on the audit writer: `atdm_audit_events_total{action,status}`, `atdm_audit_write_latency_seconds`, `atdm_audit_dropped_events_total` (must remain 0).
- `docs/design-decisions.md` records 7 architectural calls plus a worked-example audit record for both the rule-based and the (Phase 2) LLM-mode planners.

### Phase 7 — `atdm` CLI and `atdm.pytest` library (2026-05-20)

- Installable `atdm-client` package with PEP 561 `py.typed` marker.
- `atdm` console script with 8 subcommands and `--output (human|json)` flag.
- `@atdm_scenario(...)` decorator + `atdm_data` fixture; auto-loads via pytest11 entry point.
- `AtdmClient` sync HTTP wrapper for direct Python use.
- New agent endpoint `GET /catalog/scenarios` (FR-041).
- Example pytest + Playwright tests under `automation/`.
- `make playwright-install` / `make playwright-test` targets.
- 16 atdm-client unit tests + 5 Phase 7 integration tests.

### Phase 6 — Fixture delivery (2026-05-20)

- `POST /test-data/requests` writes a Playwright JSON fixture and/or an importable pytest Python module to `ATDM_FIXTURE_DIR/<scenario>_<run_id>.{json,py}` when the delivery flags are set.
- Host sees emitted fixtures under `automation/fixtures/` via the docker compose bind-mount.
- pytest module exposes `SCENARIO_ID`, `TEST_RUN_ID`, `scenario_data() -> dict`. Importable from any test runner.
- New `fixtures_emitted` audit event records what was written.

### Phase 5 — Full reset strategy surface (2026-05-20)

- All five reset strategies demoable from the agent's HTTP API: `reset_run`, `reset_all`, `baseline_snapshot`, `baseline_restore`, and `idempotent_seed` (property of restore).
- Server-side snapshot/restore via PyArrow + MinIO Parquet objects, schema-agnostic.
- `reset_all` gated by `X-Confirm: yes` header to prevent demo accidents.
- Idempotent restore (NFR-016): second invocation yields identical state.
- Strategy invocations get their own audit trail under synthetic `strategy-{name}-{ULID}` run IDs.
- 8 new integration tests covering C2 / C3 / C4 acceptance + X-Confirm gate.

### Phase 4 — Broadened generators, validators, and scenarios (2026-05-20)

- Five entities live on the Target SUT (Provider, Eligibility, Claim, ProcedureCode, DiagnosisCode) with Pydantic models, transaction-aware repos, and atomic bundle endpoints.
- Five scenarios fulfill end-to-end: `active_member_clean`, `claim_denial_active_member`, `expired_eligibility`, `out_of_network_pending_claim`, `inactive_member_with_history`.
- Four cross-entity validators reject contradictory bundles before any DB write (B2 acceptance).
- Atomic single-transaction bundle insert + FK-safe atomic bundle delete (FR-014).
- 91% combined line coverage on generators/, validators/, seeders/ (every module ≥80%, Phase 4 exit criterion).

### Phase 3 — First end-to-end vertical slice (2026-05-20)

- `POST /test-data/requests` returns scenario-grounded synthetic test data, seeds the Target SUT, records the catalog and audit trail, and returns a `cleanup_token`.
- `POST /test-data/runs/{run_id}/reset` cleans up by `test_run_id` via Target SUT. Token-verified (sha256), idempotent, FK-safe deletion order.
- `GET /audit/runs/{run_id}` returns the chronological audit trail with `x-audit-source` header.
- Rule-based planner, scenario YAML registry, deterministic seedable generators (Member + Plan).
- Saga compensation: any seeder failure rolls back inserted entities by `test_run_id` in reverse order.
- Catalog and audit log persisted as Parquet objects in MinIO.
- Bearer-token middleware on all mutating endpoints.
- `ATDM_PLANNER=llm` 501 stub.
- One scenario shipped: `active_member_clean`.

### Phase 2 — Target SUT schema and Member entity (2026-05-20)

- Seven-entity Postgres schema landed via Postgres `docker-entrypoint-initdb.d/`. Idempotent — re-applies cleanly via `make migrate`.
- `test_run_id` discipline on every mutable table; reference tables permit NULL for baseline rows.
- NFR-010 markers enforced **twice** (Pydantic + DB CHECK): non-`FAKE_` names and non-`ZZ` states fail at the application boundary AND at the DDL layer.
- Member CRUD via internal routes (`POST` / `DELETE /internal/members?run_id=`). Single-SQL-surface repository pattern; asyncpg pool managed by FastAPI lifespan.
- Typed error mapping: unique-violation → 409, FK-violation → 422, CHECK-violation → 422.
- 10 new integration tests across schema sanity, happy path, scoping, validation, and edge cases.

### Phase 1 — local stack (2026-05-20)

- `docker compose up` brings up Postgres 16, MinIO, the Target SUT FastAPI stub, and the ATDM agent FastAPI stub. All long-running services healthy within 18s (p95 over 5 runs) — well under the 60s NFR-001 budget.
- One-shot `minio-buckets` init container creates the three required buckets (`atdm-catalog`, `atdm-audit`, `atdm-fixtures`) idempotently.
- Target SUT serves `GET /health`. ATDM agent serves `GET /health` and `GET /metrics` (Prometheus text).
- Non-default host port mapping (55432, 19000/19001, 18000, 18001) so the stack doesn't collide with other local services.
- 512MB memory limit per long-running service (NFR-017).
- Unit tests per app (TestClient, no Docker), integration tests against the live stack, e2e warm-start budget test, cold-start benchmark script.
- GitHub Actions `stack` job runs the integration suite on every push.
- Comprehensive developer guide at `docs/development.md`.

## Planned by phase

See [planning/PLAN.md](planning/PLAN.md) for the full phase breakdown. Summary:

- **Phase 9.** `make demo`, README final, design-decisions doc.
- **Phase 10.** Hardening, asciinema cast, project-wide Definition of Done complete.
