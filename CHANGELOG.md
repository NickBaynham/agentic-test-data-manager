# Changelog

All notable changes to this project are recorded here. Newest first.

## [Unreleased]

### Added — 2026-05-20 — Phase 7 `atdm` CLI and `atdm.pytest` library

- New installable package `atdm-client` under `apps/test-data-agent/python/` with its own `pyproject.toml`. Installs via `pip install -e ./apps/test-data-agent/python` or as a path dep via pdm.
- **`atdm` CLI** (Typer-based) with 8 subcommands: `request`, `reset`, `reset-all`, `baseline-snapshot`, `baseline-restore`, `baseline-list`, `audit`, `scenarios`. Global `--output (human|json)` flag. Reads `ATDM_API_URL` / `ATDM_API_TOKEN` from env. Non-zero exit on any API error with `HTTP {status}` + JSON-formatted error body on stderr.
- **`atdm.pytest` plugin** — auto-loads via the `pytest11` entry point. Exports `atdm_scenario(name, constraints={...})` decorator (a thin `pytest.mark.atdm_scenario(...)` wrapper) and the `atdm_data` fixture that seeds before the test and resets after.
- **`AtdmClient`** sync HTTP wrapper at `atdm.client.AtdmClient`. Methods: `request_scenario`, `reset_run`, `reset_all`, `baseline_snapshot`, `baseline_restore`, `baseline_list`, `get_audit`, `get_scenarios`. Raises `AtdmClientError` with status code + body on any 4xx/5xx.
- **New agent endpoint `GET /catalog/scenarios`** (FR-041) returning all loaded scenario definitions including `linked_requirement_ids` (FR-044). Powers `atdm scenarios`.
- **PEP 561 `py.typed` marker** included in the wheel so downstream mypy sees `atdm`'s type hints.
- **Example tests**:
  - `automation/pytest-api/test_example_member.py` — three flows: decorator + fixture, decorator with constraint overrides, direct client usage.
  - `automation/playwright/` — minimal Playwright TypeScript setup (`package.json`, `playwright.config.ts`, `tests/member.spec.ts`) consuming a JSON fixture via `FIXTURE_PATH` env var.
- **Makefile targets** `playwright-install` and `playwright-test`. The `test-unit` target gains a fourth invocation for the `atdm-client` package's own tests.
- **Tests** (all green):
  - 13 CLI unit tests via Typer's `CliRunner` with mocked `AtdmClient`.
  - 3 pytest plugin tests via `pytester` — verify the marker + fixture seed/reset cycle against an in-memory mock client. **D3 acceptance** covered at unit level.
  - 5 new integration tests against the live stack (CLI smoke, `@atdm_scenario` decorator end-to-end + DB verification).

### Added — 2026-05-20 — Phase 6 fixture delivery

- `apps/test-data-agent/app/fixtures/playwright.py` writes a JSON fixture per scenario request to `ATDM_FIXTURE_DIR/<scenario>_<run_id>.json`. Shape: `{scenario_id, test_run_id, data, cleanup}`.
- `apps/test-data-agent/app/fixtures/pytest_module.py` writes an importable Python module per scenario request to `ATDM_FIXTURE_DIR/<scenario>_<run_id>.py`. Exposes `SCENARIO_ID`, `TEST_RUN_ID`, and `scenario_data() -> dict`.
- `POST /test-data/requests` honors `delivery.return_playwright_fixture` / `delivery.return_pytest_fixture`. The response's `fixtures` block carries absolute paths (or `null`). New audit event `fixtures_emitted` records what was written.
- `infra/docker-compose.yml`: bind-mount `../automation/fixtures` → `/fixtures` on the agent; `ATDM_FIXTURE_DIR=/fixtures`. Host sees written fixtures under `automation/fixtures/`.
- pytest module embeds the payload via `repr()` on the dict (not as embedded JSON in a triple-quoted string) so backslashes and quotes round-trip cleanly.
- 6 new unit tests for the writers + 4 new integration tests covering D1/D2 acceptance and the audit event.

### Added — 2026-05-20 — Phase 5 full reset strategy surface

All five reset strategies live and demoable from the agent's HTTP API. The
SUT does the data work (it owns the schema and the rows); the agent
orchestrates and writes audit events.

- **Target SUT — server-side reset machinery**:
  - `POST /internal/reset/all-tagged` — single Postgres transaction that DELETEs `WHERE test_run_id IS NOT NULL` from every mutable + reference table. Baseline reference rows (NULL) preserved.
  - `POST /internal/baseline/snapshot?baseline_id=...` — writes each of the 7 tables to Parquet at `s3://atdm-catalog/baselines/{baseline_id}/<table>.parquet` plus a self-describing `manifest.json` (table list, row counts, captured_at, schema_version).
  - `POST /internal/baseline/restore?baseline_id=...` — `TRUNCATE ... CASCADE` then re-insert from Parquet in FK order. Server-side transaction guarantees atomicity. Idempotent (NFR-016).
  - `GET /internal/baseline/list` — every known baseline, newest first.
- **ATDM agent — strategy endpoints**:
  - `POST /test-data/reset/all` — requires `X-Confirm: yes` header (428 without). Wraps SUT reset-all-tagged + audit trail.
  - `POST /test-data/baseline/snapshot` — generates a baseline_id if not supplied; emits `snapshot_started`/`snapshot_completed` audit events.
  - `POST /test-data/baseline/restore` — accepts optional baseline_id; defaults to latest. Emits `restore_started`/`restore_completed`.
  - `GET /test-data/baseline/list` — read-only, no auth.
- **`idempotent_seed`** is the property that re-invoking `baseline_restore` twice in a row yields identical state. Verified by integration test, not a separate endpoint.
- **`apps/target-healthcare-api/app/reset/`** module: `strategies.py` declares FK insert order and the mutable/reference table lists; `snapshotter.py` implements snapshot/restore as schema-agnostic Parquet round-trip (no hard-coded column lists — works for any column added in Phase 6+).
- **Schema-agnostic Parquet round-trip**: snapshot dumps `SELECT *` per table; restore inserts back via dynamic parameterized SQL constructed from the Parquet column names. Generic SQL is acceptable inside the SUT (AR-003 forbids it in the agent only).
- **Synthetic audit run IDs** for strategy invocations: `strategy-{name}-{ULID}` so they have their own audit trail visible via `GET /audit/runs/{audit_run_id}`.
- Deps: `pyarrow` and `minio` added to Target SUT runtime (already in agent).
- **8 new integration tests** in `tests/integration/test_phase5_resets.py`:
  - X-Confirm gate (without / wrong value → 428)
  - C3: `reset_all` clears tagged-only, preserves baseline reference rows
  - C2: snapshot → pollute → restore yields exact captured state (deterministic SHA-256 row hash)
  - C4: `baseline_restore` is idempotent — twice yields identical state
  - Unknown baseline_id → 404
  - `baseline_list` returns array
  - `reset_all` emits `reset_started` + `reset_completed` audit events

### Added — 2026-05-20 — Phase 4 broadened generators, validators, and scenarios

Phase 4 widens the Phase 3 vertical slice from one scenario to five, fills in
all seven entity types, and wires up four cross-entity validators that fail
fast before any DB write.

- **Five entities added to Target SUT** — Provider, Eligibility, Claim, ProcedureCode, DiagnosisCode. Pydantic models (mirrors of DB CHECKs), repositories (single SQL surface, parameterized queries only), all transaction-aware via the new `DbConn` type alias.
- **Atomic bundle endpoints** — `POST /internal/scenarios/seed` accepts a `ScenarioBundle` and inserts everything in one Postgres transaction. `DELETE /internal/scenarios?run_id=...` deletes all 7 tables in FK-safe reverse order in one transaction. Saga compensation removed from the agent — server-side transactions handle atomicity.
- **Five new ATDM generators** — `generate_provider`, `generate_eligibility`, `generate_claim`, `generate_procedure_code`, `generate_diagnosis_code`. All pure, seedable from `test_run_id`. Parent IDs derived deterministically via `{kind}-{run_id}` convention so generators are self-contained.
- **Four validators** under `apps/test-data-agent/app/validators/` with a registry mapping dotted names to callables:
  - `relational.eligibility_status_matches_member`
  - `relational.claim_references_existing_member`
  - `domain.denial_requires_invalid_code`
  - `temporal.eligibility_window_contains_claim`
- **Four new scenarios** (`claim_denial_active_member`, `expired_eligibility`, `out_of_network_pending_claim`, `inactive_member_with_history`) plus an updated `active_member_clean`. Scenario YAML schema gains `default_constraints` — caller's `constraints` merge on top.
- **Refactored seeder** — generate → validate → POST bundle. `ValidatorRejected` raised on validator failure (no bundle posted). `SeedError` raised on server failure.
- **New audit events** — `validators_passed`, `plan_rejected`. The latter carries the failed validator name and message in the audit trail.
- **`POST /test-data/requests` returns 422 + `plan_rejected`** when any validator fails (BRD B2 acceptance). Catalog records the run with status `rejected`.
- Tests:
  - 8 new integration tests in `test_phase4_scenarios.py` covering all 5 scenarios + B2 validator rejection + full bundle clear.
  - 13 new unit tests for generators, 17 for validators, 8 for seeder (47 unit tests total). **Coverage on generators/, validators/, seeders/ combined: 91%** (every module ≥80% — Phase 4 exit criterion met).
- **Phase 3 test fixtures updated** — `_force_cleanup` in `test_request_lifecycle.py` now uses the bundle DELETE instead of per-entity DELETEs (Phase 4's scenarios produce children that FK-reference Member/Plan; the old helper would fail).

### Added — 2026-05-20 — Phase 3 first end-to-end vertical slice

The headline `POST /test-data/requests` endpoint is live for the
`active_member_clean` scenario. Full request → plan → seed → audit → reset
lifecycle works end-to-end against the local stack.

- **Scenario YAML registry.** `apps/test-data-agent/app/scenarios/` loaded at agent startup via the lifespan. Each YAML carries `scenario_id`, ordered `generators`, optional `validators`, `linked_requirement_ids` (FR-044 — Coverage Intelligence linkage from MVP).
- **Rule-based planner.** `apps/test-data-agent/app/agents/planner.py` — no LLM, fully deterministic. Translates `{scenario_id, constraints}` into an ordered `Plan(steps=[(generator, args), ...])`.
- **Deterministic generators.** `apps/test-data-agent/app/generators/{plan,member}.py` — pure functions, seedable from `test_run_id`. Names drawn from a fixed `FAKE_` pool (NFR-010). Address state always `ZZ`.
- **Seeder with saga compensation.** `apps/test-data-agent/app/seeders/healthcare.py` — `execute_plan` calls Target SUT internal routes in order. On any failure, deletes by `run_id` in reverse order. `reset_run` deletes Member then Plan (FK-safe order).
- **Catalog and audit (MinIO + Parquet).** One Parquet object per run under `s3://atdm-catalog/runs/{run_id}.parquet` (catalog) and `s3://atdm-audit/runs/{run_id}.parquet` (audit). Cleanup tokens stored as sha256 only (DR-007). Append-only at API layer (NFR-011).
- **API: `POST /test-data/requests`.** Orchestrates the full vertical slice. Emits 5 audit events in order: `request_received`, `plan_resolved`, `seed_started`, `seed_completed`, `catalog_recorded`. Returns the FR-005 contract shape with `request_id`, `test_run_id`, `data`, `cleanup`.
- **API: `POST /test-data/runs/{run_id}/reset`.** Verifies cleanup_token against stored sha256, deletes via Target SUT, updates catalog status. Idempotent — second call returns `already_cleaned`. Wrong token returns 403. Unknown run returns 404.
- **API: `GET /audit/runs/{run_id}`.** Returns full audit trail as JSON with `x-audit-source` header pointing at the source Parquet object.
- **API token middleware.** Bearer token required on all mutating endpoints (POST/PUT/PATCH/DELETE). `/health` and `/metrics` always pass through.
- **`ATDM_PLANNER=llm` 501 stub** (BRD §16 decision #2) — returns `LLM_MODE_NOT_ENABLED`. Tested via unit test, not integration (env override + container restart proved too fragile mid-suite).
- **Target SUT: Plan entity.** Mirror of Member: Pydantic model, repository, internal `POST /internal/plans` and `DELETE /internal/plans?run_id=` routes. Phase 3 prerequisite — Member.plan_id is a FK, so a Plan must exist before a Member can be inserted.
- **Deps added** (project + ATDM agent requirements.txt): `python-ulid`, `pyarrow`, `minio`, `pyyaml`, `types-PyYAML`.
- **Tests** (all green):
  - 11 new integration tests under `tests/integration/test_request_lifecycle.py` covering happy path, reset with correct token, idempotent reset, wrong-token 403, unknown-run 404, audit event ordering, audit JSON contract, `x-audit-source` header, auth required (401), unknown scenario (404), health bypass.
  - 6 new unit tests under `apps/test-data-agent/tests/test_planner_modes.py` covering LLM mode 501, auth (no token / wrong token), health/metrics bypass, unknown scenario.

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
- 2026-05-20 — **"Member only" in PLAN.md Phase 3 actually requires Plan too.** The PLAN.md said Phase 3 builds the Member generator/seeder/route only, deferring the other six entities to Phase 4. But Member.plan_id is a FK to Plan in the Phase 2 schema, so any Member insert needs a Plan to exist first. Resolution: added a minimal Plan repo + internal route in Phase 3 (mirror of Member, 30 lines each). Backfilled into PLAN.md Phase 3 "Known prerequisite". For Phase 4, the lesson: when sequencing entity work, sequence by FK dependency order, not by alphabetical or arbitrary order.
- 2026-05-20 — **`pyarrow` ships no type stubs.** mypy `--strict` rejects it. Resolution: add `[mypy-pyarrow.*] ignore_missing_imports = True` in `mypy.ini`. Note: this section is "unused" in mypy passes that don't touch pyarrow (target-healthcare-api, tests/) — mypy emits a harmless warning. Acceptable noise; no fix needed.
- 2026-05-20 — **Restarting a docker compose service mid-integration-test corrupts subsequent tests.** I tried to test `ATDM_PLANNER=llm` mode by restarting the agent container with an env override during an integration test. The restart left the stack in a transitional state and the next-running test (`test_all_services_healthy`) caught the agent as `starting` and failed. Resolution: moved that test to a unit test using `TestClient` + `monkeypatch.setenv`. **General rule for integration tests: never restart compose services mid-suite.** If you need a different config, exercise it in a unit test or in a separate top-level integration job.
- 2026-05-20 — **Per-entity `_force_cleanup` helpers break when a phase adds new entities.** Phase 3 tests' helper did `DELETE FROM member; DELETE FROM plan`. Phase 4 added Eligibility and Claim, both FK-referencing Member, so the old helper failed with a constraint violation. Resolution: switch every test's cleanup to the atomic bundle DELETE (`DELETE /internal/scenarios?run_id=...`) which handles FK order centrally. **General rule**: cleanup helpers should call the most atomic DELETE the API exposes, not enumerate tables — adding a new entity to a phase shouldn't require touching every prior phase's tests.
- 2026-05-20 — **PoolConnectionProxy vs Connection — type alias is the clean fix.** Adding transaction-aware repositories (Phase 4) re-surfaced the asyncpg "Pool.acquire() yields PoolConnectionProxy, not Connection" issue from Phase 2. Six repos all needed the same union type. Resolution: a single `type DbConn = asyncpg.Connection[Any] | asyncpg.pool.PoolConnectionProxy[Any]` alias in `app/db/session.py`. Use the modern `type` keyword over `TypeAlias` — ruff prefers it.
- 2026-05-20 — **A single `_pk(record)` helper that scans for `*_id` keys silently returns the wrong key.** When the Member record carries both `member_id` (PK) and `plan_id` (FK), iterating keys and returning the first match yields the FK. Subtle bug that smoke-tested fine but broke `data.member_id` in the response. Resolution: always pass the entity kind explicitly. **General rule**: helpers that scan over a fixed list of keys should never silently pick a "winner" — make the lookup explicit.
- 2026-05-20 — **Embedding JSON inside a Python triple-quoted string breaks on backslashes.** Phase 6's pytest module first embedded `json.dumps(payload)` between `"""..."""`. JSON containing `\\Users\\fake` (Windows path) became `\Users\fake` after Python's string parsing — invalid JSON. Resolution: embed the dict via `repr()`. Python's `repr()` on built-in types (str/int/float/bool/None/list/dict) round-trips cleanly through normal module loading. **General rule**: when emitting Python source code that needs to embed runtime data, use `repr()` to produce a literal — never concatenate JSON into a string literal.
- 2026-05-20 — **Typer chokes on `Any` in command signatures.** Phase 7's CLI initially wrapped every command with a `@_handle` decorator that exposed `(*args: Any, **kwargs: Any)` to Typer. Typer inspects the function signature to build Click options and rejects `Any` as a parameter type. Resolution: inline the error handling in each command instead of decorating, OR use `functools.wraps` plus careful signature preservation. The inline form is simpler and avoids a second source of bugs. **General rule**: Typer / Click only sees the signature of the function it decorates — if you wrap, you also have to preserve the signature exactly.
- 2026-05-20 — **Typer global options must precede the subcommand.** `atdm request scenario -o json` fails with "No such option '-o'" because `--output` is on the root callback, not on `request`. Correct form: `atdm -o json request scenario`. **General rule**: global CLI options live on the callback and bind at parse time before the subcommand resolves; this is consistent with Click conventions but worth knowing for tests and docs.
- 2026-05-20 — **The duplicate-package mypy trap extends a third time to `tests/`.** When Phase 7 added `apps/test-data-agent/python/tests/`, mypy refused because `apps/test-data-agent/tests/` already declared a package called `tests`. Resolution: same as the original `app` trap from Phase 0 — add a fourth mypy invocation in the Makefile for the new source root. The `test-data-agent` mypy call now explicitly lists `apps/test-data-agent/app apps/test-data-agent/tests` so it doesn't sweep `python/`. **General rule**: every new package root under an existing `apps/<name>/` subtree needs its own mypy invocation.
- 2026-05-20 — **`pytest.request.addfinalizer` runs BEFORE yield-based fixture teardowns.** I tried to verify "the decorator's teardown emits a `reset_completed` audit event" by registering a finalizer inside the test body. The finalizer ran first (LIFO from the test's perspective), then the `atdm_data` fixture's teardown ran, so the audit trail was inspected pre-reset. Resolution: cover the property at the unit level (pytester with a mock client) instead of fighting fixture-ordering at the integration level. **General rule**: cross-fixture verification needs a session-scoped tracker, not a test-scoped finalizer.
