# MVP Build Plan: Agentic Test Data Manager (ATDM)

> **Document type:** Implementation plan
> **Scope:** ATDM v0.1 — Intent-to-Data, Synthetic Healthcare (the MVP defined in [BRD §17](../requirements/BRD.md))
> **Reads with:** [requirements/BRD.md](../requirements/BRD.md), [requirements/engineering-handoff.md](../requirements/engineering-handoff.md), [requirements/concept.md](../requirements/concept.md)
> **Date:** 2026-05-19
> **Style:** Small, validated increments. Every phase ends in something that runs and is tested. No big-bang merges.

---

## How to read this plan

The plan is organized as **10 phases**. Each phase has:

- A **Goal** — one sentence on what becomes true at the end.
- **Inputs** — what must already exist.
- **Work items** — concrete tasks the engineer or coding agent will do.
- **Exit criteria** — observable conditions that close the phase. Never proceed without these.
- **Verification commands** — the exact commands a reviewer runs to confirm the phase is done.
- **Maps to** — the BRD and engineering-handoff IDs the phase satisfies.

Phases are sequenced so that each one delivers a thin vertical slice. The first end-to-end happy path is reached at **Phase 3** (Member-only). Full MVP is reached at **Phase 9**. Phase 10 is hardening and demo polish.

Code is **not** scaffolded ahead of need. A module appears in the repo only when the phase that exercises it lands.

---

## Phase 0 — Repo scaffold and CI skeleton

**Goal.** A repo that lints, types-checks, and tests an empty package on `main`, with a CI badge.

**Inputs.** `requirements/` already in repo. Empty repo otherwise.

**Work items.**

- `pdm init`. Set Python 3.12.
- Add dev dependencies: `ruff`, `mypy`, `pytest`, `pytest-cov`, `httpx`.
- Create the directory skeleton from [BRD §17](../requirements/BRD.md) and [concept.md "Project modules"](../requirements/concept.md):
  ```
  apps/test-data-agent/app/{api,agents,generators,validators,seeders,catalog,reset,audit,fixtures,scenarios}
  apps/test-data-agent/python/atdm/
  apps/test-data-agent/tests/
  apps/target-healthcare-api/app/{models,routes,db,repositories}
  apps/target-healthcare-api/migrations/
  apps/target-healthcare-api/tests/
  automation/{playwright,pytest-api,fixtures}
  data/{seed,parquet,catalogs}
  docs/
  infra/{postgres,minio}
  tests/architecture/
  ```
- Add `Makefile` with stub targets: `setup`, `up`, `down`, `lint`, `test`, `build`, `demo`, `reset-baseline`, `baseline-snapshot`, `smoke`. The `lint` target must invoke mypy **once per source root** — see "Known pitfall" below.
- Add `pyproject.toml` ruff config (line-length 100, target py312).
- Add `mypy.ini` with the following non-negotiable settings to avoid the duplicate-`app/` trap (see "Known pitfall"):
  ```ini
  [mypy]
  python_version = 3.12
  strict = True
  explicit_package_bases = True
  namespace_packages = True
  ```
  Do **not** set a single `files = ...` directive that lists both `apps/test-data-agent/app` and `apps/target-healthcare-api/app` together — mypy will reject it.
- Add `.env.example` with `ATDM_API_TOKEN`, `ATDM_API_URL`, `MINIO_*`, `POSTGRES_*`, `ATDM_FIXTURE_DIR`, `ATDM_PLANNER=rule`.
- Add `.github/workflows/ci.yml`: lint, test, architecture jobs.
- Add `CHANGELOG.md`, `FEATURES.md`, `TODO.md` (per CLAUDE.md).
- Add a top-level `README.md` placeholder with a "Status: in development" banner and links to `requirements/`.

**Known pitfall — two `app/` packages collide under mypy.**

The documented structure has two Python packages literally named `app` — one under `apps/test-data-agent/app/` and one under `apps/target-healthcare-api/app/`. Both also carry `__init__.py`. Mypy treats them as duplicate top-level modules and aborts with:

```
error: Duplicate module named "app" (also at "<other_path>/app/__init__.py")
```

This is the same problem mypy describes at <https://mypy.readthedocs.io/en/stable/running_mypy.html#mapping-file-paths-to-modules>. It is **not** solvable by adjusting `MYPYPATH` alone, because both packages still resolve to the same top-level module name `app`.

The accepted resolution — bake this in during Phase 0, don't discover it during lint:

1. In `mypy.ini`, set `explicit_package_bases = True` and `namespace_packages = True`.
2. Do **not** declare a `files = ...` list that includes both `app/` directories in one mypy invocation.
3. In the `Makefile` `lint` target, invoke mypy in **three separate calls**, one per source root, so each invocation only sees one `app/`:
   ```make
   lint:
   	$(PDM) run ruff check .
   	$(PDM) run ruff format --check .
   	$(PDM) run mypy --config-file mypy.ini apps/test-data-agent
   	$(PDM) run mypy --config-file mypy.ini apps/target-healthcare-api
   	$(PDM) run mypy --config-file mypy.ini tests
   ```
4. Mirror the same three-pass invocation in the CI `lint` job — calling `make lint` is sufficient.

The same pattern protects the project from a future third `app/` (e.g., if Phase 3 adds an e-commerce SUT under `apps/target-ecommerce-api/app/`): add one more `mypy ...` line to the `lint` target. Do **not** be tempted to rename the inner packages to avoid the trap — the `app/` convention is referenced consistently across [BRD](../requirements/BRD.md), [engineering-handoff](../requirements/engineering-handoff.md), and [concept.md](../requirements/concept.md), and renaming would cascade through several documents.

If a future contributor proposes consolidating mypy into one call: this is the reason that proposal will fail. Point them at this section.

**The pitfall extends to pytest (discovered in Phase 1).** The same duplicate-module problem hits pytest as soon as both apps have a `tests/` directory that imports `from app.main import app`. If `pyproject.toml` declares both `apps/test-data-agent/tests` and `apps/target-healthcare-api/tests` in `testpaths`, a single `pdm run pytest` invocation tries to import both `app` packages and one wins — tests then pass against the wrong code, or fail with `ImportError`.

Resolution — bake this into Phase 1, don't discover it during test:

1. In `pyproject.toml`, `[tool.pytest.ini_options].testpaths` lists **only** `tests` (the top-level root tests). Per-app tests are explicitly NOT discovered by default.
2. The `Makefile` `test` target invokes pytest three times — once for the root `tests/`, once per app — each time with `PYTHONPATH` pointing at exactly one app's source root:
   ```make
   test: test-unit

   test-unit:
   	$(PDM) run pytest tests -m "not integration and not e2e"
   	PYTHONPATH=apps/target-healthcare-api $(PDM) run pytest apps/target-healthcare-api/tests
   	PYTHONPATH=apps/test-data-agent $(PDM) run pytest apps/test-data-agent/tests
   ```
3. Integration / e2e tests that exercise the running stack live under the top-level `tests/integration/` and are tagged `@pytest.mark.integration` / `@pytest.mark.e2e`. They are NOT part of `make test` (which stays Docker-free). They run via `make test-integration`.
4. Ruff `isort` must declare `app` and `atdm` as known-first-party so it sorts the `from app.main import app` import after third-party (`fastapi`):
   ```toml
   [tool.ruff.lint.isort]
   known-first-party = ["app", "atdm"]
   ```
   Without this, ruff fails the import order check.

The pattern generalizes: any tooling that imports / discovers Python modules and processes both apps in one call will hit the trap. Always invoke per source root with isolated PYTHONPATH/MYPYPATH.

**Exit criteria.**

- `make setup` works on a fresh clone (only Docker + pdm prerequisites).
- `make lint` passes on the empty package (ruff + mypy clean).
- `make test` passes on a single trivial test (`def test_truth(): assert True`).
- CI is green on `main` and a green badge is in `README.md`.

**Verification.**

```
git clean -fdx && make setup && make lint && make test
```

**Maps to:** FR-070, FR-073, NFR-007, NFR-014, NFR-015, [Handoff Epic A — A3].

---

## Phase 1 — Docker Compose: Postgres, MinIO, two service stubs

> **STATUS: COMPLETE — 2026-05-20.** All exit criteria met. 5-run cold-start benchmark: p95 = 18s (NFR-001 budget 60s). Unit + integration + e2e tests green. See [CHANGELOG.md "Added — 2026-05-20"](../CHANGELOG.md) for the full deliverable list.

**Goal.** `make up` brings up Postgres, MinIO, a Target-SUT stub, and an ATDM-agent stub. All four are healthy within 60 seconds.

**Inputs.** Phase 0 complete.

**Host port mapping (canonical).** This project uses non-default host ports to avoid collisions with other local stacks (one developer machine commonly runs Postgres on 5432 and MinIO on 9000/9001 for unrelated projects). Container-internal ports remain conventional; only the host side is remapped. Treat this table as **stable** — changing it later cascades through `.env.example`, READMEs, demo scripts, and asciinema cast.

| Service | Container port | **Host port** | Reason for shift |
|---|---|---|---|
| Postgres | 5432 | **55432** | Avoid `5432` collisions. |
| MinIO API | 9000 | **19000** | Avoid `9000` collisions. |
| MinIO Console | 9001 | **19001** | Avoid `9001` collisions. |
| Target SUT (FastAPI) | 8000 | **18000** | Symmetry with MinIO shift (1xxxx). |
| ATDM agent (FastAPI) | 8001 | **18001** | Symmetry with Target SUT. |

Inside the compose network, services address each other by service name + container port (e.g., `postgres:5432`, `minio:9000`, `target-healthcare-api:8000`). The host port mapping only affects connections from the developer's laptop (CLI, pytest from host, browser).

**Work items.**

- Add `infra/docker-compose.yml` with services:
  - `postgres:16` with healthcheck, named volume `atdm_postgres_data`, host port mapping `55432:5432`.
  - `minio/minio:RELEASE.2025-04-22T22-12-26Z` (pinned by tag) with healthcheck, named volume `atdm_minio_data`, host port mappings `19000:9000` (API) and `19001:9001` (console).
  - `minio-buckets` — one-shot `minio/mc` init container that creates `atdm-catalog`, `atdm-audit`, `atdm-fixtures` and exits 0.
  - `target-healthcare-api` — `python:3.12-slim` with bind-mounted source from `apps/target-healthcare-api/`, running `uvicorn`, exposing host port `18000:8000`. Serves `GET /health`.
  - `test-data-agent` — `python:3.12-slim` with bind-mounted source from `apps/test-data-agent/`, running `uvicorn`, exposing host port `18001:8001`. Serves `GET /health` and `GET /metrics`.
- Per NFR-017, each long-running service carries `deploy.resources.limits.memory: 512m` (postgres, minio, target-healthcare-api, test-data-agent). The one-shot `minio-buckets` container is exempt.
- Pin images by tag (not `latest`) for Postgres and MinIO. Pin by digest in a Phase 10 follow-up.
- No host network mode. Only the five ports above are published.
- `Makefile` `up` and `down` invoke `docker compose -f infra/docker-compose.yml`.
- Update `.env.example` host-side URLs to use the remapped ports (`localhost:18000`, `localhost:18001`, `localhost:55432`, `localhost:19000`).
- Note in README "Quickstart" that the stack uses non-default host ports and reference the table above.

**Exit criteria.**

- `make up` reports all four long-running services `healthy` within 60 seconds (p95 over 5 runs). The one-shot `minio-buckets` container reports `Exited (0)`.
- `curl http://localhost:18000/health` and `curl http://localhost:18001/health` return 200.
- `make down` cleanly removes containers (volumes preserved).
- Smoke test `tests/integration/test_stack_up.py::test_all_services_healthy_within_60s` passes.

**Verification.**

```
make down && time make up
curl -fsS http://localhost:18000/health
curl -fsS http://localhost:18001/health
pdm run pytest tests/integration/test_stack_up.py -k healthy
```

**Maps to:** FR-071, NFR-001, NFR-013, [Handoff Epic A — A1].

---

## Phase 2 — Target SUT minimum: schema and repositories

> **STATUS: COMPLETE — 2026-05-20.** All exit criteria met. 7-table schema with `test_run_id` discipline and NFR-010 CHECK constraints applied via Postgres `docker-entrypoint-initdb.d/`. Member Pydantic model + async repository + internal routes wired with typed error mapping (409 / 422). 10 new integration tests added (16 total in suite), all passing. See [CHANGELOG.md "Added — 2026-05-20 — Phase 2"](../CHANGELOG.md).

**Goal.** Target SUT has the 7-entity schema with `test_run_id` discipline; repository methods exist for Member only; migrations apply on container start.

**Inputs.** Phase 1 complete.

**Work items.**

- `apps/target-healthcare-api/migrations/0001_init.sql`:
  - Tables: `member`, `plan`, `provider`, `eligibility`, `claim`, `procedure_code`, `diagnosis_code`.
  - Every mutable table has `test_run_id TEXT NOT NULL` and an index on it.
  - `procedure_code` and `diagnosis_code` have `test_run_id TEXT NULL` (shared reference data + per-run invalid codes).
  - DB CHECK constraint: `member.first_name LIKE 'FAKE\_%'` (enforces NFR-010 at DDL).
- `apps/target-healthcare-api/app/db/session.py` — async engine (`asyncpg`).
- `apps/target-healthcare-api/app/repositories/member.py` — `insert_member`, `delete_by_run_id`, `count_by_run_id`. Parameterized queries only.
- `apps/target-healthcare-api/app/routes/member.py` — internal routes used by the seeder: `POST /internal/members`, `DELETE /internal/members?run_id=...`.
- Migration runs on container startup via an entrypoint script.
- Unit tests on the Member repository against a Postgres test container (`testcontainers-python`) or against the docker-compose Postgres.

**Known pitfall (discovered in Phase 2) — Postgres `docker-entrypoint-initdb.d/` runs once.**

The `/docker-entrypoint-initdb.d/` directory in the official `postgres:16` image is processed **only when the data directory is empty**. If you bring up the stack in Phase 1 (no migrations mounted), then in Phase 2 you add migrations and re-run `make up`, the entrypoint sees a non-empty data directory and skips them entirely. You'll get a healthy stack with zero tables.

Resolution — bake this in during Phase 2:

1. Phase 2 migrations use `CREATE TABLE IF NOT EXISTS` and `INSERT ... ON CONFLICT DO NOTHING` so they are idempotent and safe to re-apply.
2. Provide a `make migrate` target that runs every `.sql` file in the migrations directory against the live Postgres via `psql`. This works on any state of the data directory and is the recommended path for incremental schema changes during dev.
3. For a true reset, document `make down-clean && make up` (destructive — wipes the volume). Used when you need the entrypoint to re-fire on a known-empty data directory.
4. Document all of the above in `docs/development.md` so future contributors know the three paths.

In Phase 3+ where migrations grow more complex, consider replacing the entrypoint pattern with a dedicated migration tool (alembic, dbmate, atlas) that tracks applied state in a `schema_migrations` table. The entrypoint pattern is fine for Phase 2's single-file schema.

**Other Phase 2 lessons learned (lower-impact):**

- `asyncpg` ships no type stubs. With `mypy --strict`, add `asyncpg-stubs` as a dev dep. Without stubs you get `Skipping analyzing "asyncpg": module is installed, but missing library stubs` errors that block lint.
- `pool.acquire()` yields `PoolConnectionProxy[Any]`, not `Connection[Any]`. Annotate the context-manager return type accordingly.
- `pytest-asyncio` 0.26 requires `pytest < 9` (transitively downgrades pytest). Pin if you depend on pytest 9 features.

**Exit criteria.**

- `make up` ends with the schema present and `\dt` listing all 7 tables.
- Member repository tests pass: insert one row, count by run_id, delete by run_id, count returns 0.
- Constraint check works: inserting a member with `first_name = 'Bob'` (no FAKE_ prefix) fails with a check-violation error.

**Verification.**

```
make up
pdm run pytest apps/target-healthcare-api/tests/ -k member
```

**Maps to:** FR-011, FR-012, FR-015, FR-016, DR-001, DR-002, DR-004, NFR-010, [Handoff Epic B — data model section].

---

## Phase 3 — First vertical slice: one scenario, one entity, one reset path

> **STATUS: COMPLETE — 2026-05-20.** All BRD §13 acceptance blocks (FR-001/FR-005, FR-030/FR-035, E1, E2) pass against the live stack. Headline `POST /test-data/requests` end-to-end: planner → seeder → catalog → audit → response in ~1s. Reset round-trip with cleanup_token verification, idempotency, 403/404 paths all green. Scenario YAML registry, rule-based planner, deterministic seedable generators, MinIO+Parquet catalog/audit, Bearer-token middleware, `ATDM_PLANNER=llm` 501 stub — all shipped. 11 new integration tests + 6 new unit tests, all 36 tests in the suite passing.

**Known prerequisite (discovered in Phase 3) — Member needs Plan.** The PLAN.md work items below say "Member only" for generators/seeders/routes. But Member.plan_id is a FK to Plan in the Phase 2 schema, so any Member insert requires a Plan first. Phase 3 added a minimal Plan repo+route on the Target SUT (mirror of Member, ~50 lines total) as an in-phase prerequisite — NOT scope creep, just FK reality. The general lesson for Phase 4+: **when sequencing entity work, sequence by FK dependency order**, not alphabetical or arbitrary. The seven entities should be added in order: ProcedureCode + DiagnosisCode (independent reference) → Plan (independent) → Provider (independent) → Member (FK to Plan) → Eligibility (FK to Member) → Claim (FK to Member, Provider, codes).

**Goal.** `POST /test-data/requests` for the single scenario `active_member_clean` produces a Member in the Target SUT, returns a `test_run_id` and `cleanup_token`, and `POST /test-data/runs/{run_id}/reset` removes the Member. The audit log records the request happy-path events.

This is the **first demoable end-to-end slice**. Everything after this is broadening.

**Inputs.** Phase 2 complete.

**Work items.**

- `apps/test-data-agent/app/scenarios/active_member_clean.yaml` — declares scenario_id, constraints schema (empty), generators=[`generate_member`], validators=[].
- `apps/test-data-agent/app/scenarios/registry.py` — loads YAML scenarios at startup; exposes lookup by `scenario` name.
- `apps/test-data-agent/app/generators/member.py` — pure function `generate_member(seed: int, constraints) -> MemberDict`. Names from a fixed `FAKE_` pool. State always `"ZZ"`.
- `apps/test-data-agent/app/seeders/healthcare.py` — minimal: a single function `seed_member` that POSTs to the Target SUT internal route inside a transaction context (or a saga that compensates on partial failure).
- `apps/test-data-agent/app/reset/strategies.py` — implements `reset_run(run_id, cleanup_token)` via Target SUT `DELETE /internal/members?run_id=...`.
- `apps/test-data-agent/app/audit/writer.py` — append-only Parquet writer to MinIO bucket `atdm-audit`, partitioned by `dt=YYYY-MM-DD`.
- `apps/test-data-agent/app/api/requests.py` — `POST /test-data/requests` wiring: schema validate → planner (rule-based) → validators (none yet) → seeder → cleanup token → audit append → response.
- `apps/test-data-agent/app/api/reset.py` — `POST /test-data/runs/{run_id}/reset`.
- `apps/test-data-agent/app/api/audit.py` — `GET /audit/runs/{run_id}` returning JSON.
- Cleanup token: 128-bit random; stored in catalog (Parquet) keyed by `run_id`; **hashed (sha256)** in audit log (DR-007).
- `test_run_id`: ULID library.
- API token middleware: rejects mutating requests without `Authorization: Bearer ${ATDM_API_TOKEN}`.

**Exit criteria — acceptance blocks from BRD §13 and Handoff Epic E:**

- FR-001 / FR-005 happy path (FR-001 acceptance block) returns 200 with the contract shape.
- FR-030 / FR-035 acceptance block: reset with correct token → 200; same call again → `already_cleaned`; wrong token → 403; no rows remain after success.
- E1 acceptance block (subset for happy path): audit events `request_received`, `plan_resolved`, `seed_started`, `seed_completed`, `catalog_recorded` exist in chronological order for the run.
- E2 acceptance block: `GET /audit/runs/{run_id}` returns the JSON contract.

**Verification.**

```
make up
# Request
curl -fsS -X POST http://localhost:18001/test-data/requests \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d '{"domain":"healthcare","scenario":"active_member_clean","constraints":{},
          "delivery":{"seed_target":true,"return_playwright_fixture":false,
                      "return_pytest_fixture":false,"cleanup_strategy":"after_test"}}' \
     | tee /tmp/atdm-resp.json
RUN_ID=$(jq -r .test_run_id /tmp/atdm-resp.json)
TOKEN=$(jq -r .cleanup.cleanup_token /tmp/atdm-resp.json)
# Audit
curl -fsS http://localhost:18001/audit/runs/$RUN_ID | jq .
# Reset
curl -fsS -X POST http://localhost:18001/test-data/runs/$RUN_ID/reset \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d "{\"cleanup_token\":\"$TOKEN\"}"
# Idempotent
curl -fsS -X POST http://localhost:18001/test-data/runs/$RUN_ID/reset \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d "{\"cleanup_token\":\"$TOKEN\"}"
# Wrong token
curl -fsS -o /dev/null -w "%{http_code}\n" -X POST \
     http://localhost:18001/test-data/runs/$RUN_ID/reset \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d '{"cleanup_token":"wrong"}'   # expect 403
```

**Maps to:** FR-001, FR-002, FR-003, FR-005, FR-006, FR-007, FR-010 (Member only), FR-012, FR-014, FR-015, FR-030, FR-034, FR-035, FR-040, FR-050, FR-051, FR-052, DR-001, DR-007, NFR-004, NFR-005, AR-002, AR-003.

**Strategic note.** This phase is the minimum proof of the architecture. Do **not** widen scope until this passes cleanly. Resist adding entities, scenarios, fixtures, or the HTML UI here.

---

## Phase 4 — Broaden generators, validators, and scenarios

> **STATUS: COMPLETE — 2026-05-20.** All BRD §13 acceptance blocks (B1, B2) and Phase 4 exit criteria met. All 5 scenarios fulfill end-to-end against the live stack. Four validators wired and rejection produces 422 + `plan_rejected` audit + zero DB writes. Atomic bundle insert (`POST /internal/scenarios/seed`) replaces per-entity HTTP calls — saga compensation removed in favor of server-side Postgres transactions. **Coverage: 91% combined on generators/ + validators/ + seeders/** (every module ≥80%). 47 unit tests + 35 integration tests, all green.

**Goal.** All 7 entities have generators; the registered 5 scenarios are demoable; validators are wired and rejection produces 422 with no DB writes.

**Inputs.** Phase 3 complete.

**Work items.**

- Generators for Plan, Provider, Eligibility, Claim, ProcedureCode, DiagnosisCode in `apps/test-data-agent/app/generators/`. All pure, seedable.
- Repositories and internal routes on the Target SUT for the remaining 6 entities (mirrors the Member work in Phase 2).
- Validators in `apps/test-data-agent/app/validators/`:
  - `relational.eligibility_status_matches_member` — inactive member cannot have active eligibility.
  - `relational.claim_references_existing_member` — Claim.member_id must be in the same run.
  - `domain.denial_requires_invalid_code` — `claim.status="denied"` requires a procedure_code marked invalid OR a denial_reason.
  - `temporal.eligibility_window_contains_claim` — denied/pending claims must have submitted_at within an eligibility window.
- Five YAML scenarios:
  - `active_member_clean` (already exists from Phase 3).
  - `claim_denial_active_member` — headline scenario.
  - `expired_eligibility`.
  - `out_of_network_pending_claim`.
  - `inactive_member_with_history`.
- Each scenario YAML names the generators and validators it composes.
- Seeder orchestrates entity ordering and enforces single-transaction or compensating-saga semantics. Implement transaction approach first: open one transaction at the Target-SUT side via a single "scenario seed" route that accepts the whole record bundle.
- Replace the per-entity `POST /internal/<entity>` calls with one `POST /internal/scenarios/seed` route that accepts the full bundle and commits atomically (avoids cross-HTTP transactions).

**Known pitfalls (discovered in Phase 4):**

1. **A per-entity `_force_cleanup` test helper breaks the moment a phase adds a child entity.** Phase 3 helpers did `DELETE FROM member; DELETE FROM plan`. Phase 4 added Eligibility and Claim, both FK-referencing Member, so Phase 3 cleanup started failing on constraint violations. **Resolution baked into PLAN.md**: every test's cleanup uses the most atomic DELETE the API exposes (`DELETE /internal/scenarios?run_id=...`), never a per-table enumeration. Adding a new entity should not require touching any prior phase's tests.

2. **Per-event audit event lists are fragile.** Phase 3 tests asserted `actions == [request_received, plan_resolved, seed_started, seed_completed, catalog_recorded]`. Phase 4 inserted `validators_passed` between `seed_started` and `seed_completed`, breaking the assertion. **Recommendation for Phase 5+**: assert on the *presence and order* of required events (e.g., `seed_started` < `seed_completed`), not on exact equality to a fixed list. Audit events are append-only and additive across phases.

3. **A `_pk(record)` helper that scans for `*_id` keys returns the wrong key when a record carries both a PK and an FK.** Member has both `member_id` (PK) and `plan_id` (FK); iterating keys returns `plan_id` first. Subtle: smoke-tests fine, production response shows `member_id == "plan-XXX"`. **Resolution**: pass the entity kind explicitly. **General rule**: helpers that scan over a fixed key list should never silently pick a winner — make the lookup explicit.

4. **B4 acceptance ("inject a generator failure → 500") is over-spec for the new flow.** With Phase 4's atomic bundle insert, a generator failure happens BEFORE any HTTP call to the SUT, so "zero rows written" is automatic — there's no race window. Resolution: B4 is exercised as a unit test on the seeder (`SeedError` on unknown generator), not as an integration test that needs fault injection. The actual server-side failure path (e.g., FK violation from a misgenerated record) is exercised by the existing 422 path with `CHECK_VIOLATION` / `FK_VIOLATION` codes.

5. **Sequencing entity work by FK dependency was the right call** (lesson from Phase 3). Phase 4 added the 5 remaining entities in one go via the bundle endpoint, sidestepping per-entity HTTP route work. The PLAN said "replace per-entity calls with bundle" — that simplification removed ~150 lines of saga-compensation code and made atomicity a server-side property instead of an application invariant.

**Exit criteria.**

- B1 acceptance block on `claim_denial_active_member` (Handoff Epic B).
- B2 acceptance block: feed contradicting constraints → 422 → zero rows written, audit `plan_rejected` event.
- B4 acceptance block: inject a generator failure → 500 → zero rows written, audit `seed_failed` event.
- All 5 scenarios fulfill successfully against a clean Target SUT.
- ≥ 80 % line coverage on `generators/`, `validators/`, `seeders/`.

**Verification.**

```
pdm run pytest apps/test-data-agent/tests/ -k "scenario or validator or generator" --cov=apps/test-data-agent/app --cov-report=term-missing
```

**Maps to:** FR-003, FR-004, FR-010, FR-011, FR-013, FR-014, FR-015, NFR-008, AR-002, [Handoff Epic B — B1, B2, B3, B4].

---

## Phase 5 — Full reset surface

> **STATUS: COMPLETE — 2026-05-20.** All five reset strategies live and demoable from the ATDM agent's HTTP API. C1 still passes; C2 (snapshot/restore round-trip + idempotency), C3 (`reset_all` clears tagged-only), and C4 (idempotent_seed) all pass against the live stack with deterministic SHA-256 row-hash verification. `X-Confirm: yes` gate enforced (428 without). Snapshot/restore is schema-agnostic Parquet round-trip via PyArrow + MinIO. **90 tests passing across unit, integration, and e2e (47 unit + 43 integration).**

**Inputs.** Phase 4 complete.

**Known pitfalls (discovered in Phase 5):**

1. **Snapshot/restore belongs server-side, not in the agent.** PLAN.md originally placed `snapshotter.py` under `apps/test-data-agent/`. But the SUT owns the schema and the rows, and AR-003 forbids the agent from running raw SQL. Moving snapshot/restore into the SUT (`apps/target-healthcare-api/app/reset/snapshotter.py`) cleanly inverts the layering — the SUT does the data work, the agent orchestrates and writes audit events. **General rule**: a service that owns the data also owns the snapshot of that data.

2. **`TRUNCATE ... CASCADE` is the right tool for restore.** Doing `DELETE FROM table WHERE 1=1` per table in FK order works but requires careful ordering. `TRUNCATE table1, table2, ... CASCADE` truncates everything in one statement, ignoring FK constraints. Restore then re-inserts in FK order from Parquet. Two SQL statements, total. TRUNCATE inside a `BEGIN ... COMMIT` is transactional in Postgres — rollback works.

3. **Schema-agnostic Parquet round-trip — `SELECT *` is the right primitive.** Avoid hard-coding column lists in snapshot/restore. `SELECT *` plus `INSERT INTO table (cols...) VALUES (...)` derived from the Parquet's columns means Phase 6+ schema changes don't touch snapshot/restore. Dynamic SQL is acceptable inside the SUT (AR-003 forbids it only in agent code).

4. **Strategy invocations need their own audit run IDs.** `reset_all` and the baseline endpoints don't have a scenario `test_run_id` — but the audit trail still needs to record them. Resolution: synthetic `strategy-{name}-{ULID}` run IDs. They show up in `GET /audit/runs/{id}` like any scenario run. **General rule**: every action that mutates state earns an audit run_id, even if it isn't scoped to a scenario.

5. **State-equivalence verification needs a deterministic hash.** Phase 5 tests assert that restore yields the captured state. Row-count comparison isn't enough (right counts, wrong values). Resolution: `md5(string_agg(t::text, '|' ORDER BY t::text))` per table — a content hash invariant to insert order. Per NFR-016, this includes all columns (TEXT PKs in our schema). For schemas with auto-increment IDs, hash non-PK columns only.

**Work items.**

- `POST /test-data/reset/all` — truncates rows where `test_run_id IS NOT NULL` on every mutable table. Reference rows with `test_run_id IS NULL` are preserved.
- `POST /test-data/baseline/snapshot` — reads every mutable table to Parquet under `s3://atdm-catalog/baselines/{baseline_id}/<table>.parquet`. Records baseline metadata in catalog.
- `POST /test-data/baseline/restore` — truncates mutable tables, replays the snapshot, writes audit event.
- Idempotent seed semantics: running `baseline_restore` twice produces identical state.
- `apps/test-data-agent/app/reset/snapshotter.py` — capture/restore via PyArrow + DuckDB.
- Optional safety: `POST /test-data/reset/all` requires header `X-Confirm: yes` (Should — implement now to avoid accidental nukes during demos).
- Audit log records every reset with strategy name and `cleared_record_count`.

**Exit criteria — acceptance blocks from BRD §13 and Handoff Epic C:**

- C1 (already met in Phase 3) still passes.
- C2: baseline snapshot → arbitrary scenario requests → baseline restore → row-hash match (excluding auto-increment IDs). Second restore identical.
- C3: `reset_all` clears run-tagged rows only; reference rows untouched.
- C4: `idempotent_seed` — re-running baseline restore is identical.

**Verification.**

```
pdm run pytest apps/test-data-agent/tests/test_reset.py -v
make smoke   # exercises all five strategies end-to-end via CLI
```

**Maps to:** FR-031, FR-032, FR-033, FR-034, FR-036, NFR-005, [Handoff Epic C].

---

## Phase 6 — Fixture delivery: Playwright JSON and pytest module

> **STATUS: COMPLETE — 2026-05-20.** D1 + D2 acceptance blocks verified end-to-end against the live stack. `delivery.return_playwright_fixture` and `delivery.return_pytest_fixture` honored; files land under `ATDM_FIXTURE_DIR` (mounted to `automation/fixtures/` on the host); response `fixtures` block carries paths; `fixtures_emitted` audit event recorded. 6 new unit tests for the writers + 4 integration tests. **100 tests passing total (53 unit + 47 integration).**

**Known pitfall (discovered in Phase 6):**

- **Embedding JSON inside a Python triple-quoted string breaks on backslashes.** The first version of the pytest-module writer concatenated `json.dumps(payload)` between `"""..."""`. Payloads containing `\\Users\\fake` (Windows paths) became `\Users\fake` after Python parsed the source file — invalid JSON. **Resolution baked into the writer**: embed the payload via `repr()` on the dict, not as embedded JSON. Python's `repr()` on built-in types round-trips cleanly through normal module loading. **General rule for codegen**: when emitting Python source that needs to embed runtime data, use `repr()` to produce a literal — never concatenate non-Python strings into a string literal.

**Inputs.** Phase 5 complete.

**Work items.**

- `apps/test-data-agent/app/fixtures/playwright.py` — emits JSON `{scenario_id, test_run_id, data, cleanup}`.
- `apps/test-data-agent/app/fixtures/pytest_module.py` — emits a `.py` module exposing `scenario_data()` returning the dict.
- Wire `delivery.return_playwright_fixture` and `delivery.return_pytest_fixture` flags through `POST /test-data/requests`.
- Response `fixtures.playwright` and `fixtures.pytest` carry the absolute paths.
- Audit event `fixtures_emitted` records what was written.

**Exit criteria.**

- D1 acceptance block: Playwright file written, valid JSON, contains required keys.
- D2 acceptance block: pytest module importable and `scenario_data()` returns the dict.

**Verification.**

```
pdm run pytest apps/test-data-agent/tests/test_fixtures.py -v
ls -la ./automation/fixtures/
```

**Maps to:** FR-020, FR-021, FR-022, FR-023, [Handoff Epic D — D1, D2].

---

## Phase 7 — `atdm` CLI and `atdm.pytest` library

> **STATUS: COMPLETE — 2026-05-20.** `atdm` console script installs via editable package and is on the PATH after `pdm install`. All 8 subcommands exit 0 on happy path and propagate API errors as non-zero exits with structured stderr. `@atdm_scenario("...")` decorator + `atdm_data` fixture auto-load via pytest11 entry point and successfully seed + reset against the live stack (D3 verified at both unit and integration layers). **125 tests passing total (73 unit + 52 integration).**

**Known pitfalls (discovered in Phase 7):**

1. **Typer chokes on `Any` in command signatures.** Initial CLI wrapped each command in an `@_handle` error decorator that exposed `*args: Any, **kwargs: Any` to Typer's parameter introspection. Typer rejected the whole CLI. Resolution: inline the error handling per command instead of wrapping. **General rule**: when working with Typer/Click, wrapped functions must preserve the exact signature, or the wrapper has to be a no-op for parameter introspection.

2. **Typer global options must precede the subcommand.** `atdm request scenario -o json` fails with "No such option `-o`" because `--output` is on the root callback. Correct: `atdm -o json request scenario`. Worth documenting in user-facing examples.

3. **The duplicate-package mypy trap extended again — `tests/` this time.** Phase 7's `apps/test-data-agent/python/tests/` collides with `apps/test-data-agent/tests/`. Resolution mirrors the original `app` trap: add a fourth mypy invocation in the Makefile, explicit per-source-root. **General rule** (locked in by three repeated occurrences now): every new package root under `apps/<name>/` needs its own mypy invocation. Don't try to make one invocation cover multiple namespace-colliding subtrees.

4. **`pytest.request.addfinalizer` runs BEFORE yield-fixture teardowns.** Tried to verify "the decorator's teardown emits reset_completed" by adding a finalizer to a marker-decorated test. The finalizer ran first (LIFO inside the test scope), then the `atdm_data` fixture's teardown — so the audit trail was inspected pre-reset. Resolution: cover the property in unit tests with `pytester` + a mock client, not at the integration layer. **General rule**: cross-fixture verification needs a session-scoped tracker, not a test-scoped finalizer.

5. **PEP 561 `py.typed` must be force-included in the wheel.** Without it, downstream mypy treats every `atdm.*` import as untyped and refuses to type-check decorators. Hatchling needs `[tool.hatch.build.targets.wheel.force-include] "atdm/py.typed" = "atdm/py.typed"` (the marker file itself plus the build config).

**Inputs.** Phase 6 complete.

**Work items.**

- `apps/test-data-agent/python/atdm/cli.py` — Click or Typer; subcommands `request`, `reset`, `baseline-snapshot`, `baseline-restore`, `audit`, `catalog`.
- Reads `ATDM_API_URL` and `ATDM_API_TOKEN` from env.
- `--output json` for machine-readable mode; default is human-readable.
- Non-zero exit on API error.
- `apps/test-data-agent/python/atdm/pytest.py` — `@atdm_scenario("name", constraints={...})` decorator that, in pytest fixture lifecycle, requests data and registers a finalizer that calls `reset_run`.
- `pyproject.toml` installs `atdm` as a console script entry point.
- Example tests in `automation/pytest-api/test_example_member.py` using the decorator.
- Example Playwright test in `automation/playwright/tests/member.spec.ts` consuming a JSON fixture (requires a tiny `package.json` and a one-shot `make playwright-install`).

**Exit criteria.**

- D3 acceptance block: `@atdm_scenario` test runs, fixture has expected fields, teardown logs `status=cleaned` in audit.
- CLI subcommand smoke: each subcommand exits 0 on a happy-path invocation and prints both human and JSON output.
- `pdm install -G atdm` (or `pip install -e ./apps/test-data-agent/python`) works from a fresh clone.
- One Playwright test passes against the live demo stack.

**Verification.**

```
atdm request --scenario active_member_clean --output json
atdm audit <run_id> --output json
pdm run pytest automation/pytest-api -v
cd automation/playwright && npx playwright test
```

**Maps to:** FR-024, FR-060, FR-061, FR-062, IR (Playwright / pytest), [Handoff Epic D — D3].

---

## Phase 8 — Audit HTML page and architecture fitness test

**Goal.** `GET /ui/audit/{run_id}` renders a server-side HTML page that a reviewer reads in a browser; AR-003 architectural fitness test runs in CI and would fail any future refactor that lets an agent write SQL.

This is the **single most important phase for portfolio impact**, per BRD §14 R1 and §17 strategic note. Spend the time.

**Inputs.** Phase 7 complete.

**Work items.**

- `apps/test-data-agent/app/audit/ui.py` — FastAPI route that renders a Jinja template.
- `apps/test-data-agent/app/audit/templates/audit_run.html` — single page. Sections:
  - Header: run_id, scenario, invoker (`human:<name>` / `agent:<id>`), planner_mode, started_at → finished_at.
  - Plan section: generators in order; validators listed with pass/fail badges.
  - Records-created table: table_name, primary_key, link to row (for Postgres, a simple `psql` snippet copy-paste).
  - Fixtures list: file links to Playwright JSON and pytest module.
  - Reset status badge: `pending` | `cleaned` | `already_cleaned`.
  - Timeline: chronological event list with timestamps.
- Pico.css via CDN for visual polish (per open question 7; revisit if user prefers hand-rolled CSS).
- One screenshot committed to `docs/assets/audit-trail.png`.
- `tests/architecture/test_no_sql_from_agents.py` — greps `apps/test-data-agent/app/` for forbidden imports (`psycopg`, `asyncpg`, `sqlalchemy.engine`, `sqlmodel.Session.exec`). Fails CI on any match.
- `tests/architecture/test_audit_log_append_only.py` — proves no API surface deletes or updates audit events.
- `tests/architecture/test_no_emoji.py` — fails CI if any source/doc file under the project contains an emoji (per CLAUDE.md).
- CI workflow gains an `architecture` job that runs only these tests.

**Exit criteria.**

- E3 acceptance block: `/ui/audit/{run_id}` renders for a real run; ≤ 100 KB; 404 page for unknown run.
- E1 (full): every documented audit action appears for happy path, validator-rejection, and seed-failure paths.
- AR-003 fitness test passes and is wired into CI.
- Audit-append-only fitness test passes.
- No-emoji fitness test passes (and immediately catches if `docs/` or anywhere else has slipped).

**Verification.**

```
open http://localhost:18001/ui/audit/<a-known-run_id>
pdm run pytest tests/architecture/ -v
```

**Maps to:** FR-053, FR-050, FR-051, FR-052, NFR-011, NFR-012, AR-003, [Handoff Epic E].

---

## Phase 9 — `make demo`, README, design-decisions doc

**Goal.** A reviewer can clone the repo, run `make demo`, and watch the full intent → seed → test → reset → audit flow complete in ≤ 90 seconds with no manual steps.

**Inputs.** Phase 8 complete.

**Work items.**

- `make demo` orchestrates:
  1. `make up` (idempotent — skip if already healthy).
  2. `make baseline-snapshot` (one-shot if missing).
  3. `atdm request --scenario claim_denial_active_member --return-playwright-fixture --return-pytest-fixture`.
  4. Print returned run_id, cleanup token, fixture paths.
  5. `pdm run pytest automation/pytest-api/test_example_claim_denial.py` against the fresh fixture.
  6. `atdm reset <run_id>`.
  7. `atdm audit <run_id> --output json | jq .`.
  8. Print "Demo complete. Open http://localhost:18001/ui/audit/<run_id> in a browser." and exit 0.
- Reference reviewer flow scripted in `docs/demo-script.md`.
- `README.md` (≤ 400 lines):
  - Opens with the "what this proves" bullets from BRD §17.
  - Architecture diagram (`docs/assets/architecture.png`) — mermaid + exported PNG.
  - Quickstart (`make setup && make up && make demo`).
  - Link to `docs/architecture.md`, `docs/design-decisions.md`, `docs/healthcare-domain-model.md`, `docs/recruiter-summary.md`.
  - Security model section explicitly documenting the MVP-grade auth limitation (single shared API token; read endpoints open on local network).
  - Data ethics section: NFR-010 markers documented.
- `docs/design-decisions.md`:
  - Two worked-example audit records (rule-based path + LLM placeholder).
  - Why rule-based planner before LLM.
  - Why DuckDB + Parquet + MinIO.
  - Why single-transaction seeding via one Target-SUT route.
  - Why server-rendered HTML, no React.
- `docs/architecture.md` — high-level diagram + component descriptions.
- `docs/healthcare-domain-model.md` — entity catalog with relationships and example records.
- `docs/recruiter-summary.md` — one page, plain language.
- `FEATURES.md` — bulleted list of MVP features actually shipped.
- `CHANGELOG.md` — entries per merged PR.
- `TODO.md` — Phase 2+ items pulled from BRD §18.

**Exit criteria.**

- A2 acceptance block: `make demo` exits 0 within 90 seconds.
- README ≤ 400 lines (per CLAUDE.md, NFR-009).
- All five `docs/*` files exist and are current.
- One audit-trail screenshot in `docs/assets/`.
- One architecture diagram in `docs/assets/`.

**Verification.**

```
wc -l README.md   # must be ≤ 400
time make demo    # must be ≤ 90s
ls docs/ docs/assets/
```

**Maps to:** FR-072, NFR-009, NFR-014, [Handoff Epic A — A2, project-wide DoD].

---

## Phase 10 — Hardening, polish, and merge-to-`main`

**Goal.** CI is green, coverage is ≥ 80 % on the core modules, the demo is reproducible on a clean machine, and the project is presentable.

**Inputs.** Phase 9 complete.

**Work items.**

- Run a fresh-clone reviewer dry-run on a separate machine (or a fresh Docker context). Time `make up` and `make demo`. Adjust if either exceeds NFR-001 (60s) or A2 (90s).
- Add an asciinema cast or animated GIF of the demo to `docs/assets/` (open question 5 — confirm with user).
- Tag images by digest in `infra/docker-compose.yml`.
- Pin pdm lockfile.
- Add `pre-commit` hooks: ruff, mypy, no-emoji-grep.
- Add `make catalog-prune` (Could-have from BRD §16 Q11) only if the catalog growth becomes irritating during dev.
- Audit the codebase against the project-wide DoD checklist in [engineering-handoff.md](../requirements/engineering-handoff.md) — tick every box or open a TODO.

**Exit criteria — project-wide DoD from engineering-handoff.md:**

- [ ] All five reset strategies demonstrable from CLI and API.
- [ ] All seven entities generated, validated, seeded, and reset correctly.
- [ ] `make demo` runs the full flow in ≤ 90s.
- [ ] AR-003 architecture fitness test enforced in CI.
- [ ] `GET /ui/audit/{run_id}` renders for a real run; screenshot in `docs/assets/`.
- [ ] `atdm` CLI exposes all six subcommands.
- [ ] Playwright JSON fixture and pytest Python fixture both written and consumable.
- [ ] `atdm.pytest` installable and exercised by at least one example test.
- [ ] README ≤ 400 lines.
- [ ] All five `docs/*` files exist and are current.
- [ ] CHANGELOG, FEATURES, TODO maintained.
- [ ] Ruff + mypy --strict clean.
- [ ] Coverage ≥ 80 % on core modules.
- [ ] CI green on `main`.
- [ ] No PHI; all NFR-010 markers present and verified by test.
- [ ] LLM mode off by default; clearly marked Phase 2 in README and Makefile.

**Verification.**

```
make lint && make test && make demo
pdm run pytest --cov=apps/test-data-agent/app --cov-report=term-missing
grep -R --line-number -P "[\x{1F300}-\x{1FAFF}]" . || echo "no emoji"
```

**Maps to:** Project-wide DoD, full MVP definition from BRD §17.

---

## Dependencies and parallel work

Most phases are linear, but there are two opportunities to parallelize once Phase 3 is in:

- **Phase 4 (broaden generators) and Phase 5 (full reset surface)** can be developed in parallel branches because they touch different modules. Merge order: 4 then 5.
- **Phase 6 (fixtures), Phase 7 (CLI/library), and Phase 8 (audit UI + fitness)** can be developed in parallel after Phase 5 lands.

Phases 0–3 must be sequential. Phase 9 and 10 must be at the end.

---

## What is explicitly out of this plan (Phase 2 territory — see [BRD §18](../requirements/BRD.md))

- Real LLM planner calls (`ATDM_PLANNER=llm` ships as a 501-stub feature flag in MVP).
- MCP server.
- ChromaDB / pgvector retrieval.
- Reviewer UI for LLM plan acceptance.
- React dashboard.
- MotherDuck cloud mode.
- E-commerce domain pack.
- Multi-tenant auth / RBAC.
- Production deployment artifacts.

Do not let any of these bleed into MVP work. If one feels tempting mid-build, open a TODO entry and keep moving.

---

## Open dependencies — RESOLVED 2026-05-19

All 12 BRD §16 open questions are resolved. No blockers remain to Phase 0. The full decision table lives in [BRD §16](../requirements/BRD.md). Summary of decisions affecting this plan:

| # | Decision | Where this plan reflects it |
|---|---|---|
| 1 | Synthetic healthcare-style domain for MVP. | Phases 2–4 entities and scenarios. |
| 2 | LLM mode is a 501-stub feature flag; OFF by default. | Phase 3 work item — `ATDM_PLANNER=llm` returns HTTP 501 with `LLM_MODE_NOT_ENABLED`. |
| 3 | Single shared API token (`Authorization: Bearer ${ATDM_API_TOKEN}`). | Phase 3 middleware. |
| 4 | One in-repo FastAPI + Postgres Target SUT. | Phase 2 layout. |
| 5 | `make demo` in terminal **plus** an asciinema cast at `docs/assets/demo.cast`. | Phase 10 work item. |
| 6 | Every ScenarioDefinition YAML carries `linked_requirement_ids: list[str]` from MVP (FR-044). | Phase 3 + Phase 4 — scenarios/registry validation includes the field. |
| 7 | Audit HTML page uses Pico.css via CDN. | Phase 8. |
| 8 | MIT license. | Phase 0 work item adds `LICENSE` at repo root. |
| 9 | Playwright fixture is JSON only for MVP. | Phase 6. |
| 10 | `baseline_restore` produces logically-equivalent state; sequence values not reset (NFR-016). | Phase 5 verification uses non-PK hash compare. |
| 11 | Catalog grows indefinitely in MVP; `make catalog-prune` is Could-have. | Phase 10 optional item. |
| 12 | Conservative 512MB memory limit per service in compose (NFR-017). | Phase 1 work item. |

### Phase 0 — addition

- Add `LICENSE` at repo root with the standard MIT text, copyright `2026 Nick Baynham`.

### Phase 1 — addition

- Each service in `infra/docker-compose.yml` carries `deploy.resources.limits.memory: 512m` (postgres, minio, target-healthcare-api, test-data-agent). Verify with `docker compose config | grep -A1 memory`.

### Phase 3 — addition

- Schema-validate `linked_requirement_ids: list[str]` in the scenarios YAML loader; default to `[]` if missing. Surface it in `GET /catalog/scenarios` response.
- `ATDM_PLANNER=llm` causes the planner to short-circuit and return `501 {error:{code:"LLM_MODE_NOT_ENABLED"}}`. Rule-based mode is the default and only working mode.

### Phase 5 — addition

- Baseline-restore acceptance test compares row contents by **non-PK columns** (NFR-016). Do not compare auto-increment IDs.

### Phase 10 — addition

- Record the demo as an asciinema cast (`docs/assets/demo.cast`) and export an SVG via `asciinema-rec` or `svg-term-cli` for embedding in README.

---

## Suggested rhythm

- One phase per merge to `main`.
- Each phase opens a PR with the acceptance commands run in the description and CI green.
- CHANGELOG entry per PR.
- A short demo (Loom, asciinema, or live) of each phase's exit-criteria proof is optional but valuable for the portfolio story — even an off-the-cuff 30-second clip beats nothing.

The MVP is **done** when Phase 10's checklist is fully ticked. Anything not ticked goes into `TODO.md` as a Phase 2 item.
