# Features

Tracks the features that ship in the Agentic Test Data Manager (ATDM) MVP. A feature appears here only when it lands in `main` with passing CI. Phase numbers refer to [planning/PLAN.md](planning/PLAN.md).

## Shipped

_None yet — Phase 0 only scaffolds the repo._

## In Phase 0 (scaffold)

- pdm-managed Python 3.12 project.
- `ruff` linting and `mypy --strict` type checking.
- `pytest` + `pytest-cov` test harness.
- `Makefile` with `setup`, `lint`, `test` targets working end-to-end on a trivial test.
- GitHub Actions CI: lint job, test job, architecture job.
- Directory skeleton for the test-data-agent app, target-healthcare-api app, automation, infra, data, and docs.
- MIT license.

## Planned by phase

See [planning/PLAN.md](planning/PLAN.md) for the full phase breakdown. Summary:

- **Phase 1.** Docker Compose stack: Postgres, MinIO, Target SUT stub, ATDM agent stub.
- **Phase 2.** Target SUT schema (7 entities, `test_run_id` discipline); Member repository.
- **Phase 3.** First end-to-end slice: `active_member_clean` request → seed → audit → reset.
- **Phase 4.** All 7 entities, all 5 scenarios, validator-gated atomic seeding.
- **Phase 5.** All five reset strategies (`reset_run`, `reset_all`, `baseline_snapshot`, `baseline_restore`, `idempotent_seed`).
- **Phase 6.** Playwright JSON + pytest module fixture emitters.
- **Phase 7.** `atdm` CLI and `atdm.pytest` library.
- **Phase 8.** Audit HTML page + AR-003 architecture fitness test in CI.
- **Phase 9.** `make demo`, README final, design-decisions doc.
- **Phase 10.** Hardening, asciinema cast, project-wide Definition of Done complete.
