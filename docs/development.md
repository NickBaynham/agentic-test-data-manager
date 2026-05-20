# Development Guide

This guide is for engineers working **on** ATDM. End-user docs are in the
top-level [README.md](../README.md).

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12 |
| pdm | 2.26+ |
| Docker Engine | 24+ |
| Docker Compose | v2 (`docker compose ...`, not legacy `docker-compose`) |
| GNU Make | any |

Verify with:

```bash
python3.12 --version
pdm --version
docker --version
docker compose version
```

## First-time setup

```bash
git clone git@github.com:NickBaynham/agentic-test-data-manager.git
cd agentic-test-data-manager
make setup       # pdm install
cp .env.example .env.local   # then edit if you want non-default secrets
```

## Day-to-day workflow

```bash
# Bring up the local stack (Postgres, MinIO, Target SUT stub, ATDM agent stub)
make up

# See what's running
make ps

# Tail container logs
make logs

# Run unit tests (no Docker)
make test          # or: make test-unit

# Run integration + e2e tests (uses the running stack)
make test-integration

# Lint and type-check
make lint

# Tear down (volumes preserved)
make down

# Tear down AND DELETE VOLUMES (destructive — wipes Postgres + MinIO data)
make down-clean
```

## Host port mapping

The stack uses **non-default host ports** to avoid colliding with other local
services. Container-internal ports are conventional; only the host side is
remapped. The full table lives in
[planning/PLAN.md Phase 1](../planning/PLAN.md#phase-1--docker-compose-postgres-minio-two-service-stubs).

| Service | Host port | URL |
|---|---|---|
| Postgres | `55432` | `postgres://atdm@localhost:55432/target_healthcare` |
| MinIO API | `19000` | `http://localhost:19000` |
| MinIO Console | `19001` | `http://localhost:19001` (browser; default creds in `.env.example`) |
| Target SUT | `18000` | `http://localhost:18000/health`, `http://localhost:18000/docs` |
| ATDM agent | `18001` | `http://localhost:18001/health`, `http://localhost:18001/metrics`, `http://localhost:18001/docs` |

Inside the compose network, services address each other by **service name +
container port** (e.g., `postgres:5432`, `minio:9000`). Host port mapping
only matters for connections from the developer's laptop.

## Project layout

```
apps/
  test-data-agent/
    app/              FastAPI agent — scenario requests, validators, seeders (Phase 3+)
    python/atdm/      Installable client library (Phase 7)
    tests/            Per-app unit tests
    requirements.txt  Container-side runtime deps
  target-healthcare-api/
    app/              FastAPI SUT — synthetic healthcare entities
    migrations/       SQL migrations (Phase 2)
    tests/            Per-app unit tests
    requirements.txt  Container-side runtime deps
automation/
  playwright/         Playwright tests (Phase 7)
  pytest-api/         pytest-API tests (Phase 7)
  fixtures/           Generated fixtures (gitignored)
data/
  catalogs/, parquet/, seed/   (Phase 3+; gitignored except .gitkeep)
docs/                 This guide and others
infra/
  docker-compose.yml  The local stack
planning/PLAN.md      Phase-by-phase build plan
requirements/         BRD, engineering handoff, original concept
scripts/              Operational scripts (e.g., cold-start benchmark)
tests/                Root-level tests; tests/integration is the stack suite
```

## Testing

Tests are split into three layers and **must be run separately per source root**
(see [PLAN.md Phase 0 Known pitfall](../planning/PLAN.md) — the duplicate-`app`
mypy/pytest trap).

| Layer | How to run | What it covers |
|---|---|---|
| **Unit (top-level)** | `pdm run pytest tests -m "not integration and not e2e"` | Repo-level utilities and architecture tests. |
| **Unit (per-app)** | `PYTHONPATH=apps/<name> pdm run pytest apps/<name>/tests` | FastAPI stubs and (later) generators, validators, seeders. |
| **Integration** | `make test-integration` | Tests that hit the running compose stack. Tagged `@pytest.mark.integration`. |
| **E2E** | `make test-integration` (subset by `-m e2e`) | Full make-up → assert → make-down cycles. Tagged `@pytest.mark.e2e`. |

`make test` runs only the unit layers — never Docker. CI keeps the same
separation: `lint` and `test` jobs are Docker-free; the `stack` job runs
`make up && make test-integration && make down`.

## Adding a new endpoint

1. Add the route to `apps/<name>/app/main.py` (Phase 1) — later it'll move
   to `apps/<name>/app/api/...` (Phase 3+).
2. Write the unit test under `apps/<name>/tests/test_<feature>.py` using
   `fastapi.testclient.TestClient`.
3. Run that app's tests:
   ```bash
   PYTHONPATH=apps/<name> pdm run pytest apps/<name>/tests
   ```
4. If the endpoint is observed from outside the stack, add an integration
   test under `tests/integration/`.
5. Run `make lint && make test && make test-integration` before commit.

## Database schema and migrations

The Target SUT schema lives in `apps/target-healthcare-api/migrations/`. Files
are `NNNN_<description>.sql` in sequence — `0001_init.sql` lands the seven
entities and the baseline reference data (procedure / diagnosis codes).

### How migrations are applied

- **On a fresh Postgres volume:** the compose file bind-mounts `migrations/`
  into `/docker-entrypoint-initdb.d/` on the postgres container. Files in
  that directory are executed **once** when the data directory is first
  initialized.
- **On an existing volume:** `make migrate` runs every `.sql` file in the
  directory against the running Postgres via `psql`. The Phase 2 migration
  uses `CREATE TABLE IF NOT EXISTS` and `INSERT ... ON CONFLICT DO NOTHING`
  so it is idempotent — re-applying does nothing.
- **After schema changes (during dev):** the simplest path is
  `make down-clean && make up`. This wipes the Postgres volume so the
  entrypoint re-runs from scratch. `make down-clean` is destructive — only
  run it when you intend to throw away local data.

### Schema overview (Phase 2)

Seven entities per [BRD §9](../requirements/BRD.md):

- `plan`, `provider`, `member`, `eligibility`, `claim` — mutable, every row
  carries `test_run_id NOT NULL` with an index (DR-001 — required for the
  `reset_run` strategy in Phase 5).
- `procedure_code`, `diagnosis_code` — reference tables; `test_run_id` is
  nullable so baseline rows (shared across all runs) coexist with per-run
  "invalid" codes that drive denial scenarios.

NFR-010 markers are enforced at two levels:

- **Pydantic models** (fast feedback, returns 422 before DB round-trip).
- **DB CHECK constraints** (defense in depth, catches inserts that bypass
  the agent): `member.first_name`/`last_name` must start with `FAKE_`;
  `member.address_state` must equal `ZZ`.

### Inspecting the schema

```bash
docker exec atdm_postgres psql -U atdm -d target_healthcare -c "\dt"
docker exec atdm_postgres psql -U atdm -d target_healthcare -c "\d+ member"
```

## Cold-start benchmark (NFR-001)

To measure the stack cold-start budget (NFR-001: ≤ 60 seconds p95 over 5 runs):

```bash
./scripts/measure_cold_start.sh 5
```

Sample output on a reference Mac (M2, 16 GB):

```
  run 1: 18s
  run 2: 18s
  run 3: 18s
  run 4: 17s
  run 5: 17s
  p50 (median): 18s
  p95 (max):    18s
  NFR-001 budget: 60s p95
  status: PASS
```

If p95 exceeds 60s on your hardware, investigate before scaling up the stack.

## Intent-to-data request (Phase 3 — headline endpoint)

The ATDM agent now serves the headline endpoint. End-to-end example against
the local stack:

```bash
# Request a scenario. The Authorization header is required for all mutations.
RESP=$(curl -fsS -X POST http://localhost:18001/test-data/requests \
  -H 'authorization: Bearer dev-token-change-me' \
  -H 'content-type: application/json' \
  -d '{"domain":"healthcare","scenario":"active_member_clean","constraints":{},
       "delivery":{"seed_target":true}}')
echo "$RESP" | jq .

RUN=$(echo "$RESP" | jq -r .test_run_id)
TOKEN=$(echo "$RESP" | jq -r .cleanup.cleanup_token)

# Inspect the audit trail.
curl -fsS "http://localhost:18001/audit/runs/$RUN" | jq '.events[].action'

# Reset.
curl -fsS -X POST "http://localhost:18001/test-data/runs/$RUN/reset" \
  -H 'authorization: Bearer dev-token-change-me' \
  -H 'content-type: application/json' \
  -d "{\"cleanup_token\":\"$TOKEN\"}" | jq .
```

### Adding a new scenario

1. Drop a YAML file in `apps/test-data-agent/app/scenarios/`. Required keys:
   `scenario_id`, `generators` (ordered list of generator function names),
   `validators` (currently empty until Phase 4), `linked_requirement_ids`
   (may be empty, but the field is mandatory — FR-044).
2. If the scenario needs new generators, add them under
   `apps/test-data-agent/app/generators/` and register them in the seeder's
   `_GENERATOR_TO_ROUTES` map.
3. The scenario registry loads at agent startup — `make down && make up`
   (or `docker compose restart test-data-agent`) for changes to take effect.

### Planner modes

- `ATDM_PLANNER=rule` (default in MVP) — deterministic lookup by scenario_id.
- `ATDM_PLANNER=llm` — Phase 4+; returns 501 `LLM_MODE_NOT_ENABLED` in MVP.

### Catalog and audit storage

The catalog (`s3://atdm-catalog/runs/{run_id}.parquet`) holds one row per
ScenarioRequest with the sha256 hash of its cleanup token. The audit log
(`s3://atdm-audit/runs/{run_id}.parquet`) holds the chronological event trail
for that run. Both live in MinIO — browse them at
`http://localhost:19001` (default creds in `.env.example`).

## Member entity (Phase 2 — internal use)

The Target SUT exposes Member CRUD under `/internal/`. These routes are
consumed by the agent's seeder (Phase 3+), not by humans, but they're
documented here for visibility.

```bash
# Create a plan first (Member.plan_id is a FK)
docker exec atdm_postgres psql -U atdm -d target_healthcare -c \
  "INSERT INTO plan VALUES ('plan-dev', 'Dev Plan', 'hmo', '2026-01-01', 'dev-run');"

# Create a member via the internal route
curl -fsS -X POST http://localhost:18000/internal/members \
  -H 'content-type: application/json' \
  -d '{"member_id":"m-dev","status":"active","first_name":"FAKE_Alice",
       "last_name":"FAKE_Smith","date_of_birth":"1990-04-12",
       "address":{"line1":"1 FAKE_Way","city":"FAKE_Town","state":"ZZ","zip":"00000"},
       "plan_id":"plan-dev","test_run_id":"dev-run"}'

# Count and delete
docker exec atdm_postgres psql -U atdm -d target_healthcare -tA -c \
  "SELECT COUNT(*) FROM member WHERE test_run_id='dev-run';"
curl -fsS -X DELETE "http://localhost:18000/internal/members?run_id=dev-run"
```

Browse the full OpenAPI doc at `http://localhost:18000/docs`.

## Troubleshooting

### `make up` fails with `bind: address already in use`

Another process is holding one of the host ports (`55432`, `19000`, `19001`,
`18000`, `18001`). Find it:

```bash
lsof -nP -iTCP:55432 -iTCP:19000 -iTCP:19001 -iTCP:18000 -iTCP:18001 -sTCP:LISTEN
```

If it's an old ATDM stack still running, `make down`. If it's something
unrelated, stop it or update the port mapping in
`infra/docker-compose.yml` (and the same table in PLAN.md, `.env.example`,
README, and this doc).

### Containers exit immediately after `make up`

Check logs:

```bash
make logs
# or for a single service:
docker logs atdm_test_data_agent
```

Common causes:
- `requirements.txt` install failed inside the container (network blip; retry `make up`).
- Code change in `app/main.py` has a syntax error — check the uvicorn log.

### Integration tests can't reach the stack

The session fixture (`tests/integration/conftest.py`) auto-detects whether the
stack is already up. If you want to debug a test against a long-running stack,
set:

```bash
export ATDM_KEEP_STACK_UP=1
make up
make test-integration
```

The fixture will skip tear-down, and the warm-start e2e test will skip.

### MinIO console is not loading at `http://localhost:19001`

Verify the container is healthy: `make ps`. Default credentials are in
`.env.example` (`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`).

### Tables are missing or schema looks wrong after schema changes

Postgres's `docker-entrypoint-initdb.d/` runs **only** when the data directory
is empty. If you've already brought up the stack and then changed the
migration files, the changes won't apply. Two ways forward:

- `make down-clean && make up` — wipes the postgres volume and lets the
  entrypoint re-run from scratch. Destructive.
- `make migrate` — runs every `.sql` file against the live Postgres via
  `psql`. Works if the migration is idempotent (the Phase 2 one is).

### `make lint` fails with `Duplicate module named "app"`

You probably tried to lint or test across both `apps/` packages in a single
mypy/pytest invocation. The Makefile is set up to invoke per source root
specifically to avoid this. See
[PLAN.md Phase 0 Known pitfall](../planning/PLAN.md) for the full story.

## Conventions

- No emojis in source files, logs, or UI (per project [CLAUDE.md](../CLAUDE.md)).
- `pdm` only. No `pip install` outside container `requirements.txt` files.
- All shared system tools (Postgres, MinIO) run in Docker locally.
- Maintain `CHANGELOG.md`, `FEATURES.md`, `TODO.md` with every merged change.
- When you encounter a surprise, write the resolution into the appropriate
  doc (PLAN.md "Known pitfall", CHANGELOG "Lessons learned", or here) so the
  next replay doesn't burn time on it again.
