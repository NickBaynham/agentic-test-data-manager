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
- Add `Makefile` with stub targets: `setup`, `up`, `down`, `lint`, `test`, `build`, `demo`, `reset-baseline`, `baseline-snapshot`, `smoke`.
- Add `pyproject.toml` ruff config (line-length 100, target py312) and `mypy.ini` (`strict = True`).
- Add `.env.example` with `ATDM_API_TOKEN`, `ATDM_API_URL`, `MINIO_*`, `POSTGRES_*`, `ATDM_FIXTURE_DIR`, `ATDM_PLANNER=rule`.
- Add `.github/workflows/ci.yml`: lint, test, architecture jobs.
- Add `CHANGELOG.md`, `FEATURES.md`, `TODO.md` (per CLAUDE.md).
- Add a top-level `README.md` placeholder with a "Status: in development" banner and links to `requirements/`.

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

**Goal.** `make up` brings up Postgres, MinIO, a Target-SUT stub, and an ATDM-agent stub. All four are healthy within 60 seconds.

**Inputs.** Phase 0 complete.

**Work items.**

- Add `infra/docker-compose.yml` with services:
  - `postgres:16` with healthcheck, named volume.
  - `minio/minio:latest` with healthcheck, named volume, two buckets autocreated via init container (`atdm-catalog`, `atdm-audit`, `atdm-fixtures`).
  - `target-healthcare-api` — FastAPI stub serving `GET /health`.
  - `test-data-agent` — FastAPI stub serving `GET /health` and `GET /metrics`.
- Pin all images by tag (not `latest` for the apps; pin MinIO and Postgres by digest in a follow-up).
- No host network mode. Only required ports published.
- `Makefile` `up` and `down` invoke `docker compose -f infra/docker-compose.yml`.

**Exit criteria.**

- `make up` reports all four services `healthy` within 60 seconds (p95 over 5 runs).
- `curl http://localhost:8000/health` and `curl http://localhost:8001/health` return 200.
- `make down` cleanly removes containers (volumes preserved).
- Smoke test `tests/integration/test_stack_up.py::test_all_services_healthy_within_60s` passes.

**Verification.**

```
make down && time make up
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8001/health
pdm run pytest tests/integration/test_stack_up.py -k healthy
```

**Maps to:** FR-071, NFR-001, NFR-013, [Handoff Epic A — A1].

---

## Phase 2 — Target SUT minimum: schema and repositories

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
curl -fsS -X POST http://localhost:8001/test-data/requests \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d '{"domain":"healthcare","scenario":"active_member_clean","constraints":{},
          "delivery":{"seed_target":true,"return_playwright_fixture":false,
                      "return_pytest_fixture":false,"cleanup_strategy":"after_test"}}' \
     | tee /tmp/atdm-resp.json
RUN_ID=$(jq -r .test_run_id /tmp/atdm-resp.json)
TOKEN=$(jq -r .cleanup.cleanup_token /tmp/atdm-resp.json)
# Audit
curl -fsS http://localhost:8001/audit/runs/$RUN_ID | jq .
# Reset
curl -fsS -X POST http://localhost:8001/test-data/runs/$RUN_ID/reset \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d "{\"cleanup_token\":\"$TOKEN\"}"
# Idempotent
curl -fsS -X POST http://localhost:8001/test-data/runs/$RUN_ID/reset \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d "{\"cleanup_token\":\"$TOKEN\"}"
# Wrong token
curl -fsS -o /dev/null -w "%{http_code}\n" -X POST \
     http://localhost:8001/test-data/runs/$RUN_ID/reset \
     -H "Authorization: Bearer dev-token" \
     -H "Content-Type: application/json" \
     -d '{"cleanup_token":"wrong"}'   # expect 403
```

**Maps to:** FR-001, FR-002, FR-003, FR-005, FR-006, FR-007, FR-010 (Member only), FR-012, FR-014, FR-015, FR-030, FR-034, FR-035, FR-040, FR-050, FR-051, FR-052, DR-001, DR-007, NFR-004, NFR-005, AR-002, AR-003.

**Strategic note.** This phase is the minimum proof of the architecture. Do **not** widen scope until this passes cleanly. Resist adding entities, scenarios, fixtures, or the HTML UI here.

---

## Phase 4 — Broaden generators, validators, and scenarios

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

**Goal.** All five reset strategies (`reset_run`, `reset_all`, `baseline_snapshot`, `baseline_restore`, `idempotent_seed`) are implemented and demoable from API and CLI.

**Inputs.** Phase 4 complete.

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

**Goal.** Every fulfilled scenario request optionally writes a Playwright JSON fixture and a pytest Python module to `ATDM_FIXTURE_DIR`, named `<scenario>_<run_id>.{json,py}`.

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

**Goal.** The `atdm` CLI wraps every HTTP endpoint with predictable subcommands; the `atdm.pytest` library exposes the `@atdm_scenario` decorator that requests data and tears it down automatically.

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
open http://localhost:8001/ui/audit/<a-known-run_id>
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
  8. Print "Demo complete. Open http://localhost:8001/ui/audit/<run_id> in a browser." and exit 0.
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
