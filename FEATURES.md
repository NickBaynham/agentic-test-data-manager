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

- **Phase 3.** First end-to-end slice: `active_member_clean` request → seed → audit → reset.
- **Phase 4.** All 7 entities, all 5 scenarios, validator-gated atomic seeding.
- **Phase 5.** All five reset strategies (`reset_run`, `reset_all`, `baseline_snapshot`, `baseline_restore`, `idempotent_seed`).
- **Phase 6.** Playwright JSON + pytest module fixture emitters.
- **Phase 7.** `atdm` CLI and `atdm.pytest` library.
- **Phase 8.** Audit HTML page + AR-003 architecture fitness test in CI.
- **Phase 9.** `make demo`, README final, design-decisions doc.
- **Phase 10.** Hardening, asciinema cast, project-wide Definition of Done complete.
