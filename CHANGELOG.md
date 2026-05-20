# Changelog

All notable changes to this project are recorded here. Newest first.

## [Unreleased]

### Added — 2026-05-20 — Phase 2 Target SUT schema and Member entity

- `apps/target-healthcare-api/migrations/0001_init.sql` lands all seven entities from BRD §9 (`plan`, `provider`, `member`, `eligibility`, `claim`, `procedure_code`, `diagnosis_code`).
  - `test_run_id` discipline (DR-001) on every mutable table with an index.
  - Reference tables (`procedure_code`, `diagnosis_code`) allow `test_run_id` NULL for baseline rows shared across runs.
  - DB CHECK constraints enforce NFR-010 markers at the DDL layer: `member.first_name` / `last_name LIKE 'FAKE\_%'` and `member.address_state = 'ZZ'`.
  - FK constraints: Member → Plan, Eligibility → Member, Claim → Member / Provider / ProcedureCode / DiagnosisCode.
  - Baseline reference data seeded: 4 procedure codes (including one invalid for denial scenarios), 4 diagnosis codes (likewise).
- Migrations auto-apply via Postgres's `docker-entrypoint-initdb.d/` on fresh volume init. `make migrate` re-applies on demand to a running stack (idempotent via `CREATE TABLE IF NOT EXISTS` and `INSERT ... ON CONFLICT DO NOTHING`).
- `apps/target-healthcare-api/app/db/session.py` — asyncpg connection pool managed by FastAPI lifespan (`init_pool` on startup, `close_pool` on shutdown). `connection()` async context manager for repository use.
- `apps/target-healthcare-api/app/models/member.py` — Pydantic v2 `Member` and `Address` models with field validators enforcing NFR-010 markers in the application layer.
- `apps/target-healthcare-api/app/repositories/member.py` — single SQL surface for the Member table. `insert_member`, `delete_by_run_id`, `count_by_run_id`, `get_by_id`. Parameterized queries only.
- `apps/target-healthcare-api/app/routes/member.py` — internal routes `POST /internal/members` and `DELETE /internal/members?run_id=...`. Maps asyncpg-level errors to typed HTTP responses: unique violation → 409, FK violation → 422, CHECK violation → 422.
- Target SUT `main.py` wires the Member router and the asyncpg lifespan.
- Project deps: `asyncpg`, `asyncpg-stubs` (mypy strict needs them), `pytest-asyncio` (with `asyncio_mode = "auto"`). Mirrored into `apps/target-healthcare-api/requirements.txt`.
- 10 new integration tests under `tests/integration/test_member_repository.py`:
  - Schema sanity: all 7 tables present; baseline reference data seeded.
  - Happy path: insert → count=1 → delete → count=0.
  - `test_run_id` scoping: deleting run A leaves run B intact.
  - Pydantic validation: non-`FAKE_` first_name and non-`ZZ` state both return 422 before any DB round-trip.
  - DB CHECK enforcement: bypassing Pydantic via direct psql still fails with `check constraint`.
  - FK violation surfaces as 422 (not 500); duplicate PK surfaces as 409.
- `make migrate` Makefile target.

### Added — 2026-05-20 — Phase 1 local stack

- `infra/docker-compose.yml` defining 5 services:
  - `postgres:16` with healthcheck, named volume `atdm_postgres_data`, host port 55432.
  - `minio/minio:RELEASE.2025-04-22T22-12-26Z` with healthcheck, named volume `atdm_minio_data`, host ports 19000 (API) / 19001 (console).
  - `minio-buckets` — one-shot `minio/mc` init container that creates the three required buckets (`atdm-catalog`, `atdm-audit`, `atdm-fixtures`) and exits 0. Idempotent (`mc mb --ignore-existing`).
  - `target-healthcare-api` — `python:3.12-slim` FastAPI stub serving `GET /health`, host port 18000.
  - `test-data-agent` — `python:3.12-slim` FastAPI stub serving `GET /health` and `GET /metrics`, host port 18001.
- All four long-running services carry `deploy.resources.limits.memory: 512m` per NFR-017. Shared `atdm_pip_cache` volume so warm starts skip re-downloads.
- FastAPI app stubs at `apps/target-healthcare-api/app/main.py` and `apps/test-data-agent/app/main.py`.
- Per-app `requirements.txt` for container-side runtime deps.
- Project-level dev deps gain `fastapi` and `uvicorn[standard]` (pinned 0.115≤fastapi<0.120, 0.32≤uvicorn<0.40).
- Unit tests for both stubs using `fastapi.testclient.TestClient` — 6 tests, no Docker required.
- Integration / e2e suite at `tests/integration/test_stack_up.py` (6 tests including a warm-start-under-60s e2e check). Session-scoped `compose_stack` fixture auto-detects whether the stack is already up and skips tear-down when `ATDM_KEEP_STACK_UP=1`.
- `Makefile` gains `up`, `down`, `down-clean`, `logs`, `ps`, `test-unit`, `test-integration`, `build` targets wired to compose. `make test` stays Docker-free (unit only); `make test-integration` brings the stack up.
- `scripts/measure_cold_start.sh` — 5-run p95 benchmark for NFR-001 (60s cold-start budget). Measured locally: p95 = 18s. PASS with wide margin.
- `.github/workflows/ci.yml` gains a `stack` job that runs `make up && make test-integration && make down` on every push.
- `docs/development.md` — comprehensive developer guide (prerequisites, day-to-day workflow, port table, testing strategy, troubleshooting).
- README updated with end-user quickstart and current implementation status.
- Project ruff isort config: `known-first-party = ["app", "atdm"]` so the duplicate-`app` pitfall doesn't also break import order checks.

### Added — 2026-05-19 — Phase 0 scaffold

- `pyproject.toml` (pdm-managed) declaring Python 3.12 and dev deps: `ruff`, `mypy`, `pytest`, `pytest-cov`, `httpx`.
- `mypy.ini` with `strict = True` against the project source paths.
- `Makefile` with stub targets: `setup`, `lint`, `test`, `build`, `up`, `down`, `demo`, `smoke`, `baseline-snapshot`, `reset-baseline`, `clean`. Stack and demo targets are placeholders that exit non-zero with a "not yet implemented — Phase N" notice.
- Top-level directory skeleton per [planning/PLAN.md](planning/PLAN.md) Phase 0: `apps/test-data-agent/`, `apps/target-healthcare-api/`, `automation/`, `data/`, `docs/`, `infra/`, `tests/`.
- `__init__.py` placed in every Python package directory.
- `.gitkeep` placed in data / infra / asset directories.
- `LICENSE` — MIT, copyright Nick Baynham 2026 (per BRD §16 decision #8).
- `README.md` placeholder with status banner, CI badge, doc index, quickstart, security and data-ethics sections.
- `CHANGELOG.md`, `FEATURES.md`, `TODO.md` per project CLAUDE.md.
- `.env.example` with the env vars MVP will use; secrets stay out of git.
- `.gitignore` for Python / pdm / virtualenv / coverage / OS artifacts.
- `.github/workflows/ci.yml` running lint, test, and architecture jobs on push and PR.
- `tests/test_truth.py` — single trivial passing test confirming the test harness runs.

### Decisions baked in

- 2026-05-19: All 12 BRD §16 open questions resolved by accepting the analyst's recommendations. See [requirements/BRD.md §16](requirements/BRD.md#16-open-questions--resolved-2026-05-19) for the decision table.

### Lessons learned

- 2026-05-19 — **mypy duplicate-module trap.** The documented layout has two Python packages literally named `app` (one per `apps/` subproject). Running mypy against both in a single invocation triggers `Duplicate module named "app"` and aborts. Resolution: `mypy.ini` sets `explicit_package_bases = True` + `namespace_packages = True`, and `make lint` runs mypy in three separate passes (one per source root). Captured in [planning/PLAN.md Phase 0 "Known pitfall"](planning/PLAN.md) so future replays of Phase 0 avoid it.
- 2026-05-19 — **Default host ports collide with other local stacks.** A common dev laptop already runs Postgres on `5432` and MinIO on `9000`/`9001` for unrelated projects. Phase 1 would have failed `make up` with `bind: address already in use`. Resolution: shifted host ports to `55432` (Postgres), `19000`/`19001` (MinIO), `18000` (Target SUT), `18001` (ATDM agent). Container-internal ports are unchanged. Locked into [planning/PLAN.md Phase 1 host port mapping table](planning/PLAN.md#phase-1--docker-compose-postgres-minio-two-service-stubs); referenced from README Quickstart and `.env.example`.
- 2026-05-20 — **The duplicate-`app` mypy trap extends to pytest.** Phase 1's per-app FastAPI stubs both ship a `tests/test_main.py` that does `from app.main import app`. If `pyproject.toml`'s `testpaths` includes both apps, a single `pdm run pytest` invocation imports both `app` modules and the second one wins — silently testing against the wrong code or failing with `ImportError`. Resolution: `testpaths` lists only the top-level `tests`; the `Makefile test` target invokes pytest three times (once per source root) with `PYTHONPATH` set. Mirrors the existing mypy pattern. Documented in [PLAN.md Phase 0 Known pitfall](planning/PLAN.md), now extended with a pytest section.
- 2026-05-20 — **Ruff isort sorts `app.main` before `fastapi` unless told otherwise.** Ruff treats unknown top-level packages as third-party by default. Since `app` is first-party in this repo, ruff sorted `from app.main import app` before `from fastapi.testclient import TestClient`, which fails its own isort rule. Resolution: declare `known-first-party = ["app", "atdm"]` in `[tool.ruff.lint.isort]`. Trivial fix, would have eaten 10 minutes if discovered during commit instead of during the first `make lint` after adding the FastAPI stubs.
- 2026-05-20 — **Postgres `docker-entrypoint-initdb.d/` is a one-shot, not a migration tool.** When Phase 2 added a migration file and bind-mounted it into the existing (Phase 1) stack, `make up` brought everything healthy but zero tables existed — Postgres skips the entrypoint when the data directory is already initialized. Resolution: migrations are idempotent (`CREATE TABLE IF NOT EXISTS`, `INSERT ... ON CONFLICT DO NOTHING`); `make migrate` re-applies via `psql` against the live stack; `make down-clean && make up` is documented as the reset path. The three options are written into PLAN.md Phase 2 "Known pitfall" and `docs/development.md`.
- 2026-05-20 — **`asyncpg` has no type stubs.** Mypy `--strict` flags every import. Resolution: add `asyncpg-stubs` as a dev dep. Also note: `pool.acquire()` yields `PoolConnectionProxy[Any]`, not `Connection[Any]` — annotate accordingly.
- 2026-05-20 — **`pytest-asyncio` 0.26 forces `pytest < 9`.** Adding `pytest-asyncio` silently downgraded `pytest` from 9.0.3 to 8.4.2. Not a blocker for us, but worth knowing if you depend on pytest 9 features. Pin both explicitly if it matters.
